"""真知识图谱：LLM 从资料正文抽取实体与有向关系。

与旧 `knowledge_map_service` 的区别：
  · 旧版是页面层级图（文档 → 章节），没有语义；
  · 本服务用 LLM 从文档 chunk 抽出「实体 + 实体之间的关系」，保存到
    `rag_graph_entity` / `rag_graph_relation`，并可回到 evidence chunk。

存储不依赖 Neo4j：当前 OpenStudy 的部署只有 PostgreSQL，实体/关系表 + JSON
来源字段足够支撑一个可筛选、可追溯的演示图。若未来关系规模变大，再把
`knowledge_graph_service` 的存储层替换为图数据库即可，接口契约不用变。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_graph import RagGraphEntity, RagGraphRelation
from app.models.rag import DOC_VECTORIZED, RagDocument, RagDocumentChunk
from app.services.ai.base_client import ChatMessage, TextBlock
from app.services.ai.db_config import chat_with_config
from app.services.rag.hybrid_search import ChunkHit

ENTITY_TYPES = ["概念", "定理/公式", "方法", "人物", "机构", "事件", "作品", "其他"]
RELATION_TYPES = ["包含", "属于", "定义", "推导", "应用", "前置", "对比", "相关", "产生", "属于领域"]
MAX_ENTITIES_PER_DOC = 40
MAX_RELATIONS_PER_DOC = 40
MAX_CHUNKS_PER_DOC = 12


def _norm_name(value: Any) -> str:
    name = re.sub(r"[\s\u3000]+", "", str(value or "").strip())
    name = name.strip("《》\"'“”‘’（）()[]【】")
    return name.lower()


def _canonical_key(value: Any) -> str:
    """把「智能体定义 / 智能体概念 / 智能体概述」这类同义写法归到实体本身。

    只处理材料里常见的解释性后缀，不做模糊同义词合并，避免把「函数」和
    「函数图像」这类不同概念误并成一个节点。
    """
    norm = _norm_name(value)
    for suffix in ("定义", "概念", "概述", "简介", "介绍", "说明"):
        if len(norm) > len(suffix) + 1 and norm.endswith(suffix):
            return norm[: -len(suffix)]
    return norm


def _clean(value: Any, limit: int = 400) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _matching_chunk_ids(name: str, chunks: List[RagDocumentChunk]) -> List[int]:
    """只把真正出现该实体名的 chunk 挂到实体上。

    旧实现把整篇文档的所有 chunk 都挂给每个实体，导致前端“来源 chunk”
    看起来有内容、实际却对不上。这里先按实体名精确匹配；匹配不到时返回空，
    由主题页生成阶段再用正文检索补来源，绝不伪造。
    """
    norm = _norm_name(name)
    if not norm:
        return []
    return [
        int(chunk.id)
        for chunk in chunks
        if getattr(chunk, "id", 0) and norm in _norm_name(chunk.content)
    ]


def _parse_json_payload(raw: str) -> Dict[str, Any]:
    text = str(raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("模型没有返回可解析的图谱 JSON")
        payload = json.loads(text[start : end + 1])
    if isinstance(payload, list):
        return {"entities": payload, "relations": []}
    if not isinstance(payload, dict):
        raise ValueError("图谱 JSON 不是对象")
    return payload


def _prompt(doc_name: str, context: str) -> str:
    return (
        "你是学习资料的知识图谱抽取器。请从给定资料片段中抽取实体和实体之间的关系。\n"
        "只输出一个 JSON 对象，不要 Markdown，不要解释。\n\n"
        "实体类型只能从以下列表选：'概念','定理/公式','方法','人物','机构','事件','作品','其他'。\n"
        "关系必须是资料中明确出现的，不要靠常识补关系；关系末端必须是同一份 JSON 里的实体。\n"
        "关系类型优先选最具体的一种：'属于','定义','推导','应用','前置','对比','产生','属于领域'；"
        "只有真正的整体—部分结构才用'包含'，不要把每一条关系都写成'包含'。\n"
        "输出格式（示例只示意字段，不要照抄示例内容）：\n"
        '{"entities":[{"name":"实体名","type":"概念","description":"资料中的简短解释"}],'
        '"relations":[{"source":"实体名1","target":"实体名2","type":"前置","description":"关系的原文依据","strength":8},'
        '{"source":"实体名1","target":"实体名3","type":"包含","description":"整体与部分关系","strength":6}]}\n'
        "strength 取值 1-10，越直接越强。若没有实体/关系，返回空数组。\n\n"
        f"资料名：{doc_name}\n资料片段：\n{context}"
    )


async def _document_chunks(db: AsyncSession, doc: RagDocument) -> List[RagDocumentChunk]:
    rows = (
        await db.execute(
            select(RagDocumentChunk)
            .where(
                RagDocumentChunk.doc_id == int(doc.id),
                RagDocumentChunk.index_version == int(getattr(doc, "index_version", 1) or 1),
            )
            .order_by(RagDocumentChunk.chunk_index.asc())
            .limit(MAX_CHUNKS_PER_DOC)
        )
    ).scalars().all()
    if rows:
        return list(rows)
    # 极端情况下 chunk 还没生成：退化为按原文切段，不伪造分块 ID。
    raw = str(doc.raw_content or "")
    if not raw:
        return []
    return [
        RagDocumentChunk(
            id=0,
            kb_id=int(doc.kb_id),
            doc_id=int(doc.id),
            chunk_index=0,
            index_version=int(getattr(doc, "index_version", 1) or 1),
            content=raw[:12000],
        )
    ]


async def _extract_doc(
    db: AsyncSession,
    user_id: int,
    doc: RagDocument,
    chunks: List[RagDocumentChunk],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    context = "\n\n".join(
        f"[片段 {int(c.chunk_index) + 1}] {str(c.content or '')[:1400]}"
        for c in chunks
        if str(c.content or "").strip()
    )
    if not context.strip():
        return [], [], []
    messages = [
        ChatMessage(role="system", content="你只输出严格 JSON，不输出客套话或 Markdown 代码围栏。"),
        ChatMessage(
            role="user",
            content=[TextBlock(type="text", text=_prompt(doc.file_name or "未命名资料", context))],
        ),
    ]
    response = await chat_with_config(
        db,
        messages,
        temperature=0.15,
        max_tokens=3500,
        user_id=int(user_id),
    )
    payload = _parse_json_payload(response.content or "")
    raw_entities = payload.get("entities") or payload.get("nodes") or []
    raw_relations = payload.get("relations") or payload.get("edges") or []
    entities: List[Dict[str, Any]] = []
    seen = set()
    for item in raw_entities:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name") or item.get("title"), 120)
        if not name or _norm_name(name) in seen:
            continue
        seen.add(_norm_name(name))
        kind = _clean(item.get("type"), 30) or "概念"
        if kind not in ENTITY_TYPES:
            kind = "概念"
        entities.append(
            {
                "name": name,
                "type": kind,
                "description": _clean(item.get("description"), 800),
                "doc_id": int(doc.id),
                "chunk_ids": _matching_chunk_ids(name, chunks),
            }
        )
        if len(entities) >= MAX_ENTITIES_PER_DOC:
            break
    names = {_norm_name(e["name"]): e for e in entities}
    relations: List[Dict[str, Any]] = []
    for item in raw_relations:
        if not isinstance(item, dict):
            continue
        source_name = _clean(item.get("source"), 120)
        target_name = _clean(item.get("target"), 120)
        source = names.get(_norm_name(source_name))
        target = names.get(_norm_name(target_name))
        if not source or not target or source is target:
            continue
        relation_type = _clean(item.get("type"), 40) or "相关"
        if relation_type not in RELATION_TYPES:
            relation_type = "相关"
        try:
            strength = max(1, min(10, int(item.get("strength") or 5)))
        except (TypeError, ValueError):
            strength = 5
        source_chunks = set(source.get("chunk_ids") or [])
        target_chunks = set(target.get("chunk_ids") or [])
        relation_chunk_ids = list(source_chunks & target_chunks) or list(source_chunks | target_chunks)
        relations.append(
            {
                "source": source["name"],
                "target": target["name"],
                "type": relation_type,
                "description": _clean(item.get("description"), 800),
                "strength": strength,
                "doc_id": int(doc.id),
                "chunk_ids": relation_chunk_ids,
            }
        )
        if len(relations) >= MAX_RELATIONS_PER_DOC:
            break
    return entities, relations, []


def _merge_unique(existing: Optional[list], new_values: Iterable[Any]) -> list:
    out = list(existing or [])
    for value in new_values:
        if value not in out:
            out.append(value)
    return out


async def merge_duplicate_entities(db: AsyncSession, user_id: int, kb_id: int) -> int:
    """合并历史数据里的同义实体（如「智能体」与「智能体定义」）。

    合并时同时迁移关系的 source/target，若迁移后与已有关系重复，则合并
    chunk_ids/strength 后删除重复关系，保证不会出现悬空边。
    """
    rows = (
        await db.execute(
            select(RagGraphEntity).where(
                RagGraphEntity.user_id == int(user_id),
                RagGraphEntity.kb_id == int(kb_id),
            )
        )
    ).scalars().all()
    groups: Dict[str, List[RagGraphEntity]] = {}
    for row in rows:
        groups.setdefault(_canonical_key(row.name), []).append(row)
    merged_count = 0
    for key, group in groups.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda item: (len(_norm_name(item.name)), -int(item.mention_count or 0)))
        keeper = group[0]
        for duplicate in group[1:]:
            if int(duplicate.id) == int(keeper.id):
                continue
            keeper.doc_ids = _merge_unique(keeper.doc_ids, duplicate.doc_ids or [])
            keeper.chunk_ids = _merge_unique(keeper.chunk_ids, duplicate.chunk_ids or [])
            keeper.mention_count = int(keeper.mention_count or 0) + int(duplicate.mention_count or 0)
            if not keeper.description or len(str(duplicate.description or "")) > len(str(keeper.description or "")):
                keeper.description = duplicate.description or keeper.description

            relations = (
                await db.execute(
                    select(RagGraphRelation).where(
                        RagGraphRelation.user_id == int(user_id),
                        RagGraphRelation.kb_id == int(kb_id),
                        or_(
                            RagGraphRelation.source_id == int(duplicate.id),
                            RagGraphRelation.target_id == int(duplicate.id),
                        ),
                    )
                )
            ).scalars().all()
            for relation in relations:
                new_source = int(keeper.id) if int(relation.source_id) == int(duplicate.id) else int(relation.source_id)
                new_target = int(keeper.id) if int(relation.target_id) == int(duplicate.id) else int(relation.target_id)
                if new_source == new_target:
                    await db.delete(relation)
                    continue
                existing = (
                    await db.execute(
                        select(RagGraphRelation).where(
                            RagGraphRelation.user_id == int(user_id),
                            RagGraphRelation.kb_id == int(kb_id),
                            RagGraphRelation.source_id == new_source,
                            RagGraphRelation.target_id == new_target,
                            RagGraphRelation.relation_type == relation.relation_type,
                            RagGraphRelation.id != int(relation.id),
                        )
                    )
                ).scalars().first()
                if existing:
                    existing.doc_ids = _merge_unique(existing.doc_ids, relation.doc_ids or [])
                    existing.chunk_ids = _merge_unique(existing.chunk_ids, relation.chunk_ids or [])
                    existing.strength = max(int(existing.strength or 5), int(relation.strength or 5))
                    existing.description = existing.description or relation.description
                    await db.delete(relation)
                else:
                    relation.source_id = new_source
                    relation.target_id = new_target
            await db.delete(duplicate)
            merged_count += 1
        keeper.normalized_name = _norm_name(keeper.name)
    if merged_count:
        await db.commit()
    return merged_count


async def build_graph(
    db: AsyncSession,
    user_id: int,
    kb_id: int,
    *,
    doc_ids: Optional[List[int]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """对资料夹内的文档抽取实体/关系。

    `force=False` 时跳过已经有实体的文档（避免重复消耗模型额度）。
    """
    await merge_duplicate_entities(db, user_id, kb_id)
    docs = (
        await db.execute(
            select(RagDocument)
            .where(RagDocument.user_id == int(user_id), RagDocument.kb_id == int(kb_id))
            .order_by(RagDocument.create_time.desc(), RagDocument.id.desc())
            .limit(100)
        )
    ).scalars().all()
    if doc_ids:
        wanted = {int(x) for x in doc_ids}
        docs = [d for d in docs if int(d.id) in wanted]
    if not docs:
        raise ValueError("当前资料夹没有可抽取的资料")

    existing_entities = (
        await db.execute(
            select(RagGraphEntity).where(
                RagGraphEntity.user_id == int(user_id),
                RagGraphEntity.kb_id == int(kb_id),
            )
        )
    ).scalars().all()
    entity_by_norm = {_canonical_key(e.name): e for e in existing_entities}
    built_doc_ids = {
        int(doc_id)
        for entity in existing_entities
        for doc_id in (entity.doc_ids or [])
        if str(doc_id).isdigit()
    }

    processed_docs = 0
    extracted_entities = 0
    extracted_relations = 0
    errors: List[Dict[str, Any]] = []
    for doc in docs:
        if not force and int(doc.id) in built_doc_ids:
            continue
        chunks = await _document_chunks(db, doc)
        if not chunks:
            continue
        try:
            entities, relations, _ = await _extract_doc(db, user_id, doc, chunks)
        except Exception as exc:  # noqa: BLE001 - 单文档失败不拖垮整个资料夹
            errors.append({"docId": int(doc.id), "fileName": doc.file_name, "error": str(exc)[:300]})
            continue

        doc_entity_map: Dict[str, RagGraphEntity] = {}
        for item in entities:
            norm = _norm_name(item["name"])
            key = _canonical_key(item["name"])
            row = entity_by_norm.get(key)
            if row is None:
                row = RagGraphEntity(
                    user_id=int(user_id),
                    kb_id=int(kb_id),
                    name=item["name"],
                    normalized_name=norm,
                    type=item["type"],
                    description=item["description"],
                    doc_ids=[int(doc.id)],
                    chunk_ids=list(item["chunk_ids"]),
                    mention_count=1,
                )
                db.add(row)
                await db.flush()
                entity_by_norm[key] = row
            else:
                if not row.description and item["description"]:
                    row.description = item["description"]
                if len(norm) < len(_norm_name(row.name)):
                    row.name = item["name"]
                row.doc_ids = _merge_unique(row.doc_ids, [int(doc.id)])
                row.chunk_ids = _merge_unique(row.chunk_ids, item["chunk_ids"])
                row.mention_count = int(row.mention_count or 0) + 1
                row.update_time = datetime.now()
            doc_entity_map[norm] = row
            doc_entity_map[key] = row

        for item in relations:
            source = doc_entity_map.get(_norm_name(item["source"]))
            target = doc_entity_map.get(_norm_name(item["target"]))
            if not source or not target:
                continue
            relation = (
                await db.execute(
                    select(RagGraphRelation).where(
                        RagGraphRelation.user_id == int(user_id),
                        RagGraphRelation.kb_id == int(kb_id),
                        RagGraphRelation.source_id == int(source.id),
                        RagGraphRelation.target_id == int(target.id),
                        RagGraphRelation.relation_type == item["type"],
                    )
                )
            ).scalars().first()
            if relation is None:
                relation = RagGraphRelation(
                    user_id=int(user_id),
                    kb_id=int(kb_id),
                    source_id=int(source.id),
                    target_id=int(target.id),
                    relation_type=item["type"],
                    description=item["description"],
                    strength=int(item["strength"]),
                    doc_ids=[int(doc.id)],
                    chunk_ids=list(item["chunk_ids"]),
                )
                db.add(relation)
            else:
                relation.description = relation.description or item["description"]
                relation.strength = max(int(relation.strength or 5), int(item["strength"]))
                relation.doc_ids = _merge_unique(relation.doc_ids, [int(doc.id)])
                relation.chunk_ids = _merge_unique(relation.chunk_ids, item["chunk_ids"])
                relation.update_time = datetime.now()
            extracted_relations += 1
        extracted_entities += len(entities)
        processed_docs += 1
        await db.flush()

    await db.commit()
    return {
        "processedDocs": processed_docs,
        "entities": extracted_entities,
        "relations": extracted_relations,
        "errors": errors,
        "skippedDocs": len(docs) - processed_docs - len(errors),
    }


async def list_graph(
    db: AsyncSession,
    user_id: int,
    *,
    kb_id: Optional[int] = None,
    q: str = "",
    entity_types: Optional[List[str]] = None,
    min_strength: int = 0,
) -> Dict[str, Any]:
    query = select(RagGraphEntity).where(RagGraphEntity.user_id == int(user_id))
    if kb_id is not None:
        query = query.where(RagGraphEntity.kb_id == int(kb_id))
    if entity_types:
        query = query.where(RagGraphEntity.type.in_(entity_types))
    entities = (await db.execute(query.order_by(RagGraphEntity.id.asc()))).scalars().all()
    # 图谱永远只展示当前资料夹仍存在的文档实体：用户删除资料后，旧实体
    # 不会继续挂在图上，也不会被误认为新资料夹的内容。
    if kb_id is not None:
        valid_doc_ids = {
            int(x)
            for x in (
                await db.execute(
                    select(RagDocument.id).where(
                        RagDocument.user_id == int(user_id),
                        RagDocument.kb_id == int(kb_id),
                    )
                )
            ).scalars().all()
        }
        entities = [
            entity
            for entity in entities
            if any(int(doc_id) in valid_doc_ids for doc_id in (entity.doc_ids or []))
        ]
    entity_by_id = {int(e.id): e for e in entities}

    relation_rows = (
        await db.execute(
            select(RagGraphRelation).where(
                RagGraphRelation.user_id == int(user_id),
                RagGraphRelation.kb_id.in_([int(x) for x in ({e.kb_id for e in entities} or {0})]),
            )
        )
    ).scalars().all()
    degree: Dict[int, int] = {int(e.id): 0 for e in entities}
    relations: List[Dict[str, Any]] = []
    for relation in relation_rows:
        source = entity_by_id.get(int(relation.source_id))
        target = entity_by_id.get(int(relation.target_id))
        if not source or not target:
            continue
        if int(relation.strength or 0) < int(min_strength or 0):
            continue
        degree[source.id] = degree.get(source.id, 0) + 1
        degree[target.id] = degree.get(target.id, 0) + 1
        relations.append(
            {
                "id": int(relation.id),
                "source": str(source.id),
                "target": str(target.id),
                "type": relation.relation_type,
                "description": relation.description or "",
                "strength": int(relation.strength or 5),
                "docIds": relation.doc_ids or [],
                "chunkIds": relation.chunk_ids or [],
            }
        )

    keyword = str(q or "").strip().lower()
    nodes = []
    for entity in entities:
        if keyword:
            haystack = f"{entity.name} {entity.description or ''}".lower()
            if keyword not in haystack:
                continue
        nodes.append(
            {
                "id": str(entity.id),
                "name": entity.name,
                "type": entity.type,
                "description": entity.description or "",
                "mentionCount": int(entity.mention_count or 1),
                "degree": degree.get(int(entity.id), 0),
                "docIds": entity.doc_ids or [],
                "chunkIds": entity.chunk_ids or [],
            }
        )
    visible_ids = {int(n["id"]) for n in nodes}
    relations = [r for r in relations if int(r["source"]) in visible_ids and int(r["target"]) in visible_ids]
    type_counts: Dict[str, int] = {}
    for node in nodes:
        type_counts[node["type"]] = type_counts.get(node["type"], 0) + 1
    return {
        "nodes": nodes,
        "edges": relations,
        "stats": {
            "entityCount": len(nodes),
            "relationCount": len(relations),
            "docCount": len({doc_id for node in nodes for doc_id in (node.get("docIds") or [])}),
            "typeCounts": type_counts,
        },
    }


async def get_entity_detail(db: AsyncSession, user_id: int, entity_id: int) -> Dict[str, Any]:
    entity = (
        await db.execute(
            select(RagGraphEntity).where(
                RagGraphEntity.id == int(entity_id),
                RagGraphEntity.user_id == int(user_id),
            )
        )
    ).scalar_one_or_none()
    if not entity:
        raise ValueError("实体不存在或无权访问")
    relations = (
        await db.execute(
            select(RagGraphRelation).where(
                RagGraphRelation.user_id == int(user_id),
                or_(
                    RagGraphRelation.source_id == int(entity_id),
                    RagGraphRelation.target_id == int(entity_id),
                ),
            )
        )
    ).scalars().all()
    neighbor_ids = set()
    for relation in relations:
        neighbor_ids.add(int(relation.source_id))
        neighbor_ids.add(int(relation.target_id))
    neighbor_ids.discard(int(entity_id))
    neighbors = (
        await db.execute(select(RagGraphEntity).where(RagGraphEntity.id.in_(neighbor_ids or {0})))
    ).scalars().all()
    by_id = {int(e.id): e for e in neighbors}
    neighbor_items = []
    for relation in relations:
        is_source = int(relation.source_id) == int(entity.id)
        other = by_id.get(int(relation.target_id if is_source else relation.source_id))
        if not other:
            continue
        neighbor_items.append(
            {
                "entityId": int(other.id),
                "name": other.name,
                "type": other.type,
                "relationType": relation.relation_type,
                "description": relation.description or "",
                "strength": int(relation.strength or 5),
                "direction": "out" if is_source else "in",
            }
        )
    chunk_ids = [int(x) for x in (entity.chunk_ids or []) if str(x).isdigit()]
    chunks = (
        await db.execute(
            select(RagDocumentChunk).where(RagDocumentChunk.id.in_(chunk_ids or [0])).limit(12)
        )
    ).scalars().all()
    doc_ids = [int(x) for x in (entity.doc_ids or []) if str(x).isdigit()]
    docs = (
        await db.execute(select(RagDocument).where(RagDocument.id.in_(doc_ids or [0])))
    ).scalars().all()
    doc_names = {int(d.id): d.file_name for d in docs}
    chunk_items = [
        {
            "chunkId": int(chunk.id),
            "docId": int(chunk.doc_id),
            "fileName": doc_names.get(int(chunk.doc_id), "资料"),
            "chunkIndex": int(chunk.chunk_index or 0),
            "excerpt": _clean(chunk.content, 320),
        }
        for chunk in chunks
    ]
    return {
        "entity": {
            "id": str(entity.id),
            "name": entity.name,
            "type": entity.type,
            "description": entity.description or "",
            "mentionCount": int(entity.mention_count or 1),
            "docIds": entity.doc_ids or [],
            "chunkIds": entity.chunk_ids or [],
        },
        "neighbors": neighbor_items,
        "chunks": chunk_items,
    }


async def expand_query_chunks(
    db: AsyncSession,
    user_id: int,
    kb_ids: List[int],
    query: str,
    *,
    top_k: int = 5,
    max_hops: int = 2,
) -> List[ChunkHit]:
    """实体识别 → 图邻居扩展 → 来源 chunk。

    这是 GraphRAG 的“图谱召回”一路，不替代向量/关键词：
      · 先按实体名是否出现在问题里做实体识别；
      · 沿关系做 1~2 跳邻居扩展，收集邻居实体的来源 chunk；
      · 返回 ChunkHit，交给 hybrid_search 的 RRF 与另外两路融合。
    """
    if not kb_ids or not (query or "").strip():
        return []

    valid_doc_ids = {
        int(x)
        for x in (
            await db.execute(
                select(RagDocument.id).where(
                    RagDocument.user_id == int(user_id),
                    RagDocument.kb_id.in_([int(x) for x in kb_ids]),
                    RagDocument.disabled == 0,
                )
            )
        ).scalars().all()
    }
    entities = (
        await db.execute(
            select(RagGraphEntity).where(
                RagGraphEntity.user_id == int(user_id),
                RagGraphEntity.kb_id.in_([int(x) for x in kb_ids]),
            )
        )
    ).scalars().all()
    entities = [
        entity
        for entity in entities
        if any(int(doc_id) in valid_doc_ids for doc_id in (entity.doc_ids or []))
    ]
    if not entities:
        return []
    by_id = {int(entity.id): entity for entity in entities}
    normalized_query = _norm_name(query)
    matched = [
        entity
        for entity in entities
        if len(str(entity.normalized_name or "")) >= 2
        and str(entity.normalized_name) in normalized_query
    ]
    if not matched:
        return []

    relations = (
        await db.execute(
            select(RagGraphRelation).where(
                RagGraphRelation.user_id == int(user_id),
                RagGraphRelation.kb_id.in_([int(x) for x in kb_ids]),
            )
        )
    ).scalars().all()
    adjacency: Dict[int, List[Tuple[int, RagGraphRelation]]] = {}
    for relation in relations:
        source_id, target_id = int(relation.source_id), int(relation.target_id)
        if source_id not in by_id or target_id not in by_id:
            continue
        adjacency.setdefault(source_id, []).append((target_id, relation))
        adjacency.setdefault(target_id, []).append((source_id, relation))

    selected = {int(entity.id) for entity in matched}
    frontier = set(selected)
    relation_results: List[Tuple[int, RagGraphRelation]] = []
    for _ in range(max(1, int(max_hops))):
        next_frontier: set[int] = set()
        for entity_id in frontier:
            for neighbor_id, relation in adjacency.get(entity_id, []):
                if neighbor_id not in selected:
                    next_frontier.add(neighbor_id)
                relation_results.append((entity_id, relation))
        selected |= next_frontier
        frontier = next_frontier
        if not frontier:
            break

    # 关系 evidence 优先，其次是被命中实体自身的 chunk；只取当前有效版本。
    chunk_ids: List[int] = []
    for _, relation in sorted(relation_results, key=lambda item: int(item[1].strength or 0), reverse=True):
        for chunk_id in relation.chunk_ids or []:
            value = int(chunk_id)
            if value > 0 and value not in chunk_ids:
                chunk_ids.append(value)
    for entity_id in selected:
        entity = by_id.get(entity_id)
        for chunk_id in (entity.chunk_ids if entity else []) or []:
            value = int(chunk_id)
            if value > 0 and value not in chunk_ids:
                chunk_ids.append(value)
    if not chunk_ids:
        return []

    rows = (
        await db.execute(
            select(RagDocumentChunk, RagDocument.file_name)
            .join(RagDocument, RagDocument.id == RagDocumentChunk.doc_id)
            .where(
                RagDocumentChunk.id.in_(chunk_ids[: max(top_k * 4, 20)]),
                RagDocumentChunk.kb_id.in_([int(x) for x in kb_ids]),
                RagDocumentChunk.index_version == RagDocument.index_version,
                RagDocument.status == DOC_VECTORIZED,
                RagDocument.disabled == 0,
            )
        )
    ).all()
    order = {chunk_id: index for index, chunk_id in enumerate(chunk_ids)}
    rows = sorted(rows, key=lambda row: order.get(int(row[0].id), 9999))
    hits: List[ChunkHit] = []
    for chunk, doc_name in rows:
        hits.append(
            ChunkHit(
                chunk_id=int(chunk.id),
                doc_id=int(chunk.doc_id),
                kb_id=int(chunk.kb_id),
                chunk_index=int(chunk.chunk_index or 0),
                content=str(chunk.content or ""),
                doc_name=doc_name,
                graph_hit=True,
            )
        )
        if len(hits) >= max(top_k, 1) * 2:
            break
    return hits


__all__ = [
    "ENTITY_TYPES",
    "RELATION_TYPES",
    "build_graph",
    "list_graph",
    "get_entity_detail",
    "expand_query_chunks",
]
