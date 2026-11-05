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
from app.models.rag import RagDocument, RagDocumentChunk
from app.services.ai.base_client import ChatMessage, TextBlock
from app.services.ai.db_config import chat_with_config

ENTITY_TYPES = ["概念", "定理/公式", "方法", "人物", "机构", "事件", "作品", "其他"]
RELATION_TYPES = ["包含", "属于", "定义", "推导", "应用", "前置", "对比", "相关", "产生", "属于领域"]
MAX_ENTITIES_PER_DOC = 40
MAX_RELATIONS_PER_DOC = 60
MAX_CHUNKS_PER_DOC = 8


def _norm_name(value: Any) -> str:
    name = re.sub(r"[\s\u3000]+", "", str(value or "").strip())
    name = name.strip("《》\"'“”‘’（）()[]【】")
    return name.lower()


def _clean(value: Any, limit: int = 400) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


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
        "输出格式：\n"
        '{"entities":[{"name":"实体名","type":"概念","description":"资料中的简短解释"}],'
        '"relations":[{"source":"实体名1","target":"实体名2","type":"包含","description":"关系的原文依据","strength":8}]}\n'
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
                "chunk_ids": [int(c.id) for c in chunks if getattr(c, "id", 0)],
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
        relations.append(
            {
                "source": source["name"],
                "target": target["name"],
                "type": relation_type,
                "description": _clean(item.get("description"), 800),
                "strength": strength,
                "doc_id": int(doc.id),
                "chunk_ids": [int(c.id) for c in chunks if getattr(c, "id", 0)],
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
    entity_by_norm = {str(e.normalized_name): e for e in existing_entities}
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
            row = entity_by_norm.get(norm)
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
                entity_by_norm[norm] = row
            else:
                if not row.description and item["description"]:
                    row.description = item["description"]
                row.doc_ids = _merge_unique(row.doc_ids, [int(doc.id)])
                row.chunk_ids = _merge_unique(row.chunk_ids, item["chunk_ids"])
                row.mention_count = int(row.mention_count or 0) + 1
                row.update_time = datetime.now()
            doc_entity_map[norm] = row

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


__all__ = ["ENTITY_TYPES", "RELATION_TYPES", "build_graph", "list_graph", "get_entity_detail"]
