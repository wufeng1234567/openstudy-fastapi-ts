"""知识百科（Wiki）主题页生成、页面图谱与 Wiki RAG 检索。

边界
----
- 实体关系图是底层索引；本模块把图上的实体整理成**用户能读的主题页**。
- 页面正文只使用原始资料 chunk，不拿别的 Wiki 页面做二次摘要，避免错误逐层放大。
- 每个小节都必须能落回真实 chunk；找不到来源的小节直接丢弃，不硬编。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional, Sequence

from loguru import logger
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentReference, RagImageAsset
from app.models.knowledge_graph import RagGraphEntity, RagGraphRelation
from app.models.question import QuestionBank, QuestionMain, QuestionSource, UserPracticeLog
from app.models.rag import RagDocument, RagDocumentChunk
from app.models.wiki import (
    RagWikiChunk,
    RagWikiPage,
    RagWikiPageLearning,
    RagWikiPageLink,
    RagWikiPageRevision,
)
from app.services.ai.base_client import ChatMessage, TextBlock
from app.services.ai.db_config import chat_with_config
from app.services.rag.embedding import embed_texts
from app.services.rag.hybrid_search import ChunkHit
from app.services.rag.rag_write_service import get_knowledge_base, sanitize_text
from app.services.rag.tokenizer import query_tokens, tokenize
from app.services.rag.wiki_merge_service import (
    apply_source_to_page,
    merge_generation_sources,
)
from app.services.rag.wiki_link_service import (
    extract_wiki_links,
    linkify_content,
    normalize_wiki_tokens,
    page_text_blocks,
    strip_wiki_tokens,
)

from app.services.rag.wiki_payload_helpers import (
    MAX_SOURCE_CHUNKS, DEFAULT_BUILD_LIMIT,
    WIKI_DRAFT, WIKI_READY, WIKI_STALE, WIKI_FAILED,
    _GENERIC_RELATIONS,
    build_learning_snapshot, _link_type_for_relation, _asset_source_ref,
)


from app.services.rag.wiki_helpers import (_page_type_for_entity, _clean_aliases, _clean, _normalize_title, _display_title, _parse_page_payload, _section_source_ids, _validate_page_payload, _render_markdown, _build_prompt)


from app.services.rag.wiki_content_helpers import (
    _asset_key_from_reference,
    _cited_source_refs,
    _find_anchor_position,
    _manual_sections,
    _page_revision_snapshot,
    _source_refs,
    _wiki_hit,
)

from app.services.rag.wiki_view_helpers import (
    build_graph_edges,
    build_graph_node,
    build_in_links,
    build_link_stats,
    build_mention_edges,
    build_out_links,
    build_page_list_item,
    count_by_page_type,
    count_learning_stats,
    count_link_degree,
)
from app.services.rag.wiki_link_edit import (
    apply_block_text,
    find_anchor_block,
    find_link_match,
    insert_link_marker,
    page_link_pattern,
    replace_link_with_text,
)

from app.services.rag.wiki_page_queries import (
    load_page,
)

from app.services.rag.wiki_page_state import (
    mark_page_manual,
    refresh_page_derived,
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


async def _replace_wiki_chunks(
    db: AsyncSession, page: RagWikiPage, sections: Sequence[Dict[str, Any]]
) -> int:
    """重建页面小节向量；失败只影响 Wiki RAG，不让页面生成失败。"""
    await db.execute(delete(RagWikiChunk).where(RagWikiChunk.page_id == int(page.id)))
    texts = [
        f"{section.get('heading', '')}\n{strip_wiki_tokens(str(section.get('body', '')))}".strip()
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


async def _rebuild_links(
    db: AsyncSession, user_id: int, kb_id: int, pages: Sequence[RagWikiPage]
) -> int:
    """重建页面级导航边：实体关系 + 正文里真实存在的页面内链。

    实体关系边回答“这两个主题为什么相关”；内链边回答“用户从哪一页能点到
    哪一页”。两者分开建，内链边在每次页面保存/批量更新后整体重建，避免旧链接
    残留在图上。
    """
    if not pages:
        return 0
    page_by_id = {int(page.id): page for page in pages}
    page_ids = set(page_by_id)
    # 只清理正文内链产生的边，不动实体关系推导出的页面边。
    await db.execute(
        delete(RagWikiPageLink).where(
            RagWikiPageLink.user_id == int(user_id),
            RagWikiPageLink.kb_id == int(kb_id),
            RagWikiPageLink.link_type == "mention",
            RagWikiPageLink.source == "mention",
        )
    )
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

    def add_link(
        from_page_id: int,
        to_page_id: int,
        link_type: str,
        weight: int,
        source: str,
        *,
        skip_reverse: bool = False,
    ) -> None:
        nonlocal created
        if from_page_id == to_page_id:
            return
        key = (int(from_page_id), int(to_page_id), str(link_type))
        if key in existing:
            return
        if skip_reverse and (int(to_page_id), int(from_page_id), str(link_type)) in existing:
            return
        db.add(
            RagWikiPageLink(
                user_id=int(user_id),
                kb_id=int(kb_id),
                from_page_id=int(from_page_id),
                to_page_id=int(to_page_id),
                link_type=str(link_type),
                weight=max(1, min(10, int(weight or 5))),
                source=str(source),
            )
        )
        existing.add(key)
        created += 1

    entity_to_page: dict[int, RagWikiPage] = {}
    for page in pages:
        for entity_id in page.entity_ids or []:
            try:
                entity_to_page[int(entity_id)] = page
            except (TypeError, ValueError):
                continue
    if len(entity_to_page) >= 2:
        relations = (
            await db.execute(
                select(RagGraphRelation).where(
                    RagGraphRelation.user_id == int(user_id),
                    RagGraphRelation.kb_id == int(kb_id),
                )
            )
        ).scalars().all()
        for rel in relations:
            source_page = entity_to_page.get(int(rel.source_id))
            target_page = entity_to_page.get(int(rel.target_id))
            if not source_page or not target_page:
                continue
            relation_type = str(rel.relation_type or "相关")
            if relation_type == "前置":
                # 抽取结果中 source 是“依赖方”，target 是“前置知识”
                # （例如：微分中值定理 -> 导数，表示学中值定理前要先学导数）。
                # 页面图必须把前置页指向依赖页，才能让前端箭头与航线顺序正确。
                add_link(
                    int(target_page.id),
                    int(source_page.id),
                    "prerequisite",
                    int(rel.strength or 5),
                    "graph",
                    skip_reverse=True,
                )
                continue
            add_link(
                int(source_page.id),
                int(target_page.id),
                _link_type_for_relation(relation_type),
                int(rel.strength or 5),
                "graph",
                skip_reverse=True,
            )

    # 正文内链：[[page:目标页|显示词]]，只连接仍在当前资料夹里的页面。
    for page in pages:
        for block in page_text_blocks(str(page.summary or ""), page.sections or []):
            for item in extract_wiki_links(str(block.get("text") or ""), int(block.get("sectionIndex", -1))):
                target_id = int(item.get("pageId") or 0)
                if target_id in page_ids:
                    add_link(int(page.id), target_id, "mention", 5, "mention")
    return created


async def linkify_wiki_pages(
    db: AsyncSession,
    user_id: int,
    kb_id: int,
    *,
    add_missing: bool = True,
) -> dict:
    """重建 Wiki 页面内链。

    - 先把正文里的 ``[[标题|原词]]`` 归一化成 ``[[page:id|原词]]``；
    - 再由页面标题、aliases、实体名做最长匹配，给每个页面补第一条安全链接；
    - 只改正文，不重算向量：`RagWikiChunk` 索引的是去掉链接标记后的文字，
      链接标记不改变锚文本，所以向量内容等价。
    """
    pages = await _load_kb_pages(db, int(user_id), int(kb_id))
    if not pages:
        return {"pages": 0, "links": 0}
    page_ids = {int(page.id) for page in pages}
    page_by_id = {int(page.id): page for page in pages}

    entities = await _load_kb_entities(db, int(user_id), int(kb_id))
    entity_by_id = {int(entity.id): entity for entity in entities}
    relation_rows = (
        await db.execute(
            select(RagGraphRelation).where(
                RagGraphRelation.user_id == int(user_id),
                RagGraphRelation.kb_id == int(kb_id),
            )
        )
    ).scalars().all()
    degree: dict[int, int] = {}
    page_relation_types: dict[int, list[dict]] = {}
    for relation in relation_rows:
        source_id, target_id = int(relation.source_id), int(relation.target_id)
        degree[source_id] = degree.get(source_id, 0) + 1
        degree[target_id] = degree.get(target_id, 0) + 1
        item = {"relationType": relation.relation_type}
        page_relation_types.setdefault(source_id, []).append(item)
        page_relation_types.setdefault(target_id, []).append(item)
    entity_names_by_page: dict[int, list[str]] = {}
    for page in pages:
        names: list[str] = []
        typed = False
        original_type = str(page.page_type or "")
        for raw_id in page.entity_ids or []:
            try:
                entity = entity_by_id.get(int(raw_id))
            except (TypeError, ValueError):
                entity = None
            if not entity:
                continue
            if not typed and str(page.page_type or "") in {"", "topic"}:
                page.page_type = _page_type_for_entity(
                    entity,
                    degree.get(int(entity.id), 0),
                    page_relation_types.get(int(entity.id), []),
                )
                typed = True
            names.append(str(entity.name or ""))
            names.extend(str(x) for x in (entity.aliases or []) if str(x).strip())
        entity_names_by_page[int(page.id)] = names

    # 候选标题/别名 → 页面。页面标题优先于实体别名；同一表面词只允许指向一个页面。
    title_to_page: dict[str, dict[str, Any]] = {}
    surface_priority: dict[str, tuple[int, int]] = {}
    surface_to_page: dict[str, int] = {}

    def register_surface(surface: str, page_id: int, priority: int) -> None:
        text = _clean(surface, 120)
        key = _normalize_title(text)
        if not key or len(text) < 2:
            return
        if priority > surface_priority.get(key, (-1, 0))[0] or (
            priority == surface_priority.get(key, (-1, 0))[0]
            and page_id < surface_priority.get(key, (-1, 0))[1]
        ):
            surface_priority[key] = (priority, page_id)
            surface_to_page[key] = page_id
        title_to_page.setdefault(key, {"pageId": page_id, "title": page_by_id[page_id].title})

    for page in pages:
        register_surface(str(page.title or ""), int(page.id), 10)
        for alias in page.aliases or []:
            register_surface(str(alias or ""), int(page.id), 8)
        for name in entity_names_by_page.get(int(page.id), []):
            register_surface(name, int(page.id), 6)

    # surface_to_page 里存的是 key（归一化文本），但展示时应使用原词；重新从页面标题/别名收集。
    display_surfaces: dict[str, str] = {}
    for page in pages:
        for surface in [page.title, *(page.aliases or []), *entity_names_by_page.get(int(page.id), [])]:
            text = _clean(surface, 120)
            key = _normalize_title(text)
            if key and surface_to_page.get(key) == int(page.id) and len(text) >= 2:
                display_surfaces.setdefault(key, text)
    refs = [
        {"pageId": int(page_id), "matchText": display_surfaces.get(key, key)}
        for key, page_id in surface_to_page.items()
        if page_id in page_by_id
    ]

    changed_pages = 0
    total_links = 0
    for page in pages:
        summary = normalize_wiki_tokens(
            str(page.summary or ""), title_to_page, page_ids, int(page.id)
        )
        sections: list[dict] = []
        for section in page.sections or []:
            if not isinstance(section, dict):
                continue
            item = dict(section)
            body = normalize_wiki_tokens(str(item.get("body") or ""), title_to_page, page_ids, int(page.id))
            if add_missing:
                body, added = linkify_content(body, refs, self_page_id=int(page.id))
                total_links += added
            item["body"] = body
            sections.append(item)
        if add_missing:
            summary, added = linkify_content(summary, refs, self_page_id=int(page.id))
            total_links += added
        if (
            summary != (page.summary or "")
            or sections != (page.sections or [])
            or str(page.page_type or "") != original_type
        ):
            page.summary = summary
            page.sections = sections
            page.content_md = _render_markdown(summary, sections)
            page.update_time = datetime.now()
            changed_pages += 1

    if changed_pages:
        await db.commit()
    return {"pages": changed_pages, "links": total_links}


async def build_wiki_pages(
    db: AsyncSession,
    user_id: int,
    kb_id: int,
    *,
    force: bool = False,
    limit: int = DEFAULT_BUILD_LIMIT,
    doc_ids: Optional[Sequence[int]] = None,
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
    if doc_ids:
        wanted_doc_ids = {int(item) for item in doc_ids if str(item).isdigit() or isinstance(item, int)}
        docs = [doc for doc in docs if int(doc.id) in wanted_doc_ids]
    if not docs:
        raise ValueError("当前资料夹没有可整理成知识百科的资料")
    doc_names = {int(doc.id): str(doc.file_name or "资料") for doc in docs}
    valid_doc_ids = set(doc_names)

    entities = await _load_kb_entities(db, int(user_id), int(kb_id))
    entities = [
        entity
        for entity in entities
        if any(int(doc_id) in valid_doc_ids for doc_id in (entity.doc_ids or []) if str(doc_id).isdigit())
        # 变量/符号保留在实体图里供 GraphRAG 使用，但不值得单独成一篇“主题页”，
        # 否则知识百科会被 x0、ξ、[a,b] 这类碎片页面稀释。
        and str(entity.type or "") != "变量/符号"
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
    linkable_titles = [_display_title(entity.name) for entity in candidates]
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
                                    linkable_titles=linkable_titles,
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
            source_chunk_ids = []
            for section in sections:
                for chunk_id in section.get("sourceChunkIds", []):
                    if chunk_id not in source_chunk_ids:
                        source_chunk_ids.append(int(chunk_id))
            cited_ids = set(source_chunk_ids)
            source_refs = [
                item
                for item in _source_refs(chunks, doc_names)
                if int(item["chunkId"]) in cited_ids
            ]
            if existing:
                # 快照必须在覆盖字段之前：保存旧标题/旧摘要/旧小节。
                db.add(_page_revision_snapshot(existing, "before_ai_regenerate", "agent"))
                page = existing
                page.version = int(page.version or 1) + 1
            else:
                page = RagWikiPage(
                    user_id=int(user_id),
                    kb_id=int(kb_id),
                    title=_display_title(entity.name)[:255],
                    normalized_title=_normalize_title(entity.name),
                    page_type="topic",
                    version=1,
                )
                db.add(page)
                await db.flush()
            page.page_type = _page_type_for_entity(
                entity, degree.get(int(entity.id), 0), relations
            )
            page.generated_by = "llm"
            source_doc_ids = sorted(
                {int(item["docId"]) for item in source_refs if item.get("docId")}
            )
            primary_doc_id = source_doc_ids[0] if source_doc_ids else 0
            apply_source_to_page(
                page,
                title=_display_title(entity.name)[:255],
                page_type=page.page_type,
                summary=summary,
                sections=sections,
                source_refs=source_refs,
                source_chunk_ids=source_chunk_ids,
                entity_ids=[int(entity.id)],
                source_type="document",
                source_id=primary_doc_id,
                source_name=doc_names.get(primary_doc_id, "资料"),
                aliases=[
                    *[str(x).strip() for x in (entity.aliases or []) if str(x).strip()],
                    *validated.get("aliases", []),
                ],
            )
            # 多文档共同生成一页时，把所有来源都记到 generation_meta.sources，
            # 供按来源更新/分组展示使用。
            for extra_doc_id in source_doc_ids[1:]:
                page.generation_meta = merge_generation_sources(
                    page.generation_meta,
                    source_type="document",
                    source_id=int(extra_doc_id),
                    source_name=doc_names.get(int(extra_doc_id), "资料"),
                )
            page.generation_meta["relationCount"] = len(relations)
            page.generation_meta["sourceChunkCount"] = len(page.source_chunk_ids or [])
            await db.flush()
            await _replace_wiki_chunks(db, page, page.sections or [])
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
    # 先做内链归一化/补链，再把内链边写进页面图。
    linkify_stats = await linkify_wiki_pages(db, int(user_id), int(kb_id), add_missing=True)
    all_pages = await _load_kb_pages(db, int(user_id), int(kb_id))
    links = await _rebuild_links(db, int(user_id), int(kb_id), all_pages)
    await db.commit()
    return {
        "processed": len(pages_touched),
        "pages": len(all_pages),
        "links": links,
        "mentions": int(linkify_stats.get("links") or 0),
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
    pages = await _load_kb_pages(db, int(user_id), int(kb_id))
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


async def _wiki_learning_map(
    db: AsyncSession, user_id: int, pages: Sequence[RagWikiPage]
) -> dict[int, dict]:
    """一次算出多张主题页的阅读 + 练习学习态，避免图谱/列表 N+1 查询。"""
    page_list = [page for page in pages if page is not None]
    if not page_list:
        return {}
    page_ids = [int(page.id) for page in page_list]
    view_rows = (
        await db.execute(
            select(RagWikiPageLearning).where(
                RagWikiPageLearning.user_id == int(user_id),
                RagWikiPageLearning.page_id.in_(page_ids),
            )
        )
    ).scalars().all()
    view_by_page = {
        int(row.page_id): (int(row.view_count or 0), row.last_view_time)
        for row in view_rows
    }

    doc_to_pages: dict[int, set[int]] = {}
    chunk_to_pages: dict[int, set[int]] = {}
    for page in page_list:
        page_id = int(page.id)
        for doc_id in page.source_doc_ids or []:
            try:
                doc_to_pages.setdefault(int(doc_id), set()).add(page_id)
            except (TypeError, ValueError):
                continue
        for chunk_id in page.source_chunk_ids or []:
            try:
                chunk_to_pages.setdefault(int(chunk_id), set()).add(page_id)
            except (TypeError, ValueError):
                continue

    practice_stats = {
        int(page.id): {"practice_count": 0, "correct_count": 0, "last_practice_time": None}
        for page in page_list
    }
    if doc_to_pages:
        practice_rows = (
            await db.execute(
                select(
                    QuestionSource.doc_id,
                    QuestionSource.chunk_id,
                    UserPracticeLog.is_correct,
                    UserPracticeLog.create_time,
                )
                .select_from(UserPracticeLog)
                .join(QuestionSource, QuestionSource.question_id == UserPracticeLog.question_id)
                # 题目被物理删除后流水仍在；学习态不能把孤儿流水算成“练过”。
                .join(QuestionMain, QuestionMain.id == QuestionSource.question_id)
                .where(
                    UserPracticeLog.user_id == int(user_id),
                    QuestionMain.status == "0",
                    QuestionSource.doc_id.in_(list(doc_to_pages.keys())),
                )
            )
        ).all()
        for doc_id, chunk_id, is_correct, create_time in practice_rows:
            target_pages: set[int] = set()
            if chunk_id is not None:
                target_pages.update(chunk_to_pages.get(int(chunk_id), set()))
            if not target_pages:
                target_pages.update(doc_to_pages.get(int(doc_id), set()))
            for page_id in target_pages:
                stat = practice_stats.get(page_id)
                if stat is None:
                    continue
                stat["practice_count"] += 1
                if int(is_correct or 0) == 1:
                    stat["correct_count"] += 1
                if create_time and (
                    stat["last_practice_time"] is None
                    or create_time > stat["last_practice_time"]
                ):
                    stat["last_practice_time"] = create_time

    result: dict[int, dict] = {}
    for page in page_list:
        page_id = int(page.id)
        views, last_view = view_by_page.get(page_id, (0, None))
        stat = practice_stats[page_id]
        result[page_id] = build_learning_snapshot(
            view_count=views,
            practice_count=stat["practice_count"],
            correct_count=stat["correct_count"],
            last_view_time=last_view,
            last_practice_time=stat["last_practice_time"],
        )
    return result


async def _wiki_practice_bank(
    db: AsyncSession, user_id: int, page: RagWikiPage
) -> Optional[dict]:
    """找这道主题页的“同源练习题库”：题目来源命中页面 chunk 或文档时才算。"""
    doc_ids = []
    chunk_ids = []
    for value in page.source_doc_ids or []:
        try:
            doc_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    for value in page.source_chunk_ids or []:
        try:
            chunk_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    conditions = []
    if doc_ids:
        conditions.append(QuestionSource.doc_id.in_(doc_ids))
    if chunk_ids:
        conditions.append(QuestionSource.chunk_id.in_(chunk_ids))
    if not conditions:
        return None
    rows = (
        await db.execute(
            select(
                QuestionSource.question_id,
                QuestionMain.bank_id,
                QuestionBank.bank_name,
                QuestionBank.user_id,
                QuestionBank.is_public,
            )
            .select_from(QuestionSource)
            .join(QuestionMain, QuestionMain.id == QuestionSource.question_id)
            .join(QuestionBank, QuestionBank.id == QuestionMain.bank_id)
            .where(
                QuestionMain.status == "0",
                QuestionBank.status == "0",
                or_(*conditions),
            )
        )
    ).all()
    grouped: dict[int, dict] = {}
    for question_id, bank_id, bank_name, owner_id, is_public in rows:
        # 与练习接口保持同一可见性口径：自己的题库、公开题库可练；分享题库由练习接口再校验。
        # 修复：此前条件写反，会跳过别人的公开题库、反而放行别人的私有题库。
        if int(owner_id or 0) != int(user_id) and int(is_public or 0) == 0:
            continue
        key = int(bank_id)
        entry = grouped.setdefault(
            key,
            {"bankId": key, "bankName": str(bank_name or "题库"), "questionIds": set()},
        )
        entry["questionIds"].add(int(question_id))
    if not grouped:
        return None
    best = max(grouped.values(), key=lambda item: (len(item["questionIds"]), -item["bankId"]))
    return {
        "bankId": best["bankId"],
        "bankName": best["bankName"],
        "questionCount": len(best["questionIds"]),
        # 计划层需要真实题目 ID 做完成判定；这里只返回可见题库里的题，
        # 与练习接口的可见性口径一致（自己的 / 公开的）。
        "questionIds": sorted(best["questionIds"]),
    }


async def record_wiki_page_view(db: AsyncSession, user_id: int, page_id: int) -> dict:
    """记录一次真实打开主题页；重复打开累加次数，不编造阅读时长。"""
    page = await load_page(db, user_id, page_id)
    if not page:
        raise ValueError("知识主题页不存在或无权访问")
    row = (
        await db.execute(
            select(RagWikiPageLearning).where(
                RagWikiPageLearning.user_id == int(user_id),
                RagWikiPageLearning.page_id == int(page_id),
            )
        )
    ).scalar_one_or_none()
    now = datetime.now()
    if row is None:
        row = RagWikiPageLearning(
            user_id=int(user_id),
            kb_id=int(page.kb_id),
            page_id=int(page_id),
            view_count=1,
            last_view_time=now,
            update_time=now,
        )
        db.add(row)
    else:
        row.view_count = int(row.view_count or 0) + 1
        row.last_view_time = now
        row.update_time = now
    await db.flush()
    learning = (await _wiki_learning_map(db, int(user_id), [page]))[int(page.id)]
    return {"pageId": int(page.id), "learning": learning}


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
    learning_by_page = await _wiki_learning_map(db, int(user_id), pages)
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
        link_counts = count_link_degree(links)
    items = [
        build_page_list_item(page, link_counts, learning_by_page.get(int(page.id)))
        for page in pages
    ]
    learning_stats = count_learning_stats(items)
    stats = {
        "pageCount": len(items),
        "readyCount": sum(1 for item in items if item["status"] == WIKI_READY),
        "staleCount": sum(1 for item in items if item["status"] == WIKI_STALE),
        "docCount": len({doc_id for page in pages for doc_id in (page.source_doc_ids or [])}),
        "linkCount": sum(1 for link in (links if page_ids else []) if str(link.link_type) == "mention"),
        "readCount": learning_stats["readCount"],
        "practicedCount": learning_stats["practicedCount"],
        "masteredCount": learning_stats["masteredCount"],
        "typeCounts": count_by_page_type(items),
    }
    return {"pages": items, "stats": stats}


async def _page_link_payload(db: AsyncSession, user_id: int, page: RagWikiPage) -> dict:
    """从页面正文解析出链/反链，不依赖第二张链接表。

    正文是唯一事实源：用户删除一个 ``[[page:...]]`` 标记，反链自然消失；不需要
    再维护一套容易漂移的 link 表。页面图仍然由 `_rebuild_links` 从正文派生。
    """
    pages = (
        await db.execute(
            select(RagWikiPage).where(
                RagWikiPage.user_id == int(user_id),
                RagWikiPage.kb_id == int(page.kb_id),
                RagWikiPage.status.in_([WIKI_READY, WIKI_STALE, WIKI_DRAFT]),
            )
        )
    ).scalars().all()
    page_by_id = {int(item.id): item for item in pages}
    page_by_id[int(page.id)] = page

    out_links = build_out_links(page, page_by_id)
    in_links = build_in_links(page, pages)
    return {
        "outLinks": out_links,
        "inLinks": in_links,
        "linkStats": build_link_stats(out_links, in_links),
    }


async def get_wiki_page(db: AsyncSession, user_id: int, page_id: int) -> dict:
    page = await load_page(db, user_id, page_id)
    if not page:
        raise ValueError("知识主题页不存在或无权访问")
    if page.merged_into_page_id and int(page.merged_into_page_id) != int(page.id):
        return await get_wiki_page(db, user_id, int(page.merged_into_page_id))
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
        # mention 是正文内链，单独用 outLinks/inLinks 展示，避免“相关主题”重复一长串。
        if str(link.link_type) == "mention":
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
    link_payload = await _page_link_payload(db, user_id, page)
    learning = (await _wiki_learning_map(db, int(user_id), [page]))[int(page.id)]
    practice_bank = await _wiki_practice_bank(db, int(user_id), page)
    page_sources = _cited_source_refs(page)
    source_doc_ids = sorted(
        {
            int(item["docId"])
            for item in page_sources
            if isinstance(item, dict) and str(item.get("docId") or "").isdigit()
        }
    ) or list(page.source_doc_ids or [])
    return {
        "pageId": int(page.id),
        "kbId": int(page.kb_id),
        "title": page.title,
        "pageType": page.page_type,
        "aliases": page.aliases or [],
        "summary": page.summary,
        "contentMd": page.content_md,
        "sections": page.sections or [],
        "sources": page_sources,
        "sourceDocIds": source_doc_ids,
        "sourceChunkIds": page.source_chunk_ids or [],
        "sourceStats": {
            "docCount": len(source_doc_ids),
            "chunkCount": len(page_sources),
            "contextChunkCount": len(page.source_refs or []),
        },
        "entityIds": page.entity_ids or [],
        "status": page.status,
        "generatedBy": page.generated_by or "llm",
        "version": int(page.version or 1),
        "updateTime": page.update_time.isoformat(sep=" ") if page.update_time else None,
        "related": related_items,
        "outLinks": link_payload["outLinks"],
        "inLinks": link_payload["inLinks"],
        "linkStats": link_payload["linkStats"],
        "images": await _page_images(db, user_id, int(page.id)),
        "learning": learning,
        "practice": practice_bank,
    }


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


async def create_manual_wiki_page(
    db: AsyncSession,
    user_id: int,
    kb_id: int,
    *,
    title: str,
    summary: str = "",
    sections: Optional[Sequence[dict]] = None,
    aliases: Optional[Sequence[str]] = None,
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
        aliases=_clean_aliases(aliases or []),
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


async def _load_kb_pages(db: AsyncSession, user_id: int, kb_id: int) -> list:
    """该资料夹里「就绪 / 过期」的页面（重建页面链接图时的输入）。

    ⚠ 这段查询原本在**六处**逐字重复 —— 现在收敛到一处，筛选口径不会再各处漂。
    """
    return (
        await db.execute(
            select(RagWikiPage).where(
                RagWikiPage.user_id == int(user_id),
                RagWikiPage.kb_id == int(kb_id),
                RagWikiPage.status.in_([WIKI_READY, WIKI_STALE]),
            )
        )
    ).scalars().all()


async def _load_kb_entities(db: AsyncSession, user_id: int, kb_id: int) -> list:
    """该资料夹下的**实体**（页面图谱的节点来源）。

    ⚠ 这段查询原本在**两处**逐字相同 —— 现在收敛到一处，
    「按 user + kb 取实体」的筛选口径不会再各处漂。
    """
    return (
        await db.execute(
            select(RagGraphEntity).where(
                RagGraphEntity.user_id == int(user_id),
                RagGraphEntity.kb_id == int(kb_id),
            )
        )
    ).scalars().all()


async def _finalize_page_edit(db: AsyncSession, user_id: int, page: RagWikiPage) -> None:
    """页面改动后的收尾：重建该资料夹的页面链接图并提交。

    ⚠ 这三步原本在**四个入口**里**逐字相同** —— 现在收敛到一处。
    """
    all_pages = await _load_kb_pages(db, int(user_id), int(page.kb_id))
    await _rebuild_links(db, int(user_id), int(page.kb_id), all_pages)
    await db.commit()


async def update_wiki_page(
    db: AsyncSession,
    user_id: int,
    page_id: int,
    *,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    sections: Optional[Sequence[dict]] = None,
    aliases: Optional[Sequence[str]] = None,
    change_type: str = "manual",
    created_by: str = "user",
    expected_version: Optional[int] = None,
) -> dict:
    """手动编辑主题页；先保存旧版本，再更新并重建 Wiki 检索块。"""
    page = await load_page(db, user_id, page_id)
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
    new_aliases = page.aliases or []
    if aliases is not None:
        cleaned_aliases = _clean_aliases(aliases)
        if cleaned_aliases != list(page.aliases or []):
            new_aliases = cleaned_aliases
            changed = True
    if not changed:
        return await get_wiki_page(db, user_id, int(page.id))

    # 快照必须保存**修改前**的标题 / 摘要 / 小节，否则“恢复历史版本”会把新值当成旧值。
    db.add(_page_revision_snapshot(page, change_type, created_by))
    page.title = new_title
    page.normalized_title = new_normalized_title
    page.aliases = new_aliases
    page.summary = new_summary
    page.sections = new_sections
    refresh_page_derived(page, _render_markdown(new_summary, new_sections))
    mark_page_manual(page, change_type)
    await db.flush()
    await _replace_wiki_chunks(db, page, new_sections)
    await db.commit()
    # 手动编辑可能新增/删除 [[标题]] 标记；只做归一化，不自动回填，尊重用户删链接。
    await linkify_wiki_pages(db, int(user_id), int(page.kb_id), add_missing=False)
    await _finalize_page_edit(db, int(user_id), page)
    return await get_wiki_page(db, user_id, int(page.id))


async def add_wiki_page_link(
    db: AsyncSession,
    user_id: int,
    page_id: int,
    *,
    target_page_id: int,
    anchor_text: str,
    section_index: Optional[int] = None,
) -> dict:
    """手动添加页面内链：只允许链接同资料夹页面，锚文本必须真实出现在正文。"""
    page = await load_page(db, user_id, page_id)
    if not page:
        raise ValueError("知识主题页不存在或无权访问")
    target = (
        await db.execute(
            select(RagWikiPage).where(
                RagWikiPage.id == int(target_page_id),
                RagWikiPage.user_id == int(user_id),
                RagWikiPage.kb_id == int(page.kb_id),
            )
        )
    ).scalar_one_or_none()
    if not target:
        raise ValueError("目标主题页不存在，或不属于当前资料夹")
    if int(target.id) == int(page.id):
        raise ValueError("不能把主题页链接到它自己")
    anchor = _clean(anchor_text, 120)
    if not anchor:
        raise ValueError("锚文本不能为空")
    if section_index is not None and int(section_index) < -1:
        raise ValueError("sectionIndex 只能是 -1（摘要）或小节序号")

    blocks = page_text_blocks(str(page.summary or ""), page.sections or [])
    chosen = find_anchor_block(blocks, section_index, anchor)
    if chosen is None:
        raise ValueError("正文中没有找到这段文字，请先在正文里写上锚文本再添加链接")
    text = str(chosen["text"])
    pos = _find_anchor_position(text, anchor)
    new_text = insert_link_marker(text, pos, int(target.id), anchor)
    db.add(_page_revision_snapshot(page, "before_manual_link", "user"))
    apply_block_text(page, chosen, new_text)
    refresh_page_derived(page, _render_markdown(str(page.summary or ""), page.sections or []))
    await db.flush()
    await db.commit()
    await linkify_wiki_pages(db, int(user_id), int(page.kb_id), add_missing=False)
    await _finalize_page_edit(db, int(user_id), page)
    return await get_wiki_page(db, user_id, int(page.id))


async def remove_wiki_page_link(
    db: AsyncSession,
    user_id: int,
    page_id: int,
    *,
    target_page_id: int,
    anchor_text: str = "",
    section_index: Optional[int] = None,
) -> dict:
    """手动移除页面内链：把 [[page:id|锚文本]] 还原成普通文字，保留正文。"""
    page = await load_page(db, user_id, page_id)
    if not page:
        raise ValueError("知识主题页不存在或无权访问")
    pattern = page_link_pattern(target_page_id)
    desired_anchor = _clean(anchor_text, 120)
    blocks = page_text_blocks(str(page.summary or ""), page.sections or [])
    chosen, match_to_replace = find_link_match(blocks, section_index, pattern, desired_anchor)
    if chosen is None or match_to_replace is None:
        raise ValueError("没有找到这条页面链接，可能已被删除")
    text = str(chosen["text"])
    label = str(match_to_replace.group(1) or "").strip()
    new_text = replace_link_with_text(text, match_to_replace, label)
    db.add(_page_revision_snapshot(page, "before_manual_unlink", "user"))
    apply_block_text(page, chosen, new_text)
    refresh_page_derived(page, _render_markdown(str(page.summary or ""), page.sections or []))
    await db.flush()
    await db.commit()
    await _finalize_page_edit(db, int(user_id), page)
    return await get_wiki_page(db, user_id, int(page.id))


async def refresh_wiki_page_links(db: AsyncSession, user_id: int, page_id: int) -> dict:
    """重新扫描当前资料夹页面标题/别名，给所有页面补链。"""
    page = await load_page(db, user_id, page_id)
    if not page:
        raise ValueError("知识主题页不存在或无权访问")
    stats = await linkify_wiki_pages(db, int(user_id), int(page.kb_id), add_missing=True)
    all_pages = await _load_kb_pages(db, int(user_id), int(page.kb_id))
    links = await _rebuild_links(db, int(user_id), int(page.kb_id), all_pages)
    await db.commit()
    result = await get_wiki_page(db, user_id, int(page.id))
    result["refreshStats"] = {**stats, "pageLinks": links}
    return result


async def list_wiki_revisions(db: AsyncSession, user_id: int, page_id: int) -> list[dict]:
    page = await load_page(db, user_id, page_id)
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
    page = await load_page(db, user_id, page_id)
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
    refresh_page_derived(page, revision.content_md or _render_markdown(page.summary, page.sections or []))
    mark_page_manual(page, "manual")
    await db.flush()
    await _replace_wiki_chunks(db, page, page.sections or [])
    await db.commit()
    await linkify_wiki_pages(db, int(user_id), int(page.kb_id), add_missing=False)
    await _finalize_page_edit(db, int(user_id), page)
    return await get_wiki_page(db, user_id, int(page.id))


async def delete_wiki_page(db: AsyncSession, user_id: int, page_id: int) -> dict:
    page = await load_page(db, user_id, page_id)
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
    kb_id = int(page.kb_id)
    await db.delete(page)
    await db.commit()
    # 把其他页面里指向已删除页面的 [[page:id|...]] 还原成普通文字，避免死链。
    await linkify_wiki_pages(db, int(user_id), kb_id, add_missing=False)
    return {"pageId": int(page_id), "title": title, "deleted": True}


async def attach_wiki_image(
    db: AsyncSession,
    user_id: int,
    page_id: int,
    asset_key: str,
    quote: str = "",
) -> dict:
    page = await load_page(db, user_id, page_id)
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
    page = await load_page(db, user_id, page_id)
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
    pages = await _load_kb_pages(db, int(user_id), int(kb_id))
    page_ids = {int(page.id) for page in pages}
    doc_ids = sorted({int(doc_id) for page in pages for doc_id in (page.source_doc_ids or []) if str(doc_id).isdigit()})
    doc_names: dict[int, str] = {}
    if doc_ids:
        doc_rows = (
            await db.execute(
                select(RagDocument.id, RagDocument.file_name).where(RagDocument.id.in_(doc_ids))
            )
        ).all()
        doc_names = {int(row.id): str(row.file_name or "资料") for row in doc_rows}
    learning_by_page = await _wiki_learning_map(db, int(user_id), pages)
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
    degree = count_link_degree(links)
    nodes = [
        build_graph_node(page, doc_names, degree, learning_by_page.get(int(page.id)))
        for page in pages
    ]
    edges = build_graph_edges(links)
    # 即使页面图还没重建，也把正文里的内链即时画出来；前端不需要等一次写库。
    edges = build_mention_edges(pages, page_ids, edges)
    type_counts = count_by_page_type(nodes)
    learning_stats = count_learning_stats(nodes)
    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "pageCount": len(nodes),
            "linkCount": len(edges),
            "typeCounts": type_counts,
            "readCount": learning_stats["readCount"],
            "practicedCount": learning_stats["practicedCount"],
            "masteredCount": learning_stats["masteredCount"],
        },
    }


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
