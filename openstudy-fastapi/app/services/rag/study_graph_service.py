"""学习图谱：把知识页与用户题库合成一张只读学习地图。

设计边界
========
· **节点只有两类**：`RagWikiPage`（知识页）与 `QuestionBank`（用户题库）。
· **题 → 页的边只来自 `QuestionSource` 的 doc/chunk 锚点**；没有锚点就不连线，
  绝不按题干关键词猜知识点。
· 题库节点可以独立存在：用户只有题库、没有知识百科时，图谱仍然可用。
· 所有统计（题数、练习次数、正确率、薄弱题）都来自真实表/真实诊断，
  不新表、不落库、不调 LLM。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import (
    QuestionBank,
    QuestionMain,
    QuestionSource,
    UserPracticeLog,
)
from app.models.wiki import RagWikiPage
from app.services import study_diagnosis_service as sds
from app.services.rag import learning_route_service, wiki_service
from app.services.rag.graph_contract import stable_edge_id

ATTENTION_LEVELS = ("repeated_failure", "lapsing", "overdue", "due_soon")
LEGACY_BANK_PREFIX = "考前计划·"
DEFAULT_BANK_LIMIT = 8
MAX_WEAK_QUESTIONS = 5


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_text(value: Any, limit: int = 120) -> str:
    text = str(value or "").strip().replace("\n", " ")
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def is_legacy_exam_bank(name: Any) -> bool:
    """旧考前计划自动生成的题库；保留数据，但不进入默认图谱/计划。"""
    return str(name or "").startswith(LEGACY_BANK_PREFIX)


def _item_sort_key(item: Dict[str, Any]) -> Tuple[int, int, int]:
    """薄弱题优先级：反复失守 > 一做就错 > 欠复习 > 该复习，同级看练习次数。"""
    order = {
        "repeated_failure": 0,
        "lapsing": 1,
        "overdue": 2,
        "due_soon": 3,
    }
    return (
        order.get(str(item.get("level") or ""), 9),
        -_safe_int(item.get("attempts")),
        _safe_int(item.get("questionId")),
    )


async def _load_question_count(
    db: AsyncSession, bank_ids: Sequence[int]
) -> Dict[int, int]:
    ids = [int(x) for x in bank_ids if int(x or 0) > 0]
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(QuestionMain.bank_id, func.count(QuestionMain.id))
            .where(
                QuestionMain.status == "0",
                QuestionMain.bank_id.in_(ids),
            )
            .group_by(QuestionMain.bank_id)
        )
    ).all()
    return {_safe_int(bank_id): int(count or 0) for bank_id, count in rows}


async def _load_bank_rows(
    db: AsyncSession,
    user_id: int,
    *,
    bank_ids: Optional[Sequence[int]] = None,
    include_legacy: bool = False,
    bank_limit: int = DEFAULT_BANK_LIMIT,
) -> List[Dict[str, Any]]:
    """读取“用户自己的 + 用户真实练过的”题库，并带真实练习统计。"""
    uid = int(user_id)
    wanted = {int(x) for x in (bank_ids or []) if _safe_int(x) > 0}
    own_rows = (
        await db.execute(
            select(QuestionBank).where(
                QuestionBank.user_id == uid,
                QuestionBank.status == "0",
            )
        )
    ).scalars().all()
    practice_rows = (
        await db.execute(
            select(
                QuestionBank.id,
                QuestionBank.bank_name,
                QuestionBank.subject,
                func.count(func.distinct(UserPracticeLog.question_id)).label("practiced_count"),
                func.count(UserPracticeLog.log_id).label("attempt_count"),
                func.sum(UserPracticeLog.is_correct).label("correct_count"),
                func.max(UserPracticeLog.create_time).label("last_practice"),
            )
            .select_from(
                UserPracticeLog.__table__.join(
                    QuestionMain.__table__,
                    UserPracticeLog.question_id == QuestionMain.id,
                ).join(
                    QuestionBank.__table__,
                    QuestionMain.bank_id == QuestionBank.id,
                )
            )
            .where(
                UserPracticeLog.user_id == uid,
                QuestionBank.status == "0",
                QuestionMain.status == "0",
            )
            .group_by(QuestionBank.id, QuestionBank.bank_name, QuestionBank.subject)
        )
    ).all()

    merged: Dict[int, Dict[str, Any]] = {}
    for bank in own_rows:
        bid = int(bank.id)
        merged[bid] = {
            "bankId": bid,
            "bankName": str(bank.bank_name or "题库"),
            "subject": str(bank.subject or ""),
            "owned": True,
            "practicedQuestionCount": 0,
            "attemptCount": 0,
            "correctCount": 0,
            "lastPracticeTime": "",
        }
    for row in practice_rows:
        bid = int(row.id)
        entry = merged.setdefault(
            bid,
            {
                "bankId": bid,
                "bankName": str(row.bank_name or "题库"),
                "subject": str(row.subject or ""),
                "owned": False,
                "practicedQuestionCount": 0,
                "attemptCount": 0,
                "correctCount": 0,
                "lastPracticeTime": "",
            },
        )
        entry["practicedQuestionCount"] = int(row.practiced_count or 0)
        entry["attemptCount"] = int(row.attempt_count or 0)
        entry["correctCount"] = int(row.correct_count or 0)
        entry["lastPracticeTime"] = (
            row.last_practice.isoformat(sep=" ", timespec="seconds")
            if row.last_practice
            else ""
        )

    if wanted:
        merged = {bid: item for bid, item in merged.items() if bid in wanted}
    if not include_legacy:
        # 显式关联/传入的题库即使名字像旧考前计划，也要保留；不能因为旧命名
        # 规则把用户在资料夹里主动关联的题库静默过滤掉。
        merged = {
            bid: item
            for bid, item in merged.items()
            if bid in wanted or not is_legacy_exam_bank(item["bankName"])
        }

    counts = await _load_question_count(db, list(merged.keys()))
    result: List[Dict[str, Any]] = []
    for bid, item in merged.items():
        question_count = int(counts.get(bid, 0))
        if question_count <= 0:
            continue
        attempts = int(item["attemptCount"])
        correct = int(item["correctCount"])
        item["questionCount"] = question_count
        item["accuracy"] = round(correct / attempts * 100, 1) if attempts else 0.0
        item["legacy"] = is_legacy_exam_bank(item["bankName"])
        result.append(item)

    result.sort(
        key=lambda item: (
            -int(item["attemptCount"]),
            -int(item["questionCount"]),
            int(item["bankId"]),
        )
    )
    limit = max(1, min(int(bank_limit or DEFAULT_BANK_LIMIT), 30))
    return result[:limit]


def _page_source_maps(pages: Sequence[RagWikiPage]) -> Tuple[Dict[int, Set[int]], Dict[int, Set[int]]]:
    doc_to_pages: Dict[int, Set[int]] = defaultdict(set)
    chunk_to_pages: Dict[int, Set[int]] = defaultdict(set)
    for page in pages:
        page_id = int(page.id)
        for doc_id in page.source_doc_ids or []:
            if _safe_int(doc_id) > 0:
                doc_to_pages[_safe_int(doc_id)].add(page_id)
        for chunk_id in page.source_chunk_ids or []:
            if _safe_int(chunk_id) > 0:
                chunk_to_pages[_safe_int(chunk_id)].add(page_id)
    return doc_to_pages, chunk_to_pages


async def _attach_bank_page_edges(
    db: AsyncSession,
    user_id: int,
    *,
    pages: Sequence[RagWikiPage],
    banks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """真实 QuestionSource 锚点 → 题库节点到知识页节点的桥；没有就不连。"""
    if not pages or not banks:
        return []
    bank_ids = [int(item["bankId"]) for item in banks]
    doc_to_pages, chunk_to_pages = _page_source_maps(pages)
    rows = (
        await db.execute(
            select(
                QuestionSource.question_id,
                QuestionSource.doc_id,
                QuestionSource.chunk_id,
                QuestionMain.bank_id,
            )
            .select_from(
                QuestionSource.__table__.join(
                    QuestionMain.__table__,
                    QuestionSource.question_id == QuestionMain.id,
                )
            )
            .where(
                QuestionSource.user_id == int(user_id),
                QuestionMain.status == "0",
                QuestionMain.bank_id.in_(bank_ids),
            )
        )
    ).all()

    page_banks: Dict[int, Set[int]] = defaultdict(set)
    bank_pages: Dict[int, Dict[int, int]] = defaultdict(dict)
    bank_qids: Dict[int, Set[int]] = defaultdict(set)
    for row in rows:
        qid = _safe_int(row.question_id)
        bid = _safe_int(row.bank_id)
        if qid <= 0 or bid <= 0:
            continue
        target_pages: Set[int] = set()
        if row.chunk_id is not None:
            target_pages.update(chunk_to_pages.get(_safe_int(row.chunk_id), set()))
        if not target_pages and row.doc_id is not None:
            target_pages.update(doc_to_pages.get(_safe_int(row.doc_id), set()))
        if not target_pages:
            continue
        bank_qids[bid].add(qid)
        for page_id in target_pages:
            bank_pages[bid][page_id] = int(bank_pages[bid].get(page_id, 0)) + 1
            page_banks[page_id].add(bid)

    edges: List[Dict[str, Any]] = []
    for bank in banks:
        bid = int(bank["bankId"])
        page_map = bank_pages.get(bid) or {}
        bank["mappedQuestionCount"] = len(bank_qids.get(bid, set()))
        bank["pageIds"] = sorted(page_map.keys())
        for page_id, weight in sorted(page_map.items()):
            edges.append(
                {
                    "id": stable_edge_id("question_source", f"bank:{bid}", f"page:{page_id}"),
                    "source": f"bank:{bid}",
                    "target": f"page:{page_id}",
                    "type": "question_source",
                    "kind": "question_source",
                    "weight": int(weight),
                }
            )
    for page in pages:
        page_id = int(page.id)
        bank_ids_for_page = sorted(page_banks.get(page_id, set()))
        if bank_ids_for_page:
            # 页面节点上带一份只读引用；前端可显示“这个知识页有同源题库”。
            setattr(page, "_study_bank_ids", bank_ids_for_page)
    return edges


def _bank_weak_questions(
    diagnosis_items: Sequence[Dict[str, Any]],
    *,
    limit: int = MAX_WEAK_QUESTIONS,
) -> Dict[int, List[Dict[str, Any]]]:
    grouped: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for item in diagnosis_items:
        if str(item.get("level") or "") not in ATTENTION_LEVELS:
            continue
        bid = _safe_int(item.get("bankId"))
        if bid <= 0:
            continue
        grouped[bid].append(
            {
                "questionId": _safe_int(item.get("questionId")),
                "questionText": _safe_text(item.get("questionText") or "", 160),
                "level": str(item.get("level") or ""),
                "levelText": str(item.get("levelText") or ""),
                "accuracy": round(_safe_float(item.get("accuracy")), 1),
                "attempts": _safe_int(item.get("attempts")),
                "advice": _safe_text(item.get("advice") or "", 160),
                "bankId": bid,
                "bankName": str(item.get("bankName") or ""),
            }
        )
    for bid in grouped:
        grouped[bid].sort(key=_item_sort_key)
    return {bid: items[:limit] for bid, items in grouped.items()}


def _count_weak(questions: Sequence[Dict[str, Any]]) -> int:
    return sum(1 for item in questions if str(item.get("level") or "") in ATTENTION_LEVELS)


def _weak_count_by_bank(diagnosis_items: Sequence[Dict[str, Any]]) -> Dict[int, int]:
    counts: Dict[int, int] = defaultdict(int)
    for item in diagnosis_items:
        if str(item.get("level") or "") not in ATTENTION_LEVELS:
            continue
        bank_id = _safe_int(item.get("bankId"))
        if bank_id > 0:
            counts[bank_id] += 1
    return dict(counts)


async def build_study_graph(
    db: AsyncSession,
    user_id: int,
    kb_id: int = 0,
    *,
    bank_ids: Optional[Sequence[int]] = None,
    include_legacy: bool = False,
    bank_limit: int = DEFAULT_BANK_LIMIT,
    weak_limit: int = MAX_WEAK_QUESTIONS,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """构建“知识页 + 题库”的统一学习图谱（只读）。"""
    moment = now or datetime.now()
    pages: List[RagWikiPage] = []
    wiki_graph: Dict[str, Any] = {"nodes": [], "edges": [], "stats": {}}
    if int(kb_id or 0) > 0:
        pages = list(
            (
                await db.execute(
                    select(RagWikiPage).where(
                        RagWikiPage.user_id == int(user_id),
                        RagWikiPage.kb_id == int(kb_id),
                        RagWikiPage.status.in_(
                            [wiki_service.WIKI_READY, wiki_service.WIKI_STALE]
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        wiki_graph = await wiki_service.get_wiki_graph(db, int(user_id), int(kb_id))

    diagnosis = await sds.diagnose(db, int(user_id), limit=200)
    diagnosis_items = list(diagnosis.get("items") or [])
    page_signals, _ = await learning_route_service._load_diagnosis_page_signals(
        db, int(user_id), pages, diagnosis=diagnosis
    )
    banks = await _load_bank_rows(
        db,
        int(user_id),
        bank_ids=bank_ids,
        include_legacy=include_legacy,
        bank_limit=bank_limit,
    )
    bank_edges = await _attach_bank_page_edges(
        db, int(user_id), pages=pages, banks=banks
    )
    weak_by_bank = _bank_weak_questions(diagnosis_items, limit=weak_limit)
    weak_count_by_bank = _weak_count_by_bank(diagnosis_items)

    page_nodes: List[Dict[str, Any]] = []
    for node in wiki_graph.get("nodes") or []:
        page_id = _safe_int(node.get("pageId"))
        signal = page_signals.get(page_id) or {}
        page = next((item for item in pages if int(item.id) == page_id), None)
        page_nodes.append(
            {
                **node,
                "kind": "page",
                "weakCount": int(signal.get("weakCount") or 0),
                "weakQuestionIds": [int(x) for x in (signal.get("questionIds") or [])],
                "bankIds": sorted(
                    {int(x) for x in getattr(page, "_study_bank_ids", []) if _safe_int(x)}
                )
                if page is not None
                else [],
            }
        )

    bank_nodes: List[Dict[str, Any]] = []
    for bank in banks:
        bid = int(bank["bankId"])
        weak = weak_by_bank.get(bid, [])
        bank_nodes.append(
            {
                "id": f"bank:{bid}",
                "kind": "bank",
                "bankId": bid,
                "title": str(bank["bankName"]),
                "subject": str(bank.get("subject") or ""),
                "questionCount": int(bank.get("questionCount") or 0),
                "practicedQuestionCount": int(bank.get("practicedQuestionCount") or 0),
                "attemptCount": int(bank.get("attemptCount") or 0),
                "accuracy": round(_safe_float(bank.get("accuracy")), 1),
                "weakCount": int(weak_count_by_bank.get(bid, _count_weak(weak))),
                "weakQuestions": weak,
                "mappedQuestionCount": int(bank.get("mappedQuestionCount") or 0),
                "pageIds": [int(x) for x in (bank.get("pageIds") or [])],
                "lastPracticeTime": str(bank.get("lastPracticeTime") or ""),
                "legacy": bool(bank.get("legacy")),
                "owned": bool(bank.get("owned")),
            }
        )

    nodes = page_nodes + bank_nodes
    edges = list(wiki_graph.get("edges") or []) + bank_edges
    page_count = len(page_nodes)
    bank_count = len(bank_nodes)
    mapped_count = sum(int(node.get("mappedQuestionCount") or 0) for node in bank_nodes)
    stats = {
        "pageCount": page_count,
        "bankCount": bank_count,
        "edgeCount": len(edges),
        "prerequisiteEdgeCount": sum(
            1 for edge in (wiki_graph.get("edges") or []) if edge.get("type") == "prerequisite"
        ),
        "linkedBankCount": sum(1 for node in bank_nodes if node.get("pageIds")),
        "unlinkedBankCount": sum(1 for node in bank_nodes if not node.get("pageIds")),
        "questionCount": sum(int(node.get("questionCount") or 0) for node in bank_nodes),
        "practicedQuestionCount": sum(
            int(node.get("practicedQuestionCount") or 0) for node in bank_nodes
        ),
        "mappedQuestionCount": mapped_count,
        "weakQuestionCount": sum(int(node.get("weakCount") or 0) for node in bank_nodes),
    }
    return {
        "kbId": int(kb_id or 0),
        "generatedAt": moment.isoformat(sep=" ", timespec="seconds"),
        "nodes": nodes,
        "edges": edges,
        "banks": bank_nodes,
        "stats": stats,
        "degraded": {
            "pagesEmpty": page_count == 0,
            "banksEmpty": bank_count == 0,
            "noQuestionSource": bank_count > 0 and mapped_count == 0,
            "noPracticeData": not bool(diagnosis.get("hasData")),
        },
        "sources": {
            "pages": "rag_wiki_page / rag_wiki_page_link",
            "learning": "rag_wiki_page_learning + user_practice_log",
            "banks": "question_bank / question_main / user_practice_log",
            "questionSource": "question_source",
            "diagnosis": "study_diagnosis_service.diagnose",
            "generated": "request-time; no graph table",
        },
    }


async def map_questions_to_pages(
    db: AsyncSession,
    user_id: int,
    question_ids: Sequence[int],
    *,
    kb_id: int = 0,
) -> List[Dict[str, Any]]:
    """题 → 真实资料锚点 → 知识页；无锚点/无页面时如实返回空。"""
    ids = sorted({_safe_int(x) for x in question_ids if _safe_int(x) > 0})
    if not ids:
        return []
    pages: List[RagWikiPage] = []
    if int(kb_id or 0) > 0:
        pages = list(
            (
                await db.execute(
                    select(RagWikiPage).where(
                        RagWikiPage.user_id == int(user_id),
                        RagWikiPage.kb_id == int(kb_id),
                        RagWikiPage.status.in_(
                            [wiki_service.WIKI_READY, wiki_service.WIKI_STALE]
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
    doc_to_pages, chunk_to_pages = _page_source_maps(pages)
    rows = (
        await db.execute(
            select(
                QuestionSource.question_id,
                QuestionSource.doc_id,
                QuestionSource.chunk_id,
                QuestionSource.quote,
                QuestionMain.bank_id,
                QuestionMain.question_text,
            )
            .select_from(
                QuestionSource.__table__.join(
                    QuestionMain.__table__,
                    QuestionSource.question_id == QuestionMain.id,
                )
            )
            .where(
                QuestionSource.user_id == int(user_id),
                QuestionSource.question_id.in_(ids),
                QuestionMain.status == "0",
            )
        )
    ).all()
    source_by_id = {_safe_int(row.question_id): row for row in rows}
    question_rows = (
        await db.execute(
            select(QuestionMain.id, QuestionMain.bank_id, QuestionMain.question_text)
            .select_from(
                QuestionMain.__table__.join(
                    QuestionBank.__table__, QuestionMain.bank_id == QuestionBank.id
                )
            )
            .where(
                QuestionMain.id.in_(ids),
                QuestionMain.status == "0",
                QuestionBank.status == "0",
                or_(
                    QuestionBank.user_id == int(user_id),
                    QuestionBank.is_public != 0,
                ),
            )
        )
    ).all()
    question_by_id = {
        _safe_int(row.id): {
            "bankId": _safe_int(row.bank_id),
            "questionText": _safe_text(row.question_text or "", 180),
        }
        for row in question_rows
    }
    result: List[Dict[str, Any]] = []
    for qid in ids:
        row = source_by_id.get(qid)
        question_meta = question_by_id.get(qid) or {}
        if row is None:
            result.append(
                {
                    "questionId": qid,
                    "bankId": int(question_meta.get("bankId") or 0),
                    "questionText": str(question_meta.get("questionText") or ""),
                    "anchored": False,
                    "pageId": 0,
                    "pageIds": [],
                    "anchor": None,
                }
            )
            continue
        page_ids: Set[int] = set()
        if row.chunk_id is not None:
            page_ids.update(chunk_to_pages.get(_safe_int(row.chunk_id), set()))
        if not page_ids and row.doc_id is not None:
            page_ids.update(doc_to_pages.get(_safe_int(row.doc_id), set()))
        result.append(
            {
                "questionId": qid,
                "bankId": _safe_int(row.bank_id),
                "questionText": _safe_text(row.question_text or "", 180),
                "anchored": True,
                "pageId": min(page_ids) if page_ids else 0,
                "pageIds": sorted(page_ids),
                "anchor": {
                    "docId": _safe_int(row.doc_id),
                    "chunkId": _safe_int(row.chunk_id) if row.chunk_id is not None else 0,
                    "quote": _safe_text(row.quote or "", 160),
                },
            }
        )
    return result


async def get_study_bank(
    db: AsyncSession,
    user_id: int,
    bank_id: int,
    *,
    kb_id: int = 0,
    now: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """单题库详情：图谱节点 + 真实薄弱题。"""
    graph = await build_study_graph(
        db,
        int(user_id),
        int(kb_id or 0),
        bank_ids=[int(bank_id)],
        include_legacy=True,
        bank_limit=1,
        now=now,
    )
    return next(
        (item for item in graph.get("banks") or [] if int(item["bankId"]) == int(bank_id)),
        None,
    )


async def search_study_graph(
    db: AsyncSession,
    user_id: int,
    query: str,
    *,
    kb_id: int = 0,
    limit: int = 8,
) -> Dict[str, Any]:
    """在知识页标题/摘要、题库名称/科目、题目题干中做真实文本搜索。"""
    q = str(query or "").strip()
    if not q:
        return {"query": q, "pages": [], "banks": [], "questions": []}
    lim = max(1, min(int(limit or 8), 20))
    graph = await build_study_graph(
        db,
        int(user_id),
        int(kb_id or 0),
        include_legacy=False,
        bank_limit=30,
    )
    like = f"%{q}%"
    pages = [
        {
            "pageId": int(node["pageId"]),
            "title": node["title"],
            "summary": node.get("summary") or "",
            "pageType": node.get("pageType") or "",
            "learning": node.get("learning") or {},
        }
        for node in graph.get("nodes") or []
        if node.get("kind") == "page"
        and (
            q.lower() in str(node.get("title") or "").lower()
            or q.lower() in str(node.get("summary") or "").lower()
        )
    ][:lim]
    banks = [
        {
            "bankId": int(node["bankId"]),
            "bankName": node["title"],
            "subject": node.get("subject") or "",
            "questionCount": int(node.get("questionCount") or 0),
            "weakCount": int(node.get("weakCount") or 0),
        }
        for node in graph.get("banks") or []
        if q.lower() in str(node.get("title") or "").lower()
        or q.lower() in str(node.get("subject") or "").lower()
    ][:lim]

    bank_ids = [int(item["bankId"]) for item in graph.get("banks") or []]
    questions: List[Dict[str, Any]] = []
    if bank_ids:
        rows = (
            await db.execute(
                select(
                    QuestionMain.id,
                    QuestionMain.bank_id,
                    QuestionMain.question_text,
                    QuestionMain.difficulty,
                    QuestionBank.bank_name,
                )
                .select_from(
                    QuestionMain.__table__.join(
                        QuestionBank.__table__, QuestionMain.bank_id == QuestionBank.id
                    )
                )
                .where(
                    QuestionMain.status == "0",
                    QuestionBank.status == "0",
                    QuestionMain.bank_id.in_(bank_ids),
                    or_(
                        QuestionMain.question_text.ilike(like),
                        QuestionMain.analysis.ilike(like),
                    ),
                )
                .order_by(QuestionMain.id.asc())
                .limit(lim)
            )
        ).all()
        for row in rows:
            questions.append(
                {
                    "questionId": int(row.id),
                    "bankId": int(row.bank_id),
                    "bankName": str(row.bank_name or ""),
                    "questionText": _safe_text(row.question_text or "", 180),
                    "difficulty": int(row.difficulty or 1),
                }
            )
    return {"query": q, "pages": pages, "banks": banks, "questions": questions}


__all__ = [
    "build_study_graph",
    "get_study_bank",
    "map_questions_to_pages",
    "search_study_graph",
    "is_legacy_exam_bank",
    "ATTENTION_LEVELS",
]
