"""学习计划（StudyPlan）：把知识图谱与用户题库展开成每天可执行的任务。

设计边界
========
· **唯一计划对象**：知识图谱与题库共同生成一份按天任务；旧的考前计划、
  今日处方只作为历史参数/视图，不再各自维护一份“计划”。
· **零新表**：所有字段从 `build_learning_route()`、`diagnose()`、
  `_wiki_practice_bank()`、`user_practice_log`、`rag_wiki_page_learning` 实时推导。
· **不造假**：没有真实 page/bank/question target 的任务不排；没有题目就不排题；
  没有页面就不排站点。
· **完成判定只认真实行为**：题目任务看 `user_practice_log`，阅读/复习任务看
  `rag_wiki_page_learning.last_view_time`；前端勾选一律不算完成。
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import UserPracticeLog
from app.models.wiki import RagWikiPage
from app.services import study_diagnosis_service as sds
from app.services.rag import learning_route_service, wiki_service

DEFAULT_DAILY_MINUTES = 40
DEFAULT_HORIZON_DAYS = 7
MAX_HORIZON_DAYS = 30
MAX_STOPS = 8

TASK_MINUTES = {
    "read": 8,
    "section": 10,
    "practice": 12,
    "question": 8,
    "review": 6,
    "retest": 10,
    "mock": 20,
}

TASK_LABELS = {
    "read": "读主题页",
    "section": "读资料章节",
    "practice": "练同源题",
    "question": "攻克薄弱题",
    "review": "快速复习",
    "retest": "复测",
    "mock": "限时模拟",
}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_text(value: Any, limit: int = 160) -> str:
    text = str(value or "").strip().replace("\n", " ")
    return text[:limit]


def _clip(text: str, limit: int = 120) -> str:
    text = str(text or "").strip()
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _parse_day(value: Any, fallback: date) -> date:
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return fallback
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return fallback


def plan_dates(
    start: date,
    *,
    exam_date: Optional[date] = None,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    rest_days: Optional[Sequence[int]] = None,
) -> List[date]:
    """从 start 起生成可用学习日；考试日只到考前一天，休息日跳过。"""
    limit = max(1, min(int(horizon_days or DEFAULT_HORIZON_DAYS), MAX_HORIZON_DAYS))
    if exam_date is not None:
        if exam_date <= start:
            return [start]
        end = exam_date - timedelta(days=1)
    else:
        end = start + timedelta(days=limit - 1)
    rest = {int(d) for d in (rest_days or []) if 1 <= int(d) <= 7}
    result: List[date] = []
    cursor = start
    while cursor <= end:
        if cursor.isoweekday() not in rest:
            result.append(cursor)
        cursor += timedelta(days=1)
    return result or [start]


def _task(
    *,
    stop: Dict[str, Any],
    task_type: str,
    title: str,
    reason: str,
    minutes: int,
    target: Dict[str, Any],
    source_ref: str = "",
) -> Dict[str, Any]:
    page_id = _safe_int(stop.get("pageId"))
    seq = len(stop.get("_tasks") or []) + 1
    # 题库轴伪站点 pageId=0；用 sourceRef 保证多个题库的 task id 不撞。
    id_token = source_ref or str(page_id)
    task = {
        "id": f"t:{id_token}:{task_type}:{seq}",
        "type": task_type,
        "typeLabel": TASK_LABELS.get(task_type, "学习"),
        "title": title,
        "reason": _clip(reason, 200),
        "minutes": max(1, int(minutes)),
        "status": "next",
        "target": target,
        "pageId": page_id,
        "axis": "page" if page_id > 0 else "bank",
        "sourceNodeId": f"p:{page_id}" if page_id > 0 else "",
        "sourceRef": source_ref,
    }
    stop.setdefault("_tasks", []).append(task)
    return task


def _tasks_for_stop(
    stop: Dict[str, Any],
    *,
    diagnosis_items: Dict[int, Dict[str, Any]],
    exam_mode: bool,
) -> List[Dict[str, Any]]:
    """一个航线站点 → 0~3 个异构任务；没有真实 target 的任务不生成。"""
    page_id = _safe_int(stop.get("pageId"))
    title = _safe_text(stop.get("title") or "主题页", 80)
    learning = stop.get("learning") or {}
    views = _safe_int(learning.get("viewCount"))
    level = str(learning.get("level") or "")
    practice = stop.get("practice") or {}
    question_ids = [
        _safe_int(x)
        for x in (practice.get("questionIds") or [])
        if _safe_int(x) > 0
    ]
    weak_ids = [
        _safe_int(x)
        for x in (stop.get("weakQuestionIds") or [])
        if _safe_int(x) > 0
    ]
    tasks: List[Dict[str, Any]] = []
    reason = str(stop.get("reason") or "按知识图谱顺序继续学习")

    # 阅读：只有确实没读过才排，不把“已读”伪装成今天的新任务。
    if views == 0:
        tasks.append(
            _task(
                stop=stop,
                task_type="read",
                title=f"读《{title}》",
                reason=reason,
                minutes=TASK_MINUTES["read"],
                target={"kind": "page", "pageId": page_id},
                source_ref=f"page:{page_id}",
            )
        )

    # 练习：有同源题库才排；题量来自 QuestionSource，不凭空造题。
    if practice.get("bankId") and question_ids:
        tasks.append(
            _task(
                stop=stop,
                task_type="practice",
                title=f"练《{title}》同源题 {len(question_ids)} 道",
                reason=(
                    f"这 {len(question_ids)} 道题有真实资料锚点；练完会回写这个主题页的学习态"
                    + (f"，其中 {len(weak_ids)} 道正被诊断关注" if weak_ids else "")
                ),
                minutes=TASK_MINUTES["practice"],
                target={
                    "kind": "bank",
                    "pageId": page_id,
                    "bankId": _safe_int(practice.get("bankId")),
                    "bankName": str(practice.get("bankName") or "题库"),
                    "questionIds": question_ids,
                },
                source_ref=f"bank:{practice.get('bankId')}",
            )
        )

    # 具体薄弱题：最多 2 道，题干和 reason 都来自真实诊断；无锚点题不进站点。
    for question_id in weak_ids[:2]:
        item = diagnosis_items.get(question_id) or {}
        stem = _safe_text(item.get("questionText") or f"题目 {question_id}", 60)
        tasks.append(
            _task(
                stop=stop,
                task_type="question",
                title=f"攻克「{stem}」",
                reason=str(item.get("advice") or item.get("levelText") or "诊断显示这道题需要优先处理"),
                minutes=TASK_MINUTES["question"],
                target={
                    "kind": "question",
                    "pageId": page_id,
                    "questionId": question_id,
                    "bankId": _safe_int(item.get("bankId")) or None,
                },
                source_ref=f"q:{question_id}",
            )
        )

    # 已掌握的站只做快速复习，不排新练习。
    if not tasks and (level == "mastered" or str(stop.get("role") or "") == "review"):
        tasks.append(
            _task(
                stop=stop,
                task_type="review",
                title=f"复习《{title}》",
                reason="这一站已经掌握，按间隔重复做一次快速回忆即可",
                minutes=TASK_MINUTES["review"],
                target={"kind": "page", "pageId": page_id},
                source_ref=f"page:{page_id}",
            )
        )

    if exam_mode and tasks and not any(t["type"] == "practice" for t in tasks):
        # 考前模式只在有真实题库锚点的站点补一次复测；无题不造模拟卷。
        if question_ids:
            tasks.append(
                _task(
                    stop=stop,
                    task_type="retest",
                    title=f"复测《{title}》",
                    reason="考前模式：用同源题确认不是记住答案",
                    minutes=TASK_MINUTES["retest"],
                    target={
                        "kind": "bank",
                        "pageId": page_id,
                        "bankId": _safe_int(practice.get("bankId")),
                        "questionIds": question_ids[:8],
                    },
                    source_ref=f"bank:{practice.get('bankId')}",
                )
            )
    return tasks


def _tasks_for_banks(
    diagnosis_items: Dict[int, Dict[str, Any]],
    *,
    bank_ids: Optional[Sequence[int]] = None,
    covered_question_ids: Optional[set[int]] = None,
    max_banks: int = 2,
    max_per_bank: int = 2,
) -> List[Dict[str, Any]]:
    """题库轴任务：只排真实诊断出的薄弱题，不复制题库、不猜知识点。

    题库轴是「用户明确选择了题库」或「完全没有知识页」时的补位，不会把
    与当前资料夹无关的题库硬混进知识图谱计划。旧 `考前计划·` 自动题库
    默认跳过，避免历史副本重复占任务。
    """
    selected = {_safe_int(x) for x in (bank_ids or []) if _safe_int(x) > 0}
    covered = {_safe_int(x) for x in (covered_question_ids or set()) if _safe_int(x) > 0}
    grouped: Dict[int, List[Dict[str, Any]]] = {}
    bank_names: Dict[int, str] = {}
    for qid, item in (diagnosis_items or {}).items():
        question_id = _safe_int(qid)
        if question_id <= 0 or question_id in covered:
            continue
        level = str(item.get("level") or "")
        if level not in {"repeated_failure", "lapsing", "overdue", "due_soon"}:
            continue
        bid = _safe_int(item.get("bankId"))
        if bid <= 0:
            continue
        bank_name = str(item.get("bankName") or "题库")
        if selected:
            if bid not in selected:
                continue
        elif bank_name.startswith("考前计划·"):
            continue
        grouped.setdefault(bid, []).append(item)
        bank_names[bid] = bank_name

    ranked_banks = sorted(
        grouped,
        key=lambda bid: (-len(grouped[bid]), bid),
    )[: max(1, int(max_banks))]

    tasks: List[Dict[str, Any]] = []
    order = {
        "repeated_failure": 0,
        "lapsing": 1,
        "overdue": 2,
        "due_soon": 3,
    }
    for bid in ranked_banks:
        items = sorted(
            grouped[bid],
            key=lambda item: (
                order.get(str(item.get("level") or ""), 9),
                -_safe_int(item.get("attempts")),
                _safe_int(item.get("questionId")),
            ),
        )
        pseudo_stop: Dict[str, Any] = {
            "pageId": 0,
            "title": bank_names.get(bid, "题库"),
            "learning": {},
            "reason": "来自你真实练过的题库；这些题没有可反查的知识页锚点，按题库直接学，不伪造图谱归属",
        }
        for item in items[: max(1, int(max_per_bank))]:
            qid = _safe_int(item.get("questionId"))
            stem = _safe_text(item.get("questionText") or f"题目 {qid}", 60)
            task = _task(
                stop=pseudo_stop,
                task_type="question",
                title=f"攻克「{stem}」",
                reason=(
                    f"题库《{bank_names.get(bid, '题库')}》 · "
                    + str(item.get("advice") or item.get("levelText") or "诊断显示需要优先处理")
                ),
                minutes=TASK_MINUTES["question"],
                target={
                    "kind": "question",
                    "pageId": 0,
                    "questionId": qid,
                    "bankId": bid,
                    "bankName": bank_names.get(bid, "题库"),
                },
                source_ref=f"q:{qid}",
            )
            task["sourceNodeId"] = f"b:{bid}"
            tasks.append(task)
    return tasks


def _pack_days(
    tasks: Sequence[Dict[str, Any]],
    dates: Sequence[date],
    *,
    daily_minutes: int,
) -> List[Dict[str, Any]]:
    """按天装箱：不拆任务、不补假任务；装不下就顺延到下一个学习日。"""
    if not tasks or not dates:
        return []
    days: List[Dict[str, Any]] = []
    current_tasks: List[Dict[str, Any]] = []
    current_minutes = 0
    day_index = 0
    for task in tasks:
        minutes = int(task.get("minutes") or 0)
        if current_tasks and (
            current_minutes + minutes > max(1, daily_minutes)
            or len(current_tasks) >= 3
        ):
            days.append(
                {
                    "date": dates[min(day_index, len(dates) - 1)].isoformat(),
                    "minutes": current_minutes,
                    "tasks": current_tasks,
                }
            )
            day_index += 1
            current_tasks = []
            current_minutes = 0
        current_tasks.append(task)
        current_minutes += minutes
    if current_tasks:
        days.append(
            {
                "date": dates[min(day_index, len(dates) - 1)].isoformat(),
                "minutes": current_minutes,
                "tasks": current_tasks,
            }
        )
    # 若任务数超过可用学习日，后面的任务仍会落在最后一天（宁可当天多学一点，
    # 也不把真实任务丢掉）；`overloaded` 让 UI 如实提示。
    for day in days:
        day["overloaded"] = day["minutes"] > max(1, daily_minutes)
    return days


def _task_done(
    task: Dict[str, Any],
    *,
    start_dt: datetime,
    practice_logs: Dict[int, datetime],
    stops_by_page: Dict[int, Dict[str, Any]],
) -> bool:
    target = task.get("target") or {}
    kind = str(target.get("kind") or "")
    if kind in ("bank", "question", "mock"):
        qids = [int(x) for x in (target.get("questionIds") or []) if _safe_int(x) > 0]
        if target.get("questionId"):
            qids.append(int(target["questionId"]))
        return any(practice_logs.get(qid) and practice_logs[qid] >= start_dt for qid in set(qids))
    page_id = _safe_int(target.get("pageId") or task.get("pageId"))
    learning = (stops_by_page.get(page_id) or {}).get("learning") or {}
    last = str(learning.get("lastActivityTime") or learning.get("lastViewTime") or "")
    if not last:
        return False
    try:
        return datetime.fromisoformat(last) >= start_dt
    except ValueError:
        return False


def _apply_progress(
    days: List[Dict[str, Any]],
    *,
    start_dt: datetime,
    now: datetime,
    practice_logs: Dict[int, datetime],
    stops_by_page: Dict[int, Dict[str, Any]],
) -> Dict[str, Any]:
    today = now.date()
    total = done = 0
    planned_minutes = done_minutes = 0
    today_total = today_done = 0
    first_open: Optional[Dict[str, Any]] = None
    for day in days:
        day_date = _parse_day(day.get("date"), today)
        for task in day.get("tasks") or []:
            total += 1
            planned_minutes += int(task.get("minutes") or 0)
            task["status"] = "next"
            if _task_done(
                task,
                start_dt=start_dt,
                practice_logs=practice_logs,
                stops_by_page=stops_by_page,
            ):
                task["status"] = "done"
                done += 1
                done_minutes += int(task.get("minutes") or 0)
            elif first_open is None:
                first_open = task
                # 今天及以后的第一个未完成任务是 current；过去未完成标 blocked。
                task["status"] = "blocked" if day_date < today else "current"
            else:
                task["status"] = "next"
            if day_date == today:
                today_total += 1
                if task["status"] == "done":
                    today_done += 1

    # 站点状态：该站所有任务 done → done；含 current/blocked → current；否则 next。
    for page_id, stop in stops_by_page.items():
        stop_tasks = [t for day in days for t in (day.get("tasks") or []) if _safe_int(t.get("pageId")) == page_id]
        if not stop_tasks:
            continue
        if all(t.get("status") == "done" for t in stop_tasks):
            stop["status"] = "done"
        elif any(t.get("status") in ("current", "blocked") for t in stop_tasks):
            stop["status"] = "current"
        else:
            stop["status"] = "next"

    return {
        "doneTasks": done,
        "totalTasks": total,
        "doneMinutes": done_minutes,
        "plannedMinutes": planned_minutes,
        "todayDone": today_done,
        "todayTotal": today_total,
        "percent": round(done / total * 100, 1) if total else 0.0,
    }


def _plan_id(
    user_id: int,
    kb_id: int,
    intent: Dict[str, Any],
    window: Dict[str, Any],
    version: str = "",
) -> str:
    raw = json.dumps(
        {"u": user_id, "k": kb_id, "i": intent, "w": window, "v": version},
        ensure_ascii=False,
        sort_keys=True,
    )
    return "sp:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


async def _load_practice_logs(
    db: AsyncSession, user_id: int, start_dt: datetime
) -> Dict[int, datetime]:
    rows = (
        await db.execute(
            select(UserPracticeLog.question_id, UserPracticeLog.create_time)
            .where(
                UserPracticeLog.user_id == int(user_id),
                UserPracticeLog.create_time >= start_dt,
            )
        )
    ).all()
    result: Dict[int, datetime] = {}
    for question_id, created in rows:
        qid = _safe_int(question_id)
        if not qid or not created:
            continue
        current = result.get(qid)
        if current is None or created > current:
            result[qid] = created
    return result


async def build_study_plan(
    db: AsyncSession,
    user_id: int,
    kb_id: int,
    *,
    goal: str = "weakness",
    exam_date: Optional[date] = None,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    daily_minutes: int = DEFAULT_DAILY_MINUTES,
    rest_days: Optional[Sequence[int]] = None,
    focus_page_id: Optional[int] = None,
    doc_id: Optional[int] = None,
    section_indexes: Optional[Sequence[int]] = None,
    bank_ids: Optional[Sequence[int]] = None,
    mode: str = "balanced",
    since_ms: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """生成当前用户的学习计划（只读、确定性、无 LLM）。

    `since_ms` 是「这份计划从什么时候开始算完成」的客户端锚点：前端首次生成
    时写入 localStorage/sessionStorage，之后每次重拉都带回来。缺省用今天 00:00。
    完成判定永远用「计划生成后发生过」（`create_time >= since`），不按日期切分。
    """
    moment = now or datetime.now()
    today = moment.date()
    version = moment.strftime("%Y%m%d%H")
    strategy = "foundation" if goal == "foundation" else "explore" if goal == "explore" else "weakness"
    intent = {
        "goal": goal if goal in {"weakness", "foundation", "explore", "exam", "today", "sections"} else "weakness",
        "examDate": exam_date.isoformat() if exam_date else None,
        "kbId": int(kb_id),
        "docId": int(doc_id) if doc_id else 0,
        "sectionIndexes": [int(x) for x in (section_indexes or [])],
        "focusPageId": int(focus_page_id) if focus_page_id else 0,
        "bankIds": sorted({_safe_int(x) for x in (bank_ids or []) if _safe_int(x) > 0}),
        "mode": "sprint" if mode == "sprint" else "balanced",
    }
    dates = plan_dates(
        today,
        exam_date=exam_date,
        horizon_days=horizon_days,
        rest_days=rest_days,
    )
    window = {
        "start": today.isoformat(),
        "end": dates[-1].isoformat() if dates else today.isoformat(),
        "horizonDays": len(dates),
        "dailyMinutes": max(10, min(int(daily_minutes or DEFAULT_DAILY_MINUTES), 240)),
        "restDays": sorted({int(d) for d in (rest_days or []) if 1 <= int(d) <= 7}),
        "daysToExam": max(0, (exam_date - today).days) if exam_date else None,
        "sinceMs": int(since_ms) if since_ms else int(datetime.combine(today, time.min).timestamp() * 1000),
    }

    if int(kb_id or 0) > 0:
        route = await learning_route_service.build_learning_route(
            db,
            user_id,
            int(kb_id),
            max_stops=MAX_STOPS,
            focus_page_id=focus_page_id,
            strategy=strategy,
        )
    else:
        route = {
            "hasRoute": False,
            "reason": "这次只从题库安排学习",
            "mode": "bank",
            "stops": [],
            "edges": [],
            "stats": {"totalPages": 0},
            "degraded": {},
        }

    stops: List[Dict[str, Any]] = list(route.get("stops") or [])
    # 资料章节意图：只保留来源文档命中的主题页；命中为空时明示，不猜。
    if doc_id:
        page_rows = (
            await db.execute(
                select(RagWikiPage).where(
                    RagWikiPage.user_id == int(user_id),
                    RagWikiPage.kb_id == int(kb_id),
                    RagWikiPage.id.in_([int(s["pageId"]) for s in stops]),
                )
            )
        ).scalars().all()
        allowed = {
            int(page.id)
            for page in page_rows
            if int(doc_id) in [_safe_int(x) for x in (page.source_doc_ids or [])]
        }
        stops = [s for s in stops if _safe_int(s.get("pageId")) in allowed]
        if not stops:
            route["degraded"] = {**(route.get("degraded") or {}), "docFiltered": True}

    diagnosis = await sds.diagnose(db, int(user_id), limit=50)
    diagnosis_items = {
        _safe_int(item.get("questionId")): item
        for item in (diagnosis.get("items") or [])
        if _safe_int(item.get("questionId")) > 0
    }
    exam_mode = bool(exam_date)
    all_tasks: List[Dict[str, Any]] = []
    for stop in stops:
        all_tasks.extend(
            _tasks_for_stop(stop, diagnosis_items=diagnosis_items, exam_mode=exam_mode)
        )

    # 题库轴：用户明确选择了题库，或完全没有知识页时，才补真实薄弱题。
    # 不复制题库、不按题干猜知识点；没有锚点的题按题库直接进入计划。
    covered_question_ids = {
        _safe_int((task.get("target") or {}).get("questionId"))
        for task in all_tasks
        if _safe_int((task.get("target") or {}).get("questionId")) > 0
    }
    for task in all_tasks:
        target = task.get("target") or {}
        for qid in target.get("questionIds") or []:
            if _safe_int(qid) > 0:
                covered_question_ids.add(_safe_int(qid))
    bank_ids_selected = [
        _safe_int(x) for x in (bank_ids or []) if _safe_int(x) > 0
    ]
    if diagnosis_items and (bank_ids_selected or not stops):
        all_tasks.extend(
            _tasks_for_banks(
                diagnosis_items,
                bank_ids=bank_ids_selected or None,
                covered_question_ids=covered_question_ids,
                max_banks=2,
                max_per_bank=2,
            )
        )
    bank_task_count = sum(
        1
        for task in all_tasks
        if str((task.get("target") or {}).get("kind") or "") == "question"
        and _safe_int((task.get("target") or {}).get("pageId")) == 0
    )
    days = _pack_days(all_tasks, dates, daily_minutes=window["dailyMinutes"])

    start_dt = (
        datetime.fromtimestamp(int(since_ms) / 1000)
        if since_ms
        else datetime.combine(today, time.min)
    )
    practice_logs = await _load_practice_logs(db, user_id, start_dt)
    stops_by_page = {_safe_int(s.get("pageId")): s for s in stops}
    progress = _apply_progress(
        days,
        start_dt=start_dt,
        now=moment,
        practice_logs=practice_logs,
        stops_by_page=stops_by_page,
    )

    # 给路由站点剥掉内部临时字段，返回稳定 JSON。
    clean_stops = []
    for stop in stops:
        clean = {k: v for k, v in stop.items() if not k.startswith("_")}
        clean_stops.append(clean)

    degraded = dict(route.get("degraded") or {})
    degraded.update(
        {
            "pagesEmpty": not bool(stops),
            "noBankForStop": any(
                not (s.get("practice") or {}).get("bankId") and int(s.get("weakCount") or 0) > 0
                for s in stops
            ),
            "examTooSoon": bool(exam_date and (exam_date - today).days <= 3),
            "docFiltered": bool(doc_id and not stops),
            "bankOnly": bool(bank_task_count and not stops),
            "noKb": int(kb_id or 0) == 0,
            "bankOnlyPlan": bool(bank_task_count and not stops),
            "noBankSelected": not bool(bank_ids_selected),
            "noAnchoredMapping": bool(bank_task_count and not stops),
        }
    )
    route_stats = dict(route.get("stats") or {})
    route_stats.update(
        {
            "bankTaskCount": bank_task_count,
            "bankCount": len(
                {
                    _safe_int((task.get("target") or {}).get("bankId"))
                    for task in all_tasks
                    if _safe_int((task.get("target") or {}).get("bankId")) > 0
                }
            ),
        }
    )
    axis_summary = {
        "pageTasks": sum(1 for task in all_tasks if task.get("axis") == "page"),
        "bankTasks": sum(1 for task in all_tasks if task.get("axis") == "bank"),
        "questionTasks": sum(
            1
            for task in all_tasks
            if str((task.get("target") or {}).get("kind") or "") == "question"
        ),
    }
    if bank_task_count and not stops:
        headline = f"先从你的题库里攻克 {bank_task_count} 道薄弱题"
    elif bank_task_count:
        headline = f"知识图谱与题库一起排好了：{len(stops)} 个知识页 + {bank_task_count} 道题库薄弱题"
    else:
        headline = str(route.get("headline") or "按知识图谱为你排好了今天的学习")
    if not days:
        headline = "暂时没有可执行任务；先读一页或做一道题，计划会自己长出来。"

    return {
        "planId": _plan_id(user_id, kb_id, intent, window, version),
        "planVersion": version,
        "generatedAt": moment.isoformat(sep=" ", timespec="seconds"),
        "intent": intent,
        "bankIds": intent["bankIds"],
        "axisSummary": axis_summary,
        "window": window,
        "route": {
            "mode": (route.get("mode") or "fallback") if stops else ("bank-only" if bank_task_count else "empty"),
            "strategy": strategy,
            "strategyLabel": route.get("strategyLabel") or {"weakness": "补弱", "foundation": "打基础", "explore": "拓展"}.get(strategy, "补弱"),
            "headline": headline,
            "targetPageId": route.get("targetPageId") or 0,
            "targetTitle": route.get("targetTitle") or "",
            "stops": clean_stops,
            "edges": route.get("edges") or [],
            "stats": route_stats,
        },
        "days": days,
        "progress": progress,
        "sources": _sources(),
        "degraded": degraded,
    }


def _sources() -> Dict[str, str]:
    return {
        "diagnosis": "study_diagnosis_service.diagnose",
        "practiceLog": "user_practice_log",
        "questionSource": "question_source",
        "pageLearning": "rag_wiki_page_learning",
        "practiceBank": "wiki_service._wiki_practice_bank",
        "questionBank": "question_bank / question_main / user_practice_log",
        "route": "learning_route_service.build_learning_route",
        "generated": "request-time recompute; no plan table",
    }


__all__ = ["build_study_plan", "plan_dates", "MAX_STOPS"]
