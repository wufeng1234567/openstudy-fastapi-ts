"""题目 → 知识点（知识主题页）展示数据。

只使用真实的 `question_source` 锚点和 `rag_wiki_page.source_*` 关系；
没有锚点时返回空知识点，不按题干关键词猜知识点。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import QuestionBank, QuestionMain, QuestionSource
from app.models.wiki import RagWikiPage


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _page_maps(pages: Sequence[RagWikiPage]) -> tuple[Dict[int, Set[int]], Dict[int, Set[int]]]:
    doc_to_pages: Dict[int, Set[int]] = defaultdict(set)
    chunk_to_pages: Dict[int, Set[int]] = defaultdict(set)
    for page in pages:
        page_id = int(page.id)
        for value in page.source_doc_ids or []:
            doc_id = _safe_int(value)
            if doc_id > 0:
                doc_to_pages[doc_id].add(page_id)
        for value in page.source_chunk_ids or []:
            chunk_id = _safe_int(value)
            if chunk_id > 0:
                chunk_to_pages[chunk_id].add(page_id)
    return doc_to_pages, chunk_to_pages


def _page_source_kinds(page: RagWikiPage) -> List[str]:
    kinds: List[str] = []
    meta = page.generation_meta or {}
    sources = meta.get("sources") if isinstance(meta.get("sources"), list) else []
    for item in sources:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("sourceType") or "")
        if kind and kind not in kinds:
            kinds.append(kind)
    if not kinds and str(meta.get("sourceType") or ""):
        kinds.append(str(meta["sourceType"]))
    if not kinds:
        kinds.append("document")
    return kinds


async def load_question_knowledge(
    db: AsyncSession,
    *,
    user_id: int,
    question_ids: Sequence[int],
) -> Dict[int, Dict[str, Any]]:
    ids = sorted({_safe_int(item) for item in question_ids if _safe_int(item) > 0})
    if not ids:
        return {}
    # 权限口径与练习接口一致：自己的题库或公开题库。
    question_rows = (
        await db.execute(
            select(
                QuestionMain.id,
                QuestionMain.bank_id,
                QuestionMain.question_text,
                QuestionSource.doc_id,
                QuestionSource.chunk_id,
                QuestionSource.quote,
            )
            .select_from(
                QuestionMain.__table__.join(
                    QuestionBank.__table__, QuestionMain.bank_id == QuestionBank.id
                ).join(
                    QuestionSource.__table__,
                    QuestionSource.question_id == QuestionMain.id,
                    isouter=True,
                )
            )
            .where(
                QuestionMain.id.in_(ids),
                QuestionMain.status == "0",
                QuestionBank.status == "0",
                (QuestionBank.user_id == int(user_id)) | (QuestionBank.is_public != 0),
            )
        )
    ).all()
    pages = (
        await db.execute(
            select(RagWikiPage).where(
                RagWikiPage.user_id == int(user_id),
                RagWikiPage.status.in_(["ready", "stale"]),
            )
        )
    ).scalars().all()
    doc_to_pages, chunk_to_pages = _page_maps(pages)
    page_by_id = {int(page.id): page for page in pages}
    result: Dict[int, Dict[str, Any]] = {
        qid: {"questionId": qid, "questionText": "", "points": [], "source": None, "hasKnowledge": False}
        for qid in ids
    }
    for row in question_rows:
        qid = int(row.id)
        entry = result.setdefault(
            qid,
            {"questionId": qid, "questionText": "", "points": [], "source": None, "hasKnowledge": False},
        )
        entry["questionText"] = str(row.question_text or "")[:300]
        if row.doc_id is None and row.chunk_id is None:
            continue
        page_ids: Set[int] = set()
        if row.chunk_id is not None:
            page_ids.update(chunk_to_pages.get(_safe_int(row.chunk_id), set()))
        if not page_ids and row.doc_id is not None:
            page_ids.update(doc_to_pages.get(_safe_int(row.doc_id), set()))
        entry["source"] = {
            "docId": _safe_int(row.doc_id),
            "chunkId": _safe_int(row.chunk_id) if row.chunk_id is not None else 0,
            "quote": str(row.quote or ""),
        }
        for page_id in sorted(page_ids):
            page = page_by_id.get(page_id)
            if not page:
                continue
            if any(item.get("pageId") == page_id for item in entry["points"]):
                continue
            entry["points"].append(
                {
                    "pageId": page_id,
                    "title": str(page.title or "未命名知识点"),
                    "pageType": str(page.page_type or ""),
                    "sourceKinds": _page_source_kinds(page),
                }
            )
        entry["hasKnowledge"] = bool(entry["points"])
    return result
