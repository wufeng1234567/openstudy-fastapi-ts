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
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_graph import RagGraphEntity, RagGraphRelation
from app.models.rag import DOC_VECTORIZED, RagDocument, RagDocumentChunk
from app.models.wiki import RagWikiPage, RagWikiPageLink
from app.services.ai.base_client import ChatMessage, TextBlock
from app.services.ai.db_config import chat_with_config
from app.services.rag.hybrid_search import ChunkHit
from app.services.rag.wiki_merge_service import apply_source_to_page

ENTITY_TYPES = [
    "概念",
    "定理/公式",
    "方法",
    "人物",
    "机构",
    "事件",
    "作品",
    "术语",
    "变量/符号",
    "其他",
]
RELATION_TYPES = [
    "包含",
    "属于",
    "定义",
    "推导",
    "应用",
    "前置",
    "对比",
    "相关",
    "产生",
    "属于领域",
    "组成",
    "影响",
]
MAX_ENTITIES_PER_DOC = 240
MAX_RELATIONS_PER_DOC = 320
MAX_CHUNKS_PER_DOC = 60
MAX_CHUNKS_PER_BATCH = 8
MAX_ENTITIES_PER_BATCH = 120
MAX_RELATIONS_PER_BATCH = 160


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


def _prompt(
    doc_name: str,
    context: str,
    *,
    batch_index: int = 1,
    batch_total: int = 1,
) -> str:
    """首次抽取提示词：目标是把资料拆成可成页的知识网络，而不是只摘几个关键词。"""
    return (
        "你是学习资料的知识图谱抽取器。目标：把一份资料拆成**可成页、可复习、可互相跳转**的"
        "知识网络，尽量覆盖这一批次里的所有知识点，不要只抽开头几个词。\n"
        "只输出一个 JSON 对象，不要 Markdown，不要解释。\n\n"
        "实体粒度（默认 exhaustive 全量模式）：\n"
        "- 概念/术语/定理/公式/方法：能被单独解释、能出题、能复习的知识点；\n"
        "- 人物/机构/事件/作品：资料里明确出现且值得单独成页的对象；\n"
        "- 变量/符号：有明确含义、反复出现的数学符号；\n"
        "- 工具、软件、命令、路径、缓存目录、系统组件、版本、设置项、指标、操作步骤，"
        "只要能单独解释或后续复习，都应作为实体；例如 Rust、Cargo、WSL、Docker Desktop、"
        "Windows Update、DISM、TEMP、WinSxS、Android SDK、Gradle 都应被识别，不要只抽章节标题；\n"
        "- 一个普通技术资料通常应有 30-60 个实体，内容更丰富时可以有 80 个以上；"
        "不要因为实体多而主动省略，但必须保持名称来自资料且可被正文检索到；\n"
        "- 不要把整段话、章节标题、泛化词（如“内容”“问题”“资料”）当成实体。\n\n"
        "实体类型只能从以下列表选：'概念','定理/公式','方法','人物','机构','事件','作品','术语','变量/符号','其他'。\n"
        "实体字段：name=资料中的标准名称；type=类型；description=用资料原话压缩成一句解释；"
        "aliases=资料里明确出现过的同义名/缩写（没有就空数组）。\n"
        "关系必须是资料中明确出现的，不要靠常识补关系；source/target 必须是同一份 JSON 里的实体名。\n"
        "关系类型优先选最具体的一种：'属于','定义','推导','应用','前置','对比','产生','属于领域','组成','影响'；"
        "只有真正的整体—部分结构才用'包含'，不要把每一条关系都写成'包含'。\n"
        "输出格式（示例只示意字段，不要照抄示例内容）：\n"
        '{"entities":[{"name":"实体名","type":"概念","description":"资料中的简短解释","aliases":["同义名"]}],'
        '"relations":[{"source":"实体名1","target":"实体名2","type":"前置","description":"关系的原文依据","strength":8},'
        '{"source":"实体名1","target":"实体名3","type":"包含","description":"整体与部分关系","strength":6}]}\n'
        "strength 取值 1-10，越直接越强。若本批没有实体/关系，返回空数组。\n"
        f"当前是第 {batch_index}/{batch_total} 批，只处理本批片段，不要重复其他批次的内容。\n\n"
        f"资料名：{doc_name}\n资料片段：\n{context}"
    )


def _count_mentions(name: str, chunks: Sequence[RagDocumentChunk]) -> int:
    """统计实体名在正文中的出现次数，用于图节点大小，不做模糊同义词合并。"""
    needle = _norm_name(name)
    if not needle:
        return 1
    total = 0
    for chunk in chunks:
        total += _norm_name(chunk.content).count(needle)
    return max(1, total)


