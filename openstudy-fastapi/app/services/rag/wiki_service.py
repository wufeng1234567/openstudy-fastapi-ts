"""知识百科（Wiki）主题页生成、页面图谱与 Wiki RAG 检索。

边界
----
- 实体关系图是底层索引；本模块把图上的实体整理成**用户能读的主题页**。
- 页面正文只使用原始资料 chunk，不拿别的 Wiki 页面做二次摘要，避免错误逐层放大。
- 每个小节都必须能落回真实 chunk；找不到来源的小节直接丢弃，不硬编。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from loguru import logger
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentReference, RagImageAsset
from app.models.knowledge_graph import RagGraphEntity, RagGraphRelation
from app.models.rag import DOC_VECTORIZED, RagDocument, RagDocumentChunk
from app.models.wiki import RagWikiChunk, RagWikiPage, RagWikiPageLink, RagWikiPageRevision
from app.services.ai.base_client import ChatMessage, TextBlock
from app.services.ai.db_config import chat_with_config
from app.services.rag.embedding import embed_texts
from app.services.rag.hybrid_search import ChunkHit
from app.services.rag.rag_write_service import get_knowledge_base, sanitize_text
from app.services.rag.tokenizer import query_tokens, tokenize

#: 每个主题页最多取多少条来源 chunk；足够形成要点，又不会撑爆模型上下文。
MAX_SOURCE_CHUNKS = 12
#: 单次接口最多生成多少页，避免一个请求把模型额度打穿。
DEFAULT_BUILD_LIMIT = 10
#: 单页最多保留多少个正文小节。
MAX_SECTIONS = 6
#: 单节正文上限（字符）。
MAX_SECTION_CHARS = 1600
#: 页面状态。
WIKI_DRAFT = "draft"
WIKI_READY = "ready"
WIKI_STALE = "stale"
WIKI_FAILED = "failed"

_SOURCE_TYPES = {"包含", "属于", "定义", "推导", "应用", "前置", "对比", "相关", "产生", "属于领域"}

#: 这些关系更像“目录/结构”，不应作为页面里最重要的“洞察”反复出现。
_GENERIC_RELATIONS = {"包含", "属于", "定义", "相关"}


def _clean(value: Any, limit: int = 4000) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return sanitize_text(text)[:limit]


def _normalize_title(value: Any) -> str:
    """页面标题归一化：只做名称级合并，不做模糊同义词合并。"""
    title = re.sub(r"[\s\u3000]+", "", str(value or "").strip())
    title = title.strip("《》\"'“”‘’（）()[]【】")
    for suffix in ("定义", "概念", "概述", "简介", "介绍", "说明"):
        if len(title) > len(suffix) + 1 and title.endswith(suffix):
            title = title[: -len(suffix)]
            break
    return title.lower()


def _display_title(value: Any) -> str:
    """展示标题去掉“定义/概念/概述”等解释性后缀，保留大小写与正文。"""
    title = re.sub(r"[\s\u3000]+", " ", str(value or "").strip())
    title = title.strip("《》\"'“”‘’（）()[]【】")
    for suffix in ("定义", "概念", "概述", "简介", "介绍", "说明"):
        if len(title) > len(suffix) + 1 and title.endswith(suffix):
            return title[: -len(suffix)].strip()
    return title


def _parse_page_payload(raw: str) -> Dict[str, Any]:
    """解析模型返回的主题页 JSON；兼容代码围栏与裸数组。"""
    text = str(raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("模型没有返回可解析的主题页 JSON")
        payload = json.loads(text[start : end + 1])
    if isinstance(payload, list):
        return {"summary": "", "sections": payload, "relatedTitles": []}
    if not isinstance(payload, dict):
        raise ValueError("主题页 JSON 不是对象")
    return payload


def _section_source_ids(section: Dict[str, Any]) -> list[int]:
    raw = (
        section.get("sourceChunkIds")
        or section.get("chunkIds")
        or section.get("source_chunk_ids")
        or section.get("sources")
        or []
    )
    if not isinstance(raw, list):
        raw = [raw]
    result: list[int] = []
    for item in raw:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value > 0 and value not in result:
            result.append(value)
    return result


def _validate_page_payload(
    payload: Dict[str, Any],
    allowed_chunk_ids: Sequence[int],
    allowed_related_titles: Sequence[str],
    fallback_summary: str,
) -> Dict[str, Any]:
    """过滤模型输出里的无效来源，保证页面只引用真实 chunk。

    原则：没有真实来源的小节宁可不要，也不把模型自造的 chunk id 写进页面。
    """
    allowed = {int(x) for x in allowed_chunk_ids if int(x) > 0}
    summary = _clean(payload.get("summary") or payload.get("description") or fallback_summary, 500)
    if not summary:
        summary = _clean(fallback_summary, 500)

    sections: list[dict] = []
    raw_sections = payload.get("sections") or payload.get("chapters") or []
    if isinstance(raw_sections, dict):
        raw_sections = [raw_sections]
    for item in raw_sections:
        if not isinstance(item, dict):
            continue
        heading = _clean(item.get("heading") or item.get("title"), 60)
        body = _clean(item.get("body") or item.get("content") or item.get("text"), MAX_SECTION_CHARS)
        if not heading or not body:
            continue
        source_ids = [cid for cid in _section_source_ids(item) if cid in allowed]
        if not source_ids:
            # 没有可核对的来源，整节不要；不能让用户以为这是资料原文。
            continue
        sections.append({"heading": heading, "body": body, "sourceChunkIds": source_ids})
        if len(sections) >= MAX_SECTIONS:
            break

    related: list[str] = []
    raw_related = payload.get("relatedTitles") or payload.get("related") or []
    allowed_names = {_normalize_title(x): _clean(x, 120) for x in allowed_related_titles if _clean(x, 120)}
    for item in raw_related if isinstance(raw_related, list) else []:
        key = _normalize_title(item)
        if key in allowed_names and allowed_names[key] not in related:
            related.append(allowed_names[key])

    return {"summary": summary, "sections": sections, "relatedTitles": related}


def _render_markdown(summary: str, sections: Sequence[Dict[str, Any]]) -> str:
    lines = [f"> {summary}", ""]
    for section in sections:
        lines.append(f"## {section['heading']}")
        lines.append("")
        lines.append(str(section.get("body") or ""))
        lines.append("")
    return "\n".join(lines).strip()


def _build_prompt(
    *,
    kb_name: str,
    entity: RagGraphEntity,
    relations: Sequence[Dict[str, Any]],
    chunks: Sequence[RagDocumentChunk],
    doc_names: Dict[int, str],
) -> str:
    context_parts = []
    for chunk in chunks:
        doc_name = doc_names.get(int(chunk.doc_id), "资料")
        context_parts.append(
            f"[chunk:{int(chunk.id)}] 资料《{doc_name}》第 {int(chunk.chunk_index) + 1} 段\n"
            f"{_clean(chunk.content, 1200)}"
        )
    context = "\n\n".join(context_parts)
    relation_lines = []
    for item in relations[:20]:
        direction = "→" if item.get("direction") == "out" else "←"
        relation_lines.append(
            f"{entity.name} {direction} {item.get('relationType', '相关')} {item.get('name', '')}"
        )
    relation_text = "\n".join(relation_lines) or "（暂时没有抽到实体关系）"

    return (
        "你是 OpenStudy 的课程知识编辑。请把给定资料整理成一篇可读的知识主题页。\n"
        "硬性要求：\n"
        "1. 只能使用下面提供的资料片段，不准使用资料之外的常识，不准编造事实、数字、引用或 chunk id。\n"
        "2. 每个 section 必须给出至少一个 sourceChunkIds，且只能从提供的 [chunk:数字] 里选。\n"
        "3. 资料不足以支撑的章节直接不写，不要写“补充证据”“据推测”等话。\n"
        "4. 不要把所有关系都罗列出来；只写对学习这个主题有帮助的内容。\n"
        "5. 输出严格 JSON，不要 Markdown 代码围栏。\n\n"
        "输出格式：\n"
        '{"summary":"一句话解释这个主题",'
        '"sections":[{"heading":"核心要点","body":"用短段落或列表写清楚",'
        '"sourceChunkIds":[123]}],'
        '"relatedTitles":["只能是相邻实体名"]}\n\n'
        f"资料夹：{kb_name}\n"
        f"主题：{entity.name}（类型：{entity.type}）\n"
        f"已有描述：{_clean(entity.description, 500) or '（无）'}\n"
        f"相邻实体：\n{relation_text}\n\n"
        f"资料片段：\n{context}"
    )


async def _load_entity_chunks(
    db: AsyncSession, user_id: int, kb_id: int, entity: RagGraphEntity
) -> list[RagDocumentChunk]:
    """获取真正包含实体名的 chunk；找不到才回退到实体历史 chunk_ids。"""
    doc_ids = [int(x) for x in (entity.doc_ids or []) if str(x).isdigit()]
    if not doc_ids:
        return []
    rows = (
        await db.execute(
            select(RagDocumentChunk)
            .join(RagDocument, RagDocument.id == RagDocumentChunk.doc_id)
            .where(
                RagDocument.user_id == int(user_id),
                RagDocument.kb_id == int(kb_id),
                RagDocument.id.in_(doc_ids),
                RagDocument.disabled == 0,
                RagDocumentChunk.index_version == RagDocument.index_version,
                RagDocumentChunk.content.ilike(f"%{entity.name}%"),
            )
            .order_by(RagDocumentChunk.chunk_index.asc())
            .limit(MAX_SOURCE_CHUNKS)
        )
    ).scalars().all()
    if rows:
        return list(rows)

    fallback_ids = [int(x) for x in (entity.chunk_ids or []) if str(x).isdigit()]
    if not fallback_ids:
        return []
    rows = (
        await db.execute(
            select(RagDocumentChunk)
            .join(RagDocument, RagDocument.id == RagDocumentChunk.doc_id)
            .where(
                RagDocumentChunk.id.in_(fallback_ids),
                RagDocument.user_id == int(user_id),
                RagDocument.kb_id == int(kb_id),
                RagDocument.disabled == 0,
                RagDocumentChunk.index_version == RagDocument.index_version,
            )
            .order_by(RagDocumentChunk.chunk_index.asc())
            .limit(MAX_SOURCE_CHUNKS)
        )
    ).scalars().all()
    return list(rows)


async def _load_relations(
    db: AsyncSession, user_id: int, kb_id: int, entity_id: int
) -> list[dict]:
    relations = (
        await db.execute(
            select(RagGraphRelation).where(
                RagGraphRelation.user_id == int(user_id),
                RagGraphRelation.kb_id == int(kb_id),
                or_(
                    RagGraphRelation.source_id == int(entity_id),
                    RagGraphRelation.target_id == int(entity_id),
                ),
            )
        )
    ).scalars().all()
    neighbor_ids = set()
    for rel in relations:
        neighbor_ids.add(int(rel.source_id))
        neighbor_ids.add(int(rel.target_id))
    neighbor_ids.discard(int(entity_id))
    neighbors = (
        await db.execute(
            select(RagGraphEntity).where(RagGraphEntity.id.in_(neighbor_ids or {0}))
        )
    ).scalars().all()
    by_id = {int(item.id): item for item in neighbors}
    result = []
    for rel in relations:
        is_source = int(rel.source_id) == int(entity_id)
        other = by_id.get(int(rel.target_id if is_source else rel.source_id))
        if not other:
            continue
        result.append(
            {
                "entityId": int(other.id),
                "name": other.name,
                "type": other.type,
                "relationType": rel.relation_type,
                "direction": "out" if is_source else "in",
                "description": rel.description or "",
                "strength": int(rel.strength or 5),
            }
        )
    # 强关系、具体关系、名称短的优先；避免把 36 条“包含”原样塞进提示词。
    result.sort(
        key=lambda item: (
            1 if item["relationType"] in _GENERIC_RELATIONS else 0,
            -int(item["strength"]),
            len(item["name"]),
        )
    )
    return result


def _source_refs(chunks: Sequence[RagDocumentChunk], doc_names: Dict[int, str]) -> list[dict]:
    refs = []
    for chunk in chunks:
        refs.append(
            {
                "docId": int(chunk.doc_id),
                "chunkId": int(chunk.id),
                "docName": doc_names.get(int(chunk.doc_id), "资料"),
                "chunkIndex": int(chunk.chunk_index),
                "quote": _clean(chunk.content, 220),
            }
        )
    return refs


async def _replace_wiki_chunks(
    db: AsyncSession, page: RagWikiPage, sections: Sequence[Dict[str, Any]]
) -> int:
    """重建页面小节向量；失败只影响 Wiki RAG，不让页面生成失败。"""
    await db.execute(delete(RagWikiChunk).where(RagWikiChunk.page_id == int(page.id)))
    texts = [
        f"{section.get('heading', '')}\n{section.get('body', '')}".strip()
        for section in sections
        if str(section.get("body") or "").strip()
    ]
    if not texts:
        return 0
    try:
        vectors = await embed_texts(texts)
    except Exception as exc:  # noqa: BLE001 - 页面本身仍可用，只缺 Wiki 检索
        logger.warning(f"[rag.wiki] 页面 {page.id} 小节向量化失败，跳过 Wiki RAG 索引: {exc}")
        return 0
    created = 0
    for index, (section, content, vector) in enumerate(zip(sections, texts, vectors)):
        if not str(content).strip():
            continue
        db.add(
            RagWikiChunk(
                user_id=int(page.user_id),
                kb_id=int(page.kb_id),
                page_id=int(page.id),
                section_index=index,
                section_title=_clean(section.get("heading"), 120),
                content=content,
                content_tokens=tokenize(content),
                embedding=vector,
                source_chunk_ids=section.get("sourceChunkIds") or [],
            )
        )
        created += 1
    return created


def _link_type_for_relation(relation_type: str) -> str:
    if relation_type == "前置":
        return "prerequisite"
    if relation_type == "对比":
        return "contrast"
    if relation_type in {"属于", "包含", "定义"}:
        return "part_of"
    return "related"


async def _rebuild_links(
    db: AsyncSession, user_id: int, kb_id: int, pages: Sequence[RagWikiPage]
) -> int:
    """从实体关系推导页面级导航边；只连接已经存在的页面。"""
    if not pages:
        return 0
    entity_to_page: dict[int, RagWikiPage] = {}
    for page in pages:
        for entity_id in page.entity_ids or []:
            try:
                entity_to_page[int(entity_id)] = page
            except (TypeError, ValueError):
                continue
    if len(entity_to_page) < 2:
        return 0
    relations = (
        await db.execute(
            select(RagGraphRelation).where(
                RagGraphRelation.user_id == int(user_id),
                RagGraphRelation.kb_id == int(kb_id),
            )
        )
    ).scalars().all()
    existing = {
        (int(row.from_page_id), int(row.to_page_id), row.link_type)
        for row in (
            await db.execute(
                select(RagWikiPageLink).where(
                    RagWikiPageLink.user_id == int(user_id),
                    RagWikiPageLink.kb_id == int(kb_id),
                )
            )
        ).scalars().all()
    }
    created = 0
    for rel in relations:
        source_page = entity_to_page.get(int(rel.source_id))
        target_page = entity_to_page.get(int(rel.target_id))
        if not source_page or not target_page or source_page.id == target_page.id:
            continue
        link_type = _link_type_for_relation(str(rel.relation_type or "相关"))
        key = (int(source_page.id), int(target_page.id), link_type)
        reverse_key = (int(target_page.id), int(source_page.id), link_type)
        if key in existing or reverse_key in existing:
            continue
        db.add(
            RagWikiPageLink(
                user_id=int(user_id),
                kb_id=int(kb_id),
                from_page_id=int(source_page.id),
                to_page_id=int(target_page.id),
                link_type=link_type,
                weight=max(1, min(10, int(rel.strength or 5))),
                source="graph",
            )
        )
        existing.add(key)
        created += 1
    return created


async def build_wiki_pages(
    db: AsyncSession,
    user_id: int,
    kb_id: int,
    *,
    force: bool = False,
    limit: int = DEFAULT_BUILD_LIMIT,
    progress_cb: Optional[Callable[[int, int, int, str], Awaitable[None]]] = None,
) -> dict:
    """把实体图整理成可读主题页。

    `force=False` 时跳过已有 ready 页面；资料变化后由 stale 标记触发重生成。
    每页只调用一次模型，任何单页失败都不拖垮整个资料夹。

    `progress_cb(done, total, failed, current_title)` 用于后台任务回写进度，
    不传时与原来的同步调用完全一致。
    """
    kb = await get_knowledge_base(db, user_id, kb_id)
    docs = (
        await db.execute(
            select(RagDocument).where(
                RagDocument.user_id == int(user_id),
                RagDocument.kb_id == int(kb_id),
                RagDocument.disabled == 0,
            )
        )
    ).scalars().all()
    if not docs:
        raise ValueError("当前资料夹没有可整理成知识百科的资料")
    doc_names = {int(doc.id): str(doc.file_name or "资料") for doc in docs}
    valid_doc_ids = set(doc_names)

    entities = (
        await db.execute(
            select(RagGraphEntity).where(
                RagGraphEntity.user_id == int(user_id),
                RagGraphEntity.kb_id == int(kb_id),
            )
        )
    ).scalars().all()
    entities = [
        entity
        for entity in entities
        if any(int(doc_id) in valid_doc_ids for doc_id in (entity.doc_ids or []) if str(doc_id).isdigit())
    ]
    if not entities:
        raise ValueError("当前资料夹还没有实体，请先抽取知识图谱")

    relations_all = (
        await db.execute(
            select(RagGraphRelation).where(
                RagGraphRelation.user_id == int(user_id),
                RagGraphRelation.kb_id == int(kb_id),
            )
        )
    ).scalars().all()
    degree: dict[int, int] = {}
    for rel in relations_all:
        degree[int(rel.source_id)] = degree.get(int(rel.source_id), 0) + 1
        degree[int(rel.target_id)] = degree.get(int(rel.target_id), 0) + 1

    existing_pages = (
        await db.execute(
            select(RagWikiPage).where(
                RagWikiPage.user_id == int(user_id),
                RagWikiPage.kb_id == int(kb_id),
            )
        )
    ).scalars().all()
    by_title = {page.normalized_title: page for page in existing_pages}
    by_entity: dict[int, RagWikiPage] = {}
    for page in existing_pages:
        for entity_id in page.entity_ids or []:
            try:
                by_entity[int(entity_id)] = page
            except (TypeError, ValueError):
                continue

    # “值得成页”的排序：提及次数 + 图上连接度；不追求给所有实体都生成薄页面。
    candidates = sorted(
        entities,
        key=lambda entity: (
            int(entity.mention_count or 1) + degree.get(int(entity.id), 0) * 2,
            int(entity.mention_count or 1),
        ),
        reverse=True,
    )

    candidates_done = 0
    pages_touched: list[RagWikiPage] = []
    errors: list[dict] = []
    progress_total = max(1, min(max(1, int(limit)), len(candidates)))
    for entity in candidates:
        if candidates_done >= max(1, int(limit)):
            break
        existing = by_entity.get(int(entity.id)) or by_title.get(_normalize_title(entity.name))
        # 用户手写过的页面不能被批量“更新知识百科”静默覆盖；保留用户内容，交给页面内
        # 的“重新整理 AI 部分”（后续版本）或人工编辑处理。
        if existing and existing.generated_by in {"manual", "agent"}:
            continue
        if existing and not force and existing.status == WIKI_READY:
            continue
        chunks = await _load_entity_chunks(db, int(user_id), int(kb_id), entity)
        if not chunks:
            continue
        relations = await _load_relations(db, int(user_id), int(kb_id), int(entity.id))
        try:
            response = await chat_with_config(
                db,
                [
                    ChatMessage(
                        role="system",
                        content="你只输出严格 JSON，不输出客套话或 Markdown 代码围栏。",
                    ),
                    ChatMessage(
                        role="user",
                        content=[
                            TextBlock(
                                type="text",
                                text=_build_prompt(
                                    kb_name=str(getattr(kb, "name", "") or "资料夹"),
                                    entity=entity,
                                    relations=relations,
                                    chunks=chunks,
                                    doc_names=doc_names,
                                ),
                            )
                        ],
                    ),
                ],
                temperature=0.2,
                max_tokens=2600,
                user_id=int(user_id),
            )
            payload = _parse_page_payload(response.content or "")
            validated = _validate_page_payload(
                payload,
                [int(chunk.id) for chunk in chunks],
                [item["name"] for item in relations],
                str(entity.description or entity.name),
            )
            if not validated["sections"]:
                raise ValueError("模型没有返回带真实来源的正文小节")
            summary = validated["summary"]
            sections = validated["sections"]
            content_md = _render_markdown(summary, sections)
            source_refs = _source_refs(chunks, doc_names)
            source_chunk_ids = []
            for section in sections:
                for chunk_id in section.get("sourceChunkIds", []):
                    if chunk_id not in source_chunk_ids:
                        source_chunk_ids.append(int(chunk_id))
            page = existing or RagWikiPage(
                user_id=int(user_id),
                kb_id=int(kb_id),
                title=_display_title(entity.name)[:255],
                normalized_title=_normalize_title(entity.name),
                page_type="topic",
            )
            if existing:
                # 快照必须在覆盖字段之前：保存旧标题/旧摘要/旧小节。
                db.add(_page_revision_snapshot(existing, "before_ai_regenerate", "agent"))
            page.title = _display_title(entity.name)[:255]
            page.page_type = "topic"
            page.summary = summary
            page.content_md = content_md
            page.sections = sections
            page.source_refs = source_refs
            page.source_doc_ids = sorted({item["docId"] for item in source_refs})
            page.source_chunk_ids = source_chunk_ids
            entity_ids = {
                int(item)
                for item in (page.entity_ids or [])
                if str(item).isdigit()
            }
            entity_ids.add(int(entity.id))
            page.entity_ids = sorted(entity_ids)
            page.status = WIKI_READY
            page.generated_by = "llm"
            page.update_time = datetime.now()
            page.generation_meta = {
                "relationCount": len(relations),
                "sourceChunkCount": len(chunks),
                "generatedAt": datetime.now().isoformat(timespec="seconds"),
            }
            if existing:
                page.version = int(page.version or 1) + 1
            else:
                db.add(page)
                await db.flush()
            await db.flush()
            await _replace_wiki_chunks(db, page, sections)
            # 每页独立提交：后面某一页失败时，前面已生成好的页面不能一起回滚。
            await db.commit()
            by_title[page.normalized_title] = page
            by_entity[int(entity.id)] = page
            pages_touched.append(page)
            candidates_done += 1
            if progress_cb is not None:
                await progress_cb(
                    len(pages_touched), progress_total, len(errors), str(page.title)
                )
        except Exception as exc:  # noqa: BLE001 - 单页失败不拖垮整个资料夹
            await db.rollback()
            # rollback 会丢掉未提交页面；已存在页面重新查询后再标 failed。
            existing = (
                await db.execute(
                    select(RagWikiPage).where(
                        RagWikiPage.user_id == int(user_id),
                        RagWikiPage.kb_id == int(kb_id),
                        RagWikiPage.normalized_title == _normalize_title(entity.name),
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.status = WIKI_FAILED
                existing.generation_meta = {
                    "error": _clean(exc, 300),
                    "failedAt": datetime.now().isoformat(timespec="seconds"),
                }
                await db.commit()
            errors.append({"entityId": int(entity.id), "name": entity.name, "error": _clean(exc, 300)})
            if progress_cb is not None:
                await progress_cb(
                    len(pages_touched), progress_total, len(errors), str(entity.name)
                )
            logger.warning(f"[rag.wiki] 实体 {entity.name} 主题页生成失败: {exc}")

    # 页面生成过程中遇到过 rollback，重新取一遍所有页面再建链接。
    all_pages = (
        await db.execute(
            select(RagWikiPage).where(
                RagWikiPage.user_id == int(user_id),
                RagWikiPage.kb_id == int(kb_id),
                RagWikiPage.status.in_([WIKI_READY, WIKI_STALE]),
            )
        )
    ).scalars().all()
    links = await _rebuild_links(db, int(user_id), int(kb_id), all_pages)
    await db.commit()
    return {
        "processed": len(pages_touched),
        "pages": len(all_pages),
        "links": links,
        "errors": errors,
        "skipped": max(0, len(candidates) - len(pages_touched) - len(errors)),
    }


async def mark_wiki_pages_stale(
    db: AsyncSession, user_id: int, kb_id: int, doc_ids: Sequence[int]
) -> int:
    """文档变化后标记受影响页面；不让旧页面继续参与 RAG。"""
    wanted = {int(x) for x in doc_ids}
    if not wanted:
        return 0
    pages = (
        await db.execute(
            select(RagWikiPage).where(
                RagWikiPage.user_id == int(user_id),
                RagWikiPage.kb_id == int(kb_id),
                RagWikiPage.status.in_([WIKI_READY, WIKI_STALE]),
            )
        )
    ).scalars().all()
    changed = 0
    for page in pages:
        source_ids = {int(x) for x in (page.source_doc_ids or []) if str(x).isdigit()}
        if source_ids & wanted and page.status != WIKI_STALE:
            page.status = WIKI_STALE
            page.update_time = datetime.now()
            changed += 1
    if changed:
        await db.commit()
    return changed


async def list_wiki_pages(
    db: AsyncSession,
    user_id: int,
    *,
    kb_id: Optional[int] = None,
    q: str = "",
    limit: int = 200,
) -> dict:
    if kb_id is not None:
        await get_knowledge_base(db, user_id, kb_id)
    stmt = select(RagWikiPage).where(RagWikiPage.user_id == int(user_id))
    if kb_id is not None:
        stmt = stmt.where(RagWikiPage.kb_id == int(kb_id))
    pages = (
        await db.execute(
            stmt.order_by(RagWikiPage.update_time.desc().nullslast(), RagWikiPage.id.desc()).limit(max(1, int(limit)))
        )
    ).scalars().all()
    keyword = str(q or "").strip().lower()
    if keyword:
        pages = [
            page
            for page in pages
            if keyword in f"{page.title} {page.summary}".lower()
        ]
    page_ids = [int(page.id) for page in pages]
    link_counts: dict[int, int] = {}
    if page_ids:
        links = (
            await db.execute(
                select(RagWikiPageLink).where(
                    RagWikiPageLink.user_id == int(user_id),
                    or_(
                        RagWikiPageLink.from_page_id.in_(page_ids),
                        RagWikiPageLink.to_page_id.in_(page_ids),
                    ),
                )
            )
        ).scalars().all()
        for link in links:
            link_counts[int(link.from_page_id)] = link_counts.get(int(link.from_page_id), 0) + 1
            link_counts[int(link.to_page_id)] = link_counts.get(int(link.to_page_id), 0) + 1
    items = []
    for page in pages:
        items.append(
            {
                "pageId": int(page.id),
                "kbId": int(page.kb_id),
                "title": page.title,
                "pageType": page.page_type,
                "summary": page.summary,
                "status": page.status,
                "version": int(page.version or 1),
                "sourceCount": len(page.source_refs or []),
                "docCount": len(page.source_doc_ids or []),
                "sectionCount": len(page.sections or []),
                "relatedCount": link_counts.get(int(page.id), 0),
                "entityIds": page.entity_ids or [],
                "generatedBy": page.generated_by or "llm",
                "updateTime": page.update_time.isoformat(sep=" ") if page.update_time else None,
            }
        )
    stats = {
        "pageCount": len(items),
        "readyCount": sum(1 for item in items if item["status"] == WIKI_READY),
        "staleCount": sum(1 for item in items if item["status"] == WIKI_STALE),
        "docCount": len({doc_id for page in pages for doc_id in (page.source_doc_ids or [])}),
    }
    return {"pages": items, "stats": stats}


async def get_wiki_page(db: AsyncSession, user_id: int, page_id: int) -> dict:
    page = (
        await db.execute(
            select(RagWikiPage).where(
                RagWikiPage.id == int(page_id),
                RagWikiPage.user_id == int(user_id),
            )
        )
    ).scalar_one_or_none()
    if not page:
        raise ValueError("知识主题页不存在或无权访问")
    related = (
        await db.execute(
            select(RagWikiPageLink).where(
                RagWikiPageLink.user_id == int(user_id),
                or_(
                    RagWikiPageLink.from_page_id == int(page.id),
                    RagWikiPageLink.to_page_id == int(page.id),
                ),
            )
        )
    ).scalars().all()
    related_ids = set()
    for link in related:
        other = int(link.to_page_id) if int(link.from_page_id) == int(page.id) else int(link.from_page_id)
        if other != int(page.id):
            related_ids.add(other)
    related_pages = (
        await db.execute(select(RagWikiPage).where(RagWikiPage.id.in_(related_ids or {0})))
    ).scalars().all()
    by_id = {int(item.id): item for item in related_pages}
    related_items = []
    for link in related:
        other_id = int(link.to_page_id) if int(link.from_page_id) == int(page.id) else int(link.from_page_id)
        other = by_id.get(other_id)
        if not other:
            continue
        related_items.append(
            {
                "pageId": int(other.id),
                "title": other.title,
                "summary": other.summary,
                "linkType": link.link_type,
                "weight": int(link.weight or 5),
                "direction": "out" if int(link.from_page_id) == int(page.id) else "in",
            }
        )
    return {
        "pageId": int(page.id),
        "kbId": int(page.kb_id),
        "title": page.title,
        "pageType": page.page_type,
        "summary": page.summary,
        "contentMd": page.content_md,
        "sections": page.sections or [],
        "sources": page.source_refs or [],
        "sourceDocIds": page.source_doc_ids or [],
        "sourceChunkIds": page.source_chunk_ids or [],
        "entityIds": page.entity_ids or [],
        "status": page.status,
        "generatedBy": page.generated_by or "llm",
        "version": int(page.version or 1),
        "updateTime": page.update_time.isoformat(sep=" ") if page.update_time else None,
        "related": related_items,
        "images": await _page_images(db, user_id, int(page.id)),
    }


def _asset_key_from_reference(ref: ContentReference) -> str:
    if ref.source_type == "document_image":
        return f"doc:{int(ref.source_id)}:{ref.source_sub_id or ''}"
    if ref.source_type == "chat_image":
        return f"chat:{int(ref.source_id)}"
    return ""


async def _page_images(db: AsyncSession, user_id: int, page_id: int) -> list[dict]:
    """主题页关联的画廊图片（统一走 content_reference，不复制原图）。"""
    rows = (
        await db.execute(
            select(ContentReference).where(
                ContentReference.user_id == int(user_id),
                ContentReference.deleted == 0,
                ContentReference.target_type == "wiki_page",
                ContentReference.target_id == int(page_id),
            )
        )
    ).scalars().all()
    if not rows:
        return []
    from app.services.rag import reference_service

    items: list[dict] = []
    for ref in rows:
        asset_key = _asset_key_from_reference(ref)
        asset = (
            await db.execute(
                select(RagImageAsset).where(
                    RagImageAsset.user_id == int(user_id),
                    RagImageAsset.asset_key == asset_key,
                )
            )
        ).scalar_one_or_none()
        try:
            enriched = await reference_service.get_reference(db, user_id, int(ref.id))
        except Exception:  # noqa: BLE001 - 单条失效引用不阻断页面
            enriched = {}
        items.append(
            {
                "referenceId": int(ref.id),
                "assetKey": asset_key,
                "url": asset.url if asset else "",
                "fileName": asset.file_name if asset else "",
                "caption": asset.caption if asset else "",
                "quote": ref.quote or "",
                "sourceType": ref.source_type,
                "sourceId": int(ref.source_id),
                "sourceSubId": ref.source_sub_id,
                "sourceTitle": ((enriched.get("source") or {}).get("title") if enriched else "") or "",
            }
        )
    return items


def _page_revision_snapshot(page: RagWikiPage, change_type: str, created_by: str) -> RagWikiPageRevision:
    return RagWikiPageRevision(
        user_id=int(page.user_id),
        kb_id=int(page.kb_id),
        page_id=int(page.id),
        version=int(page.version or 1),
        title=page.title or "",
        summary=page.summary or "",
        content_md=page.content_md or "",
        sections=page.sections or [],
        source_refs=page.source_refs or [],
        status=page.status or WIKI_READY,
        change_type=change_type,
        created_by=created_by,
    )


def _manual_sections(value: Any, allowed_chunk_ids: Optional[Sequence[int]] = None) -> list[dict]:
    """清洗用户编辑/Agent 提交的小节。

    手动编辑允许没有 chunk 来源（用户自己写的内容）；但模型传来的来源 id
    只能落在页面已知来源 chunk 里，不能让模型把任意 id 写进页面。
    """
    allowed = {int(x) for x in (allowed_chunk_ids or []) if str(x).isdigit()}
    out: list[dict] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        heading = _clean(item.get("heading") or item.get("title"), 60)
        body = _clean(item.get("body") or item.get("content") or item.get("text"), MAX_SECTION_CHARS)
        if not heading or not body:
            continue
        raw_ids = item.get("sourceChunkIds") or item.get("chunkIds") or []
        if not isinstance(raw_ids, list):
            raw_ids = []
        source_ids = []
        for chunk_id in raw_ids:
            try:
                chunk_id = int(chunk_id)
            except (TypeError, ValueError):
                continue
            if allowed and chunk_id in allowed and chunk_id not in source_ids:
                source_ids.append(chunk_id)
        out.append({"heading": heading, "body": body, "sourceChunkIds": source_ids})
        if len(out) >= MAX_SECTIONS:
            break
    return out


async def create_manual_wiki_page(
    db: AsyncSession,
    user_id: int,
    kb_id: int,
    *,
    title: str,
    summary: str = "",
    sections: Optional[Sequence[dict]] = None,
) -> dict:
    """用户/Agent 手动创建主题页（不调用模型）。"""
    await get_knowledge_base(db, user_id, kb_id)
    clean_title = _clean(title, 255)
    if not clean_title:
        raise ValueError("主题页标题不能为空")
    normalized = _normalize_title(clean_title)
    dup = (
        await db.execute(
            select(RagWikiPage).where(
                RagWikiPage.user_id == int(user_id),
                RagWikiPage.kb_id == int(kb_id),
                RagWikiPage.normalized_title == normalized,
            )
        )
    ).scalar_one_or_none()
    if dup:
        raise ValueError(f"同名主题页已存在：{dup.title}")
    clean_sections = _manual_sections(sections)
    if not clean_sections:
        raise ValueError("主题页至少需要一个正文小节")
    page = RagWikiPage(
        user_id=int(user_id),
        kb_id=int(kb_id),
        title=clean_title,
        normalized_title=normalized,
        page_type="topic",
        summary=_clean(summary or clean_title, 500),
        content_md=_render_markdown(_clean(summary or clean_title, 500), clean_sections),
        sections=clean_sections,
        source_refs=[],
        source_doc_ids=[],
        source_chunk_ids=[],
        entity_ids=[],
        status=WIKI_READY,
        generated_by="manual",
        version=1,
        update_time=datetime.now(),
    )
    db.add(page)
    await db.flush()
    await _replace_wiki_chunks(db, page, clean_sections)
    await db.commit()
    return await get_wiki_page(db, user_id, int(page.id))


async def update_wiki_page(
    db: AsyncSession,
    user_id: int,
    page_id: int,
    *,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    sections: Optional[Sequence[dict]] = None,
    change_type: str = "manual",
    created_by: str = "user",
    expected_version: Optional[int] = None,
) -> dict:
    """手动编辑主题页；先保存旧版本，再更新并重建 Wiki 检索块。"""
    page = (
        await db.execute(
            select(RagWikiPage).where(
                RagWikiPage.id == int(page_id),
                RagWikiPage.user_id == int(user_id),
            )
        )
    ).scalar_one_or_none()
    if not page:
        raise ValueError("知识主题页不存在或无权访问")
    if expected_version is not None and int(page.version or 1) != int(expected_version):
        raise ValueError(
            f"主题页已被更新（当前版本 {int(page.version or 1)}，提交版本 {int(expected_version)}），请刷新后再保存"
        )
    changed = False
    new_title = page.title
    new_normalized_title = page.normalized_title
    if title is not None:
        new_title = _clean(title, 255)
        if not new_title:
            raise ValueError("主题页标题不能为空")
        if new_title != page.title:
            dup = (
                await db.execute(
                    select(RagWikiPage).where(
                        RagWikiPage.user_id == int(user_id),
                        RagWikiPage.kb_id == int(page.kb_id),
                        RagWikiPage.normalized_title == _normalize_title(new_title),
                        RagWikiPage.id != int(page.id),
                    )
                )
            ).scalar_one_or_none()
            if dup:
                raise ValueError(f"同名主题页已存在：{dup.title}")
            new_normalized_title = _normalize_title(new_title)
            changed = True
    new_summary = page.summary
    if summary is not None:
        new_summary = _clean(summary, 500)
        if new_summary != page.summary:
            changed = True
    new_sections = page.sections or []
    if sections is not None:
        cleaned = _manual_sections(sections, page.source_chunk_ids or [])
        if not cleaned:
            raise ValueError("主题页至少需要一个正文小节")
        if cleaned != (page.sections or []):
            new_sections = cleaned
            changed = True
    if not changed:
        return await get_wiki_page(db, user_id, int(page.id))

    # 快照必须保存**修改前**的标题 / 摘要 / 小节，否则“恢复历史版本”会把新值当成旧值。
    db.add(_page_revision_snapshot(page, change_type, created_by))
    page.title = new_title
    page.normalized_title = new_normalized_title
    page.summary = new_summary
    page.sections = new_sections
    page.content_md = _render_markdown(new_summary, new_sections)
    page.status = WIKI_READY
    page.generated_by = change_type
    page.version = int(page.version or 1) + 1
    page.update_time = datetime.now()
    await db.flush()
    await _replace_wiki_chunks(db, page, new_sections)
    await db.commit()
    return await get_wiki_page(db, user_id, int(page.id))


async def list_wiki_revisions(db: AsyncSession, user_id: int, page_id: int) -> list[dict]:
    page = (
        await db.execute(
            select(RagWikiPage).where(
                RagWikiPage.id == int(page_id), RagWikiPage.user_id == int(user_id)
            )
        )
    ).scalar_one_or_none()
    if not page:
        raise ValueError("知识主题页不存在或无权访问")
    rows = (
        await db.execute(
            select(RagWikiPageRevision)
            .where(RagWikiPageRevision.page_id == int(page_id))
            .order_by(RagWikiPageRevision.version.desc(), RagWikiPageRevision.id.desc())
            .limit(30)
        )
    ).scalars().all()
    return [
        {
            "revisionId": int(row.id),
            "version": int(row.version or 1),
            "title": row.title,
            "summary": row.summary,
            "changeType": row.change_type,
            "createdBy": row.created_by,
            "createTime": row.create_time.isoformat(sep=" ") if row.create_time else "",
        }
        for row in rows
    ]


async def restore_wiki_revision(
    db: AsyncSession, user_id: int, page_id: int, revision_id: int
) -> dict:
    page = (
        await db.execute(
            select(RagWikiPage).where(
                RagWikiPage.id == int(page_id), RagWikiPage.user_id == int(user_id)
            )
        )
    ).scalar_one_or_none()
    revision = (
        await db.execute(
            select(RagWikiPageRevision).where(
                RagWikiPageRevision.id == int(revision_id),
                RagWikiPageRevision.page_id == int(page_id),
                RagWikiPageRevision.user_id == int(user_id),
            )
        )
    ).scalar_one_or_none()
    if not page or not revision:
        raise ValueError("主题页或历史版本不存在")
    db.add(_page_revision_snapshot(page, "before_restore", "user"))
    page.title = revision.title or page.title
    page.normalized_title = _normalize_title(page.title)
    page.summary = revision.summary or ""
    page.sections = revision.sections or []
    page.source_refs = revision.source_refs or page.source_refs or []
    page.content_md = revision.content_md or _render_markdown(page.summary, page.sections or [])
    page.status = WIKI_READY
    page.generated_by = "manual"
    page.version = int(page.version or 1) + 1
    page.update_time = datetime.now()
    await db.flush()
    await _replace_wiki_chunks(db, page, page.sections or [])
    await db.commit()
    return await get_wiki_page(db, user_id, int(page.id))


async def delete_wiki_page(db: AsyncSession, user_id: int, page_id: int) -> dict:
    page = (
        await db.execute(
            select(RagWikiPage).where(
                RagWikiPage.id == int(page_id), RagWikiPage.user_id == int(user_id)
            )
        )
    ).scalar_one_or_none()
    if not page:
        raise ValueError("知识主题页不存在或无权访问")
    await db.execute(delete(RagWikiChunk).where(RagWikiChunk.page_id == int(page.id)))
    await db.execute(
        delete(RagWikiPageLink).where(
            or_(
                RagWikiPageLink.from_page_id == int(page.id),
                RagWikiPageLink.to_page_id == int(page.id),
            )
        )
    )
    await db.execute(delete(RagWikiPageRevision).where(RagWikiPageRevision.page_id == int(page.id)))
    await db.execute(
        ContentReference.__table__.update()
        .where(
            ContentReference.user_id == int(user_id),
            ContentReference.target_type == "wiki_page",
            ContentReference.target_id == int(page.id),
        )
        .values(deleted=1)
    )
    title = page.title
    await db.delete(page)
    await db.commit()
    return {"pageId": int(page_id), "title": title, "deleted": True}


def _asset_source_ref(asset_key: str) -> tuple[str, int, Optional[str]]:
    key = str(asset_key or "").strip()
    if key.startswith("doc:"):
        parts = key.split(":")
        if len(parts) >= 3 and parts[1].isdigit():
            return "document_image", int(parts[1]), parts[2]
    if key.startswith("chat:"):
        tail = key.rsplit(":", 1)[-1]
        if tail.isdigit():
            return "chat_image", int(tail), None
    raise ValueError("不支持的图片资产键")


async def attach_wiki_image(
    db: AsyncSession,
    user_id: int,
    page_id: int,
    asset_key: str,
    quote: str = "",
) -> dict:
    page = (
        await db.execute(
            select(RagWikiPage).where(
                RagWikiPage.id == int(page_id), RagWikiPage.user_id == int(user_id)
            )
        )
    ).scalar_one_or_none()
    if not page:
        raise ValueError("知识主题页不存在或无权访问")
    asset = (
        await db.execute(
            select(RagImageAsset).where(
                RagImageAsset.user_id == int(user_id),
                RagImageAsset.asset_key == str(asset_key),
            )
        )
    ).scalar_one_or_none()
    if not asset:
        raise ValueError("图片资产不存在或无权访问")
    # 文档图片默认只能挂到同一资料夹的主题页；聊天图片没有 kb，允许用户自行关联。
    if asset.source_type == "document" and asset.kb_id is not None and int(asset.kb_id) != int(page.kb_id):
        raise ValueError("这张图片属于其他资料夹，不能挂到当前主题页")
    source_type, source_id, source_sub_id = _asset_source_ref(asset_key)
    from app.services.rag import reference_service

    ref = await reference_service.create_reference(
        db,
        user_id,
        source_type=source_type,
        source_id=source_id,
        source_sub_id=source_sub_id,
        target_type="wiki_page",
        target_id=int(page.id),
        quote=_clean(quote or asset.caption or asset.file_name, 800),
        created_by="user",
    )
    return {"pageId": int(page.id), "reference": ref}


async def detach_wiki_image(
    db: AsyncSession, user_id: int, page_id: int, reference_id: int
) -> dict:
    page = (
        await db.execute(
            select(RagWikiPage).where(
                RagWikiPage.id == int(page_id), RagWikiPage.user_id == int(user_id)
            )
        )
    ).scalar_one_or_none()
    ref = (
        await db.execute(
            select(ContentReference).where(
                ContentReference.id == int(reference_id),
                ContentReference.user_id == int(user_id),
                ContentReference.target_type == "wiki_page",
                ContentReference.target_id == int(page_id),
                ContentReference.deleted == 0,
            )
        )
    ).scalar_one_or_none()
    if not page or not ref:
        raise ValueError("主题页图片引用不存在或无权访问")
    from app.services.rag import reference_service

    return await reference_service.delete_reference(db, user_id, int(reference_id))


async def get_wiki_page_by_entity(db: AsyncSession, user_id: int, entity_id: int) -> Optional[dict]:
    pages = (
        await db.execute(
            select(RagWikiPage).where(RagWikiPage.user_id == int(user_id)).order_by(RagWikiPage.update_time.desc())
        )
    ).scalars().all()
    for page in pages:
        if int(entity_id) in {int(x) for x in (page.entity_ids or []) if str(x).isdigit()}:
            return await get_wiki_page(db, user_id, int(page.id))
    return None


async def get_wiki_graph(db: AsyncSession, user_id: int, kb_id: int) -> dict:
    pages = (
        await db.execute(
            select(RagWikiPage).where(
                RagWikiPage.user_id == int(user_id),
                RagWikiPage.kb_id == int(kb_id),
                RagWikiPage.status.in_([WIKI_READY, WIKI_STALE]),
            )
        )
    ).scalars().all()
    page_ids = {int(page.id) for page in pages}
    links = (
        await db.execute(
            select(RagWikiPageLink).where(
                RagWikiPageLink.user_id == int(user_id),
                RagWikiPageLink.kb_id == int(kb_id),
            )
        )
    ).scalars().all()
    links = [
        link
        for link in links
        if int(link.from_page_id) in page_ids and int(link.to_page_id) in page_ids
    ]
    degree: dict[int, int] = {}
    for link in links:
        degree[int(link.from_page_id)] = degree.get(int(link.from_page_id), 0) + 1
        degree[int(link.to_page_id)] = degree.get(int(link.to_page_id), 0) + 1
    nodes = [
        {
            "id": str(page.id),
            "pageId": int(page.id),
            "title": page.title,
            "summary": page.summary,
            "status": page.status,
            "degree": degree.get(int(page.id), 0),
            "sectionCount": len(page.sections or []),
        }
        for page in pages
    ]
    edges = [
        {
            "id": int(link.id),
            "source": str(link.from_page_id),
            "target": str(link.to_page_id),
            "type": link.link_type,
            "weight": int(link.weight or 5),
        }
        for link in links
    ]
    return {"nodes": nodes, "edges": edges, "stats": {"pageCount": len(nodes), "linkCount": len(edges)}}


async def search_wiki_chunks(
    db: AsyncSession,
    user_id: int,
    query: str,
    query_vector: Optional[Sequence[float]],
    kb_ids: Sequence[int],
    top_k: int = 5,
) -> list[ChunkHit]:
    """在知识百科小节中做向量 + 关键词检索，返回可融合的 ChunkHit。"""
    if not kb_ids or not str(query or "").strip():
        return []
    pool = max(int(top_k) * 3, int(top_k))
    base = (
        select(RagWikiChunk, RagWikiPage.title, RagWikiPage.id, RagWikiPage.status)
        .join(RagWikiPage, RagWikiPage.id == RagWikiChunk.page_id)
        .where(
            RagWikiPage.user_id == int(user_id),
            # stale 页面仍然参与检索（用户手写内容不应从问答里消失），
            # 但 ChunkHit 会带 wikiStale，提示回答“这一页可能过期”。
            RagWikiPage.status.in_([WIKI_READY, WIKI_STALE]),
            RagWikiChunk.kb_id.in_([int(x) for x in kb_ids]),
        )
    )
    vector_hits: list[ChunkHit] = []
    if query_vector:
        distance = RagWikiChunk.embedding.cosine_distance(list(query_vector))
        rows = (
            await db.execute(
                base.add_columns(distance.label("distance"))
                .where(RagWikiChunk.embedding.isnot(None))
                .order_by(distance)
                .limit(pool)
            )
        ).all()
        for row in rows:
            chunk: RagWikiChunk = row[0]
            similarity = 1.0 - float(row[4])
            if similarity < 0.3:
                continue
            vector_hits.append(
                _wiki_hit(chunk, row[1], row[2], row[3], vector_score=similarity)
            )
    keyword_hits: list[ChunkHit] = []
    tokens = [t for t in query_tokens(query) if t]
    if tokens:
        from sqlalchemy import func as _func

        tsquery = _func.to_tsquery("simple", " | ".join(tokens))
        rank = _func.ts_rank_cd(RagWikiChunk.search_vec, tsquery)
        rows = (
            await db.execute(
                base.add_columns(rank.label("rank"))
                .where(RagWikiChunk.search_vec.op("@@")(tsquery))
                .order_by(rank.desc())
                .limit(pool)
            )
        ).all()
        for row in rows:
            chunk: RagWikiChunk = row[0]
            keyword_hits.append(
                _wiki_hit(chunk, row[1], row[2], row[3], keyword_score=float(row[4]))
            )
    if not vector_hits and not keyword_hits:
        return []
    from app.services.rag.hybrid_search import reciprocal_rank_fusion

    return reciprocal_rank_fusion([vector_hits, keyword_hits], top_k=max(int(top_k), 1))


def _wiki_hit(
    chunk: RagWikiChunk,
    page_title: str,
    page_id: int,
    page_status: str,
    *,
    vector_score: Optional[float] = None,
    keyword_score: Optional[float] = None,
) -> ChunkHit:
    return ChunkHit(
        chunk_id=int(chunk.id),
        doc_id=0,
        kb_id=int(chunk.kb_id),
        chunk_index=int(chunk.section_index or 0),
        content=chunk.content,
        doc_name=f"知识百科《{page_title}》",
        vector_score=vector_score,
        keyword_score=keyword_score,
        wiki_hit=True,
        wiki_page_id=int(page_id),
        wiki_page_title=page_title,
        wiki_section=chunk.section_title,
        wiki_stale=(page_status == WIKI_STALE),
    )
