"""题库知识点的快速读取层。

关联题库时 `source_graph_service.sync_bank_graph()` 已经在后台完成 LLM 抽取，
并把实体/关系写进 `rag_graph_entity` / `rag_graph_relation` 与主题页。这里优先
读取这些落库结果，避免用户第一次点「题库知识点」时再次同步调用 LLM。

若后台尚未完成，返回 `None`，由 API 触发一次后台抽取并快速返回 pending。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_graph import RagGraphEntity, RagGraphRelation
from app.models.question import QuestionMain
from app.models.wiki import RagWikiPage


def _bank_sources(page: RagWikiPage, bank_id: int) -> bool:
    meta = page.generation_meta or {}
    sources = meta.get("sources")
    if isinstance(sources, list):
        for item in sources:
            if not isinstance(item, dict):
                continue
            if str(item.get("sourceType") or "") == "bank" and int(item.get("sourceId") or 0) == int(bank_id):
                return True
    return (
        str(meta.get("sourceType") or "") == "bank"
        and int(meta.get("sourceId") or 0) == int(bank_id)
    )


async def _question_rows(db: AsyncSession, bank_id: int) -> List[Dict[str, Any]]:
    rows = (
        await db.execute(
            select(QuestionMain.id, QuestionMain.question_text, QuestionMain.analysis)
            .where(QuestionMain.bank_id == int(bank_id), QuestionMain.status == "0")
            .order_by(QuestionMain.id.asc())
            .limit(200)
        )
    ).all()
    return [
        {
            "id": int(row.id),
            "text": str(row.question_text or "")[:500],
            "analysis": str(row.analysis or "")[:500],
        }
        for row in rows
    ]


def _attach_question_ids(entities: List[Dict[str, Any]], questions: List[Dict[str, Any]]) -> None:
    for entity in entities:
        if entity.get("questionIds"):
            continue
        name = str(entity.get("name") or "").strip()
        entity["questionIds"] = (
            [
                int(question["id"])
                for question in questions
                if name and name in f"{question.get('text', '')} {question.get('analysis', '')}"
            ]
            if name
            else []
        )


async def load_bank_knowledge(
    db: AsyncSession,
    *,
    user_id: int,
    kb_id: int,
    bank_id: int,
) -> Optional[Dict[str, Any]]:
    """读取已落库的题库知识点；没有缓存时返回 None。"""
    pages = (
        await db.execute(
            select(RagWikiPage).where(
                RagWikiPage.user_id == int(user_id),
                RagWikiPage.kb_id == int(kb_id),
                RagWikiPage.status.in_(["ready", "stale"]),
            )
        )
    ).scalars().all()
    bank_pages = [page for page in pages if _bank_sources(page, bank_id)]
    if not bank_pages:
        return None

    # 优先读 sync_bank_graph 写入的完整快照（含 questionIds/relations）。
    for page in bank_pages:
        cached = (page.generation_meta or {}).get("bankKnowledge")
        if isinstance(cached, dict) and cached.get("entities"):
            questions = await _question_rows(db, bank_id)
            result = dict(cached)
            result["questions"] = questions
            result.setdefault("questionCount", len(questions))
            result.setdefault("degraded", {})
            result["degraded"] = {**result["degraded"], "cached": True}
            _attach_question_ids(result.get("entities") or [], questions)
            return result

    # 兼容旧数据：没有 bankKnowledge 快照时，从主题页实体和关系还原。
    entity_ids = {
        int(entity_id)
        for page in bank_pages
        for entity_id in (page.entity_ids or [])
        if str(entity_id).isdigit()
    }
    if not entity_ids:
        return None
    entities = (
        await db.execute(
            select(RagGraphEntity).where(
                RagGraphEntity.user_id == int(user_id),
                RagGraphEntity.kb_id == int(kb_id),
                RagGraphEntity.id.in_(entity_ids),
            )
        )
    ).scalars().all()
    if not entities:
        return None
    id_to_name = {int(entity.id): str(entity.name or "") for entity in entities}
    relations = (
        await db.execute(
            select(RagGraphRelation).where(
                RagGraphRelation.user_id == int(user_id),
                RagGraphRelation.kb_id == int(kb_id),
                RagGraphRelation.source_id.in_(entity_ids),
                RagGraphRelation.target_id.in_(entity_ids),
            )
        )
    ).scalars().all()
    questions = await _question_rows(db, bank_id)
    result_entities = [
        {
            "name": str(entity.name or ""),
            "type": str(entity.type or "概念"),
            "description": str(entity.description or ""),
            "mentionCount": int(entity.mention_count or 1),
        }
        for entity in entities
    ]
    _attach_question_ids(result_entities, questions)
    names = [item["name"] for item in result_entities[:8] if item["name"]]
    return {
        "summary": f"题库主要聚焦：{'、'.join(names)}。" if names else "",
        "questionCount": len(questions),
        "entities": result_entities,
        "relations": [
            {
                "source": id_to_name.get(int(relation.source_id), ""),
                "target": id_to_name.get(int(relation.target_id), ""),
                "type": str(relation.relation_type or "相关"),
                "description": str(relation.description or ""),
            }
            for relation in relations
        ],
        "questions": questions,
        "degraded": {"cached": True},
    }