async def _document_chunks(db: AsyncSession, doc: RagDocument) -> List[RagDocumentChunk]:
    """取文档分块；超过上限时按全文均匀抽样，避免只读开头几章。"""
    rows = (
        await db.execute(
            select(RagDocumentChunk)
            .where(
                RagDocumentChunk.doc_id == int(doc.id),
                RagDocumentChunk.index_version == int(getattr(doc, "index_version", 1) or 1),
            )
            .order_by(RagDocumentChunk.chunk_index.asc())
        )
    ).scalars().all()
    if rows:
        if len(rows) > MAX_CHUNKS_PER_DOC:
            step = len(rows) / float(MAX_CHUNKS_PER_DOC)
            indexes = sorted({min(len(rows) - 1, int(i * step)) for i in range(MAX_CHUNKS_PER_DOC)})
            rows = [rows[index] for index in indexes]
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


async def _extract_batch(
    db: AsyncSession,
    user_id: int,
    doc: RagDocument,
    chunks: Sequence[RagDocumentChunk],
    *,
    batch_index: int,
    batch_total: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    context = "\n\n".join(
        f"[片段 {int(c.chunk_index) + 1}] {str(c.content or '')[:1400]}"
        for c in chunks
        if str(c.content or "").strip()
    )
    if not context.strip():
        return [], []
    messages = [
        ChatMessage(role="system", content="你只输出严格 JSON，不输出客套话或 Markdown 代码围栏。"),
        ChatMessage(
            role="user",
            content=[
                TextBlock(
                    type="text",
                    text=_prompt(
                        doc.file_name or "未命名资料",
                        context,
                        batch_index=batch_index,
                        batch_total=batch_total,
                    ),
                )
            ],
        ),
    ]
    response = await chat_with_config(
        db,
        messages,
        temperature=0.15,
        max_tokens=6000,
        user_id=int(user_id),
    )
    payload = _parse_json_payload(response.content or "")
    raw_entities = payload.get("entities") or payload.get("nodes") or []
    raw_concepts = payload.get("concepts") or []
    if isinstance(raw_concepts, list):
        for concept in raw_concepts:
            if isinstance(concept, dict):
                item = dict(concept)
                item.setdefault("type", "概念")
                raw_entities.append(item)
    raw_relations = payload.get("relations") or payload.get("edges") or []
    return (
        [item for item in raw_entities if isinstance(item, dict)][:MAX_ENTITIES_PER_BATCH],
        [item for item in raw_relations if isinstance(item, dict)][:MAX_RELATIONS_PER_BATCH],
    )


async def _extract_doc(
    db: AsyncSession,
    user_id: int,
    doc: RagDocument,
    chunks: List[RagDocumentChunk],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """按批抽取一篇文档，再合并实体/关系，避免长文档只读前 12 个 chunk。"""
    if not chunks:
        return [], [], []
    batch_total = max(1, (len(chunks) + MAX_CHUNKS_PER_BATCH - 1) // MAX_CHUNKS_PER_BATCH)
    raw_entities: List[Dict[str, Any]] = []
    raw_relations: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for start in range(0, len(chunks), MAX_CHUNKS_PER_BATCH):
        batch = chunks[start : start + MAX_CHUNKS_PER_BATCH]
        batch_index = start // MAX_CHUNKS_PER_BATCH + 1
        try:
            entities, relations = await _extract_batch(
                db,
                int(user_id),
                doc,
                batch,
                batch_index=batch_index,
                batch_total=batch_total,
            )
            raw_entities.extend(entities)
            raw_relations.extend(relations)
        except Exception as exc:  # noqa: BLE001 - 单批失败不丢其他批次
            errors.append(
                {
                    "batch": batch_index,
                    "error": str(exc)[:300],
                    "chunkIndexes": [int(c.chunk_index) for c in batch],
                }
            )

    # 合并同一篇文档里跨批次的实体；只用 name/canonical key 做名称级合并。
    entity_by_key: Dict[str, Dict[str, Any]] = {}
    for item in raw_entities:
        name = _clean(item.get("name") or item.get("title"), 120)
        if not name:
            continue
        key = _canonical_key(name)
        kind = _clean(item.get("type"), 30) or "概念"
        if kind not in ENTITY_TYPES:
            kind = "概念"
        aliases = []
        raw_aliases = item.get("aliases") or item.get("alias") or []
        if isinstance(raw_aliases, str):
            raw_aliases = [raw_aliases]
        if isinstance(raw_aliases, list):
            for alias in raw_aliases:
                alias = _clean(alias, 80)
                if alias and alias != name and alias not in aliases:
                    aliases.append(alias)
        row = entity_by_key.get(key)
        if row is None:
            entity_by_key[key] = {
                "name": name,
                "type": kind,
                "description": _clean(item.get("description"), 800),
                "aliases": aliases,
                "doc_id": int(doc.id),
                "chunk_ids": _matching_chunk_ids(name, chunks),
                "mention_count": _count_mentions(name, chunks),
            }
        else:
            if len(str(item.get("description") or "")) > len(str(row.get("description") or "")):
                row["description"] = _clean(item.get("description"), 800)
            row["aliases"] = list(dict.fromkeys([*(row.get("aliases") or []), *aliases]))[:8]
            row["chunk_ids"] = list(
                dict.fromkeys([*(row.get("chunk_ids") or []), *_matching_chunk_ids(name, chunks)])
            )
            row["mention_count"] = int(row.get("mention_count") or 1) + _count_mentions(name, chunks)

    entities = list(entity_by_key.values())[:MAX_ENTITIES_PER_DOC]
    names: Dict[str, Dict[str, Any]] = {}
    for entity in entities:
        names[_norm_name(entity["name"])] = entity
        for alias in entity.get("aliases") or []:
            names.setdefault(_norm_name(alias), entity)

    relations: List[Dict[str, Any]] = []
    for item in raw_relations:
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
    return entities, relations, errors


def _merge_unique(existing: Optional[list], new_values: Iterable[Any]) -> list:
    out = list(existing or [])
    for value in new_values:
        if value not in out:
            out.append(value)
    return out


def _entity_merge_keys(row: RagGraphEntity) -> set[str]:
    """实体归一键：标准名、已有别名、解释性后缀都参与，但按类型隔离。"""
    entity_type = str(row.type or "").strip()
    keys: set[str] = set()
    candidates = [row.name, *(row.aliases or [])]
    for value in candidates:
        key = _canonical_key(value)
        if len(key) >= 2:
            keys.add(f"{entity_type}|{key}")
    return keys


def _connected_entity_groups(rows: Sequence[RagGraphEntity]) -> List[List[RagGraphEntity]]:
    """并查集：通过共享名称/别名把同一类型的实体连成组。"""
    by_id = {int(row.id): row for row in rows}
    parent = {entity_id: entity_id for entity_id in by_id}

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    key_owner: Dict[str, int] = {}
    for row in rows:
        entity_id = int(row.id)
        for key in _entity_merge_keys(row):
            owner = key_owner.get(key)
            if owner is None:
                key_owner[key] = entity_id
            else:
                union(owner, entity_id)
    grouped: Dict[int, List[RagGraphEntity]] = {}
    for entity_id, row in by_id.items():
        grouped.setdefault(find(entity_id), []).append(row)
    return [group for group in grouped.values() if len(group) > 1]


async def merge_duplicate_entities(db: AsyncSession, user_id: int, kb_id: int) -> int:
    """合并历史数据里的同义实体（如「智能体」与「智能体定义」）。

    合并时同时迁移关系的 source/target，若迁移后与已有关系重复，则合并
    chunk_ids/strength 后删除重复关系，保证不会出现悬空边。

    别名归并只按「同类型」进行，避免把「模型（机器学习）」和「模型（思维）」误合并。
    同时把主题页 `entity_ids` 中的旧实体 id 替换为 keeper，避免页面图出现两个同名节点。
    """
    rows = (
        await db.execute(
            select(RagGraphEntity).where(
                RagGraphEntity.user_id == int(user_id),
                RagGraphEntity.kb_id == int(kb_id),
            )
        )
    ).scalars().all()
    groups = _connected_entity_groups(rows)
    merged_count = 0
    pages = (
        await db.execute(
            select(RagWikiPage).where(
                RagWikiPage.user_id == int(user_id),
                RagWikiPage.kb_id == int(kb_id),
            )
        )
    ).scalars().all()
    pages_by_entity: Dict[int, RagWikiPage] = {}
    for page in pages:
        for entity_id in page.entity_ids or []:
            try:
                pages_by_entity[int(entity_id)] = page
            except (TypeError, ValueError):
                continue
    for group in groups:
        group.sort(key=lambda item: (len(_norm_name(item.name)), -int(item.mention_count or 0)))
        keeper = group[0]
        for duplicate in group[1:]:
            if int(duplicate.id) == int(keeper.id):
                continue
            keeper.doc_ids = _merge_unique(keeper.doc_ids, duplicate.doc_ids or [])
            keeper.chunk_ids = _merge_unique(keeper.chunk_ids, duplicate.chunk_ids or [])
            keeper.aliases = _merge_unique(
                keeper.aliases,
                [duplicate.name, *(duplicate.aliases or [])],
            )
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
            # 迁移主题页上的实体 id；已存在的同一主题页只保留 keeper。
            for page in pages:
                entity_ids = [int(item) for item in (page.entity_ids or []) if str(item).isdigit()]
                if int(duplicate.id) not in entity_ids:
                    continue
                entity_ids = [int(keeper.id) if value == int(duplicate.id) else value for value in entity_ids]
                page.entity_ids = sorted(set(entity_ids))
            duplicate_page = pages_by_entity.get(int(duplicate.id))
            keeper_page = pages_by_entity.get(int(keeper.id))
            if (
                duplicate_page
                and keeper_page
                and int(duplicate_page.id) != int(keeper_page.id)
                and str(keeper_page.generated_by or "") not in {"manual", "agent"}
            ):
                meta = duplicate_page.generation_meta or {}
                sources = meta.get("sources") if isinstance(meta.get("sources"), list) else []
                if not sources and meta.get("sourceType"):
                    sources = [
                        {
                            "sourceType": meta.get("sourceType"),
                            "sourceId": meta.get("sourceId") or 0,
                            "sourceName": meta.get("sourceName") or "",
                        }
                    ]
                if not sources:
                    sources = [{"sourceType": "", "sourceId": 0, "sourceName": ""}]
                for source in sources:
                    apply_source_to_page(
                        keeper_page,
                        title=str(duplicate_page.title or keeper_page.title),
                        page_type=str(duplicate_page.page_type or keeper_page.page_type or "concept"),
                        summary=str(duplicate_page.summary or ""),
                        sections=list(duplicate_page.sections or []),
                        source_refs=list(duplicate_page.source_refs or []),
                        source_chunk_ids=list(duplicate_page.source_chunk_ids or []),
                        entity_ids=[int(keeper.id)],
                        source_type=str(source.get("sourceType") or ""),
                        source_id=int(source.get("sourceId") or 0),
                        source_name=str(source.get("sourceName") or ""),
                    )
                duplicate_page.status = "merged"
                duplicate_page.merged_into_page_id = int(keeper_page.id)
                duplicate_page.update_time = datetime.now()
                links = (
                    await db.execute(
                        select(RagWikiPageLink).where(
                            RagWikiPageLink.user_id == int(user_id),
                            RagWikiPageLink.kb_id == int(kb_id),
                            or_(
                                RagWikiPageLink.from_page_id == int(duplicate_page.id),
                                RagWikiPageLink.to_page_id == int(duplicate_page.id),
                            ),
                        )
                    )
                ).scalars().all()
                for link in links:
                    if int(link.from_page_id) == int(duplicate_page.id):
                        link.from_page_id = int(keeper_page.id)
                    if int(link.to_page_id) == int(duplicate_page.id):
                        link.to_page_id = int(keeper_page.id)
                pages_by_entity.pop(int(duplicate.id), None)
                pages_by_entity[int(keeper.id)] = keeper_page
            elif duplicate_page:
                pages_by_entity.pop(int(duplicate.id), None)
                pages_by_entity[int(keeper.id)] = duplicate_page
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
            .where(
                RagDocument.user_id == int(user_id),
                RagDocument.kb_id == int(kb_id),
                RagDocument.disabled == 0,
            )
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
            entities, relations, batch_errors = await _extract_doc(db, user_id, doc, chunks)
            for batch_error in batch_errors:
                errors.append(
                    {
                        "docId": int(doc.id),
                        "fileName": doc.file_name,
                        "batch": batch_error.get("batch"),
                        "error": batch_error.get("error") or "本批抽取失败",
                    }
                )
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
                    aliases=list(item.get("aliases") or []),
                    doc_ids=[int(doc.id)],
                    chunk_ids=list(item["chunk_ids"]),
                    mention_count=max(1, int(item.get("mention_count") or 1)),
                )
                db.add(row)
                await db.flush()
                entity_by_norm[key] = row
            else:
                if item["description"] and len(str(item["description"])) > len(str(row.description or "")):
                    row.description = item["description"]
                if len(norm) < len(_norm_name(row.name)):
                    row.name = item["name"]
                row.aliases = _merge_unique(row.aliases, item.get("aliases") or [])
                row.doc_ids = _merge_unique(row.doc_ids, [int(doc.id)])
                row.chunk_ids = _merge_unique(row.chunk_ids, item["chunk_ids"])
                row.mention_count = int(row.mention_count or 0) + max(1, int(item.get("mention_count") or 1))
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
        "skippedDocs": max(0, len(docs) - processed_docs - len({int(e["docId"]) for e in errors if e.get("docId")})),
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
                # GraphEdge 契约字段：与 type 保持同义，不改变既有 API。
                "kind": relation.relation_type,
                "label": relation.relation_type,
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
                # GraphNode 契约字段：与既有 name/type 保持同义。
                "kind": entity.type,
                "title": entity.name,
                "description": entity.description or "",
                "aliases": entity.aliases or [],
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
            "aliases": entity.aliases or [],
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
