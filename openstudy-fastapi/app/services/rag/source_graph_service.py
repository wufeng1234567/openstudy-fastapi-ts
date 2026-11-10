"""把非文档来源（题库/图片/笔记等）抽出的知识点落成实体与知识百科页。

文档来源已有 `knowledge_graph_service` + `wiki_service`；题库等来源没有 chunk，
不能走同一套文档页生成逻辑。这里把 `source_entity_service` 的总结结果落到：
  · `rag_graph_entity` + `rag_graph_relation`：真正进入知识图谱；
  · `rag_wiki_page` + `rag_wiki_page_link`：知识百科主题页和页面关系。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_graph import RagGraphEntity, RagGraphRelation
from app.models.wiki import RagWikiPage, RagWikiPageLink
from app.services import source_entity_service
from app.services.rag.wiki_merge_service import apply_source_to_page


def _norm(value: Any) -> str:
    text = re.sub(r"[\s\u3000]+", "", str(value or "").strip())
    return text.strip("《》\"'“”‘’（）()[]【】").lower()


def _clean(value: Any, limit: int = 600) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _link_type(kind: str) -> str:
    value = str(kind or "").strip().lower()
    if any(word in value for word in ("前置", "prerequisite", "依赖")):
        return "prerequisite"
    if any(word in value for word in ("对比", "contrast")):
        return "contrast"
    if any(word in value for word in ("包含", "组成", "part", "属于")):
        return "part_of"
    return "related"


async def _sync_entities(
    db: AsyncSession,
    *,
    user_id: int,
    kb_id: int,
    source_type: str,
    source_id: int,
    source_name: str,
    payload: Dict[str, Any],
) -> Dict[str, int]:
    entities = [item for item in (payload.get("entities") or []) if isinstance(item, dict) and item.get("name")]
    entity_by_name: Dict[str, RagGraphEntity] = {}
    for item in entities:
        name = _clean(item.get("name"), 200)
        normalized = _norm(name)
        if not normalized:
            continue
        row = (
            await db.execute(
                select(RagGraphEntity).where(
                    RagGraphEntity.user_id == int(user_id),
                    RagGraphEntity.kb_id == int(kb_id),
                    RagGraphEntity.normalized_name == normalized,
                )
            )
        ).scalar_one_or_none()
        description = _clean(item.get("description"), 1200)
        if row is None:
            row = RagGraphEntity(
                user_id=int(user_id),
                kb_id=int(kb_id),
                name=name,
                normalized_name=normalized,
                type=_clean(item.get("type") or "概念", 40),
                description=description,
                doc_ids=[],
                chunk_ids=[],
                mention_count=max(1, int(payload.get("question_count") or 1)),
            )
            db.add(row)
            await db.flush()
        else:
            if description and len(description) > len(row.description or ""):
                row.description = description
            row.type = _clean(item.get("type") or row.type or "概念", 40)
            row.mention_count = max(int(row.mention_count or 1), 1)
        entity_by_name[name] = row

    relations: List[RagGraphRelation] = []
    for item in payload.get("relations") or []:
        if not isinstance(item, dict):
            continue
        source = entity_by_name.get(_clean(item.get("source"), 200))
        target = entity_by_name.get(_clean(item.get("target"), 200))
        if not source or not target or source.id == target.id:
            continue
        relation_type = _clean(item.get("type") or "相关", 80)
        row = (
            await db.execute(
                select(RagGraphRelation).where(
                    RagGraphRelation.user_id == int(user_id),
                    RagGraphRelation.kb_id == int(kb_id),
                    RagGraphRelation.source_id == int(source.id),
                    RagGraphRelation.target_id == int(target.id),
                    RagGraphRelation.relation_type == relation_type,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = RagGraphRelation(
                user_id=int(user_id),
                kb_id=int(kb_id),
                source_id=int(source.id),
                target_id=int(target.id),
                relation_type=relation_type,
                description=_clean(item.get("description"), 600),
                strength=5,
                doc_ids=[],
                chunk_ids=[],
            )
            db.add(row)
        else:
            row.description = _clean(item.get("description") or row.description, 600)
        relations.append(row)

    # 给每个实体生成/更新一个知识百科主题页，图谱页才能看到对应节点。
    page_by_name: Dict[str, RagWikiPage] = {}
    for name, entity in entity_by_name.items():
        title = _clean(name, 255)
        normalized_title = _norm(title)
        page = (
            await db.execute(
                select(RagWikiPage).where(
                    RagWikiPage.user_id == int(user_id),
                    RagWikiPage.kb_id == int(kb_id),
                    RagWikiPage.normalized_title == normalized_title,
                )
            )
        ).scalar_one_or_none()
        if page is not None and str(page.generated_by or "") in {"manual", "agent"}:
            page_by_name[name] = page
            continue
        summary = _clean(entity.description, 600) or f"来自{source_name}的知识点"
        section_body = summary
        sections = [
            {
                "heading": "核心知识点",
                "body": section_body,
                "sourceChunkIds": [],
                "sourceType": source_type,
                "sourceId": int(source_id),
                "sourceName": source_name,
            }
        ]
        if page is None:
            page = RagWikiPage(
                user_id=int(user_id),
                kb_id=int(kb_id),
                title=title,
                normalized_title=normalized_title,
                page_type="concept",
                version=1,
                generated_by=f"source:{source_type}",
            )
            db.add(page)
            await db.flush()
        apply_source_to_page(
            page,
            title=title,
            page_type="concept",
            summary=summary,
            sections=sections,
            source_refs=[],
            source_chunk_ids=[],
            entity_ids=[int(entity.id)],
            source_type=source_type,
            source_id=int(source_id),
            source_name=source_name,
        )
        if not str(page.generated_by or ""):
            page.generated_by = f"source:{source_type}"
        page_by_name[name] = page

    # 页面关系来自真实抽取关系，不伪造。
    linked = 0
    for relation in relations:
        from_entity = next((item for item in entity_by_name.values() if int(item.id) == int(relation.source_id)), None)
        to_entity = next((item for item in entity_by_name.values() if int(item.id) == int(relation.target_id)), None)
        if not from_entity or not to_entity:
            continue
        from_page = page_by_name.get(str(from_entity.name))
        to_page = page_by_name.get(str(to_entity.name))
        if not from_page or not to_page or from_page.id == to_page.id:
            continue
        link_type = _link_type(relation.relation_type)
        exists = (
            await db.execute(
                select(RagWikiPageLink).where(
                    RagWikiPageLink.user_id == int(user_id),
                    RagWikiPageLink.kb_id == int(kb_id),
                    RagWikiPageLink.from_page_id == int(from_page.id),
                    RagWikiPageLink.to_page_id == int(to_page.id),
                    RagWikiPageLink.link_type == link_type,
                )
            )
        ).scalar_one_or_none()
        if not exists:
            db.add(
                RagWikiPageLink(
                    user_id=int(user_id),
                    kb_id=int(kb_id),
                    from_page_id=int(from_page.id),
                    to_page_id=int(to_page.id),
                    link_type=link_type,
                    weight=5,
                    source="source_graph",
                )
            )
            linked += 1
    await db.flush()
    return {
        "entities": len(entity_by_name),
        "relations": len(relations),
        "pages": len(page_by_name),
        "pageLinks": linked,
    }


async def sync_text_source(
    db: AsyncSession,
    *,
    user_id: int,
    kb_id: int,
    source_type: str,
    source_id: int,
    source_name: str,
    text: str,
) -> Dict[str, int]:
    """图片/网页/笔记等文本型来源的实体落库与主题页生成。"""
    payload = await source_entity_service.extract_entities_from_text(
        db,
        user_id=int(user_id),
        source_type=source_type,
        source_id=int(source_id),
        source_name=source_name,
        text=text,
        use_llm=True,
    )
    return await _sync_entities(
        db,
        user_id=int(user_id),
        kb_id=int(kb_id),
        source_type=source_type,
        source_id=int(source_id),
        source_name=source_name,
        payload=payload,
    )


async def sync_bank_graph(
    db: AsyncSession,
    *,
    user_id: int,
    kb_id: int,
    bank_id: int,
    source_name: str = "题库",
) -> Dict[str, int]:
    payload = await source_entity_service.extract_bank_entities(
        db,
        user_id=int(user_id),
        bank_id=int(bank_id),
        limit=200,
        chunk_size=20,
        use_llm=True,
    )
    return await _sync_entities(
        db,
        user_id=int(user_id),
        kb_id=int(kb_id),
        source_type="bank",
        source_id=int(bank_id),
        source_name=source_name,
        payload=payload,
    )


__all__ = ["sync_bank_graph", "sync_text_source"]
