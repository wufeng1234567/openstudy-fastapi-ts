"""规划建议快照 CRUD：只存建议，不存任务/完成态。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.study_plan import StudyPlanSnapshot
from app.services.study_advice_service import _humanize_advice_text

MAX_SNAPSHOTS_PER_USER = 50


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _humanize_advice(advice: Dict[str, Any], graph: Dict[str, Any]) -> Dict[str, Any]:
    """把历史快照里的内部术语也翻译成用户可读文本。"""
    if not isinstance(advice, dict):
        return {}
    title_map = {
        str(node.get("id")): str(node.get("title") or "")
        for node in (graph or {}).get("nodes") or []
        if isinstance(node, dict)
    }
    out = dict(advice)
    for key in ("title", "summary"):
        out[key] = _humanize_advice_text(out.get(key), title_map)
    phases = []
    for phase in advice.get("phases") or []:
        if not isinstance(phase, dict):
            continue
        item = dict(phase)
        for key in ("title", "goal", "reason"):
            item[key] = _humanize_advice_text(item.get(key), title_map)
        phases.append(item)
    out["phases"] = phases
    suggestions = []
    for suggestion in advice.get("suggestions") or []:
        if not isinstance(suggestion, dict):
            continue
        item = dict(suggestion)
        for key in ("title", "why"):
            item[key] = _humanize_advice_text(item.get(key), title_map)
        suggestions.append(item)
    out["suggestions"] = suggestions
    alternatives = []
    for alt in advice.get("alternatives") or []:
        if not isinstance(alt, dict):
            continue
        item = dict(alt)
        for key in ("title", "summary", "tradeoff"):
            item[key] = _humanize_advice_text(item.get(key), title_map)
        alternatives.append(item)
    out["alternatives"] = alternatives
    out["risks"] = [_humanize_advice_text(item, title_map) for item in (advice.get("risks") or [])]
    return out


def _serialize(row: StudyPlanSnapshot, *, include_payload: bool = True) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": int(row.id),
        "kbId": int(row.kb_id or 0),
        "title": str(row.title or ""),
        "source": str(row.source or "page"),
        "pinned": bool(row.pinned),
        "parentId": int(row.parent_id or 0),
        "createTime": row.create_time.isoformat(sep=" ", timespec="seconds") if row.create_time else "",
        "updateTime": row.update_time.isoformat(sep=" ", timespec="seconds") if row.update_time else "",
    }
    if include_payload:
        data["scope"] = row.scope_json or {}
        data["advice"] = _humanize_advice(row.advice_json or {}, row.graph_json or {})
        data["trace"] = row.trace_json or {}
        data["graph"] = row.graph_json or {}
    else:
        advice = _humanize_advice(row.advice_json or {}, {})
        data["summary"] = str(advice.get("summary") or "")
        data["phaseCount"] = len(advice.get("phases") or [])
    return data


async def save_snapshot(
    db: AsyncSession,
    *,
    user_id: int,
    kb_id: int = 0,
    title: str = "",
    scope: Optional[Dict[str, Any]] = None,
    advice: Optional[Dict[str, Any]] = None,
    trace: Optional[Dict[str, Any]] = None,
    graph: Optional[Dict[str, Any]] = None,
    parent_id: int = 0,
    source: str = "page",
) -> Dict[str, Any]:
    advice = advice or {}
    row = StudyPlanSnapshot(
        user_id=int(user_id),
        kb_id=int(kb_id or 0),
        title=str(title or advice.get("title") or "规划建议")[:160],
        scope_json=scope or advice.get("scope") or {},
        advice_json=advice,
        trace_json=trace or {},
        graph_json=graph or {},
        parent_id=int(parent_id) if int(parent_id or 0) > 0 else None,
        source=str(source or "page")[:16],
        pinned=0,
        deleted=0,
    )
    db.add(row)
    await db.flush()
    await prune_snapshots(db, user_id=int(user_id))
    await db.commit()
    await db.refresh(row)
    return _serialize(row, include_payload=True)


async def list_snapshots(
    db: AsyncSession,
    *,
    user_id: int,
    limit: int = 20,
    keyword: str = "",
) -> List[Dict[str, Any]]:
    query = select(StudyPlanSnapshot).where(
        StudyPlanSnapshot.user_id == int(user_id),
        StudyPlanSnapshot.deleted == 0,
    )
    if str(keyword or "").strip():
        query = query.where(StudyPlanSnapshot.title.like(f"%{str(keyword).strip()}%"))
    rows = (
        await db.execute(
            query.order_by(
                StudyPlanSnapshot.pinned.desc(),
                StudyPlanSnapshot.create_time.desc(),
                StudyPlanSnapshot.id.desc(),
            ).limit(max(1, min(int(limit or 20), 100)))
        )
    ).scalars().all()
    return [_serialize(row, include_payload=False) for row in rows]


async def get_snapshot(
    db: AsyncSession, *, user_id: int, snapshot_id: int
) -> Optional[Dict[str, Any]]:
    row = (
        await db.execute(
            select(StudyPlanSnapshot).where(
                StudyPlanSnapshot.id == int(snapshot_id),
                StudyPlanSnapshot.user_id == int(user_id),
                StudyPlanSnapshot.deleted == 0,
            )
        )
    ).scalars().first()
    return _serialize(row, include_payload=True) if row else None


async def update_snapshot(
    db: AsyncSession,
    *,
    user_id: int,
    snapshot_id: int,
    title: Optional[str] = None,
    pinned: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    row = (
        await db.execute(
            select(StudyPlanSnapshot).where(
                StudyPlanSnapshot.id == int(snapshot_id),
                StudyPlanSnapshot.user_id == int(user_id),
                StudyPlanSnapshot.deleted == 0,
            )
        )
    ).scalars().first()
    if not row:
        return None
    if title is not None:
        row.title = str(title).strip()[:160]
    if pinned is not None:
        row.pinned = 1 if pinned else 0
    row.update_time = datetime.now()
    await db.commit()
    await db.refresh(row)
    return _serialize(row, include_payload=False)


async def delete_snapshot(
    db: AsyncSession, *, user_id: int, snapshot_id: int
) -> bool:
    row = (
        await db.execute(
            select(StudyPlanSnapshot).where(
                StudyPlanSnapshot.id == int(snapshot_id),
                StudyPlanSnapshot.user_id == int(user_id),
                StudyPlanSnapshot.deleted == 0,
            )
        )
    ).scalars().first()
    if not row:
        return False
    row.deleted = 1
    row.update_time = datetime.now()
    await db.commit()
    return True


async def prune_snapshots(db: AsyncSession, *, user_id: int) -> None:
    """保留最近 50 条；置顶不参与淘汰。"""
    rows = (
        await db.execute(
            select(StudyPlanSnapshot)
            .where(
                StudyPlanSnapshot.user_id == int(user_id),
                StudyPlanSnapshot.deleted == 0,
            )
            .order_by(
                StudyPlanSnapshot.pinned.desc(),
                StudyPlanSnapshot.create_time.desc(),
                StudyPlanSnapshot.id.desc(),
            )
        )
    ).scalars().all()
    unpinned = [row for row in rows if not int(row.pinned or 0)]
    for row in unpinned[MAX_SNAPSHOTS_PER_USER:]:
        row.deleted = 1
        row.update_time = datetime.now()


__all__ = [
    "save_snapshot",
    "list_snapshots",
    "get_snapshot",
    "update_snapshot",
    "delete_snapshot",
    "prune_snapshots",
    "MAX_SNAPSHOTS_PER_USER",
]
