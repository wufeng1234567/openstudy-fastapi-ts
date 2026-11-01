"""考前倒计时路线图。

用户输入考试名、考试日期、开始复习日期、每周休息日、每天可学多久；
系统按逐题诊断结果倒排 —— 不是「生成一份漂亮计划」，而是每天告诉用户
先做哪几道题、为什么。

规划逻辑（确定性，不调用大模型）：
  · 距考试 > 10 天：补地基 → 还债 + 巩固 → 全真模拟
  · 距考试 4~10 天：还债 + 巩固 → 模拟
  · 距考试 ≤ 3 天：只做「错题回看 + 一套模拟」，不再开新战线

任何时候题库不够时，任务数量会自动收缩到真实可用的题，不凑数。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import study_diagnosis_service as sds

DELETED_PLACEHOLDER = "（题目内容已不可用，可能已被删除）"

MODE_RATIOS = {
    # (补地基, 还债+巩固, 全真模拟)
    "balanced": (0.35, 0.40, 0.25),
    "sprint": (0.15, 0.45, 0.40),
}


def _pick(items: List[Dict[str, Any]], levels: set[str], used: set[int], count: int) -> List[Dict[str, Any]]:
    picked: List[Dict[str, Any]] = []
    for item in items:
        qid = int(item.get("questionId") or 0)
        if qid in used or item.get("level") not in levels:
            continue
        picked.append(item)
        used.add(qid)
        if len(picked) >= count:
            break
    return picked


def _task(item: Dict[str, Any], verb: str, minutes: int, note: str = "") -> Dict[str, Any]:
    return {
        "type": "question",
        "questionId": int(item.get("questionId") or 0),
        "subject": item.get("subject") or "",
        # 不在这里截断题干：截断会切坏 LaTeX，前端用 CSS 两行省略
        "title": f"{verb}「{item.get('questionText') or ''}」",
        "detail": note or (item.get("advice") or ""),
        "minutes": minutes,
    }


def _phase(key: str, title: str, goal: str, dates: List[date], color: str) -> Dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "goal": goal,
        "start": dates[0].isoformat() if dates else "",
        "end": dates[-1].isoformat() if dates else "",
        "days": len(dates),
        "color": color,
    }


def _take(pool: List[Dict[str, Any]], cursor: int, count: int) -> tuple[List[Dict[str, Any]], int]:
    """从池子里循环取题：错题本来就需要重复，取完一轮再从头上。"""
    if not pool:
        return [], cursor
    picked = [pool[(cursor + i) % len(pool)] for i in range(min(count, len(pool)))]
    return picked, (cursor + count) % len(pool)


def _study_dates(start_date: date, exam_date: date, rest_days: List[int]) -> List[date]:
    """开始日到考前一天，排除用户选择的每周休息日。"""
    dates: List[date] = []
    cursor = start_date
    while cursor < exam_date:
        if cursor.isoweekday() not in rest_days:
            dates.append(cursor)
        cursor += timedelta(days=1)
    return dates


def _fallback_subject(subjects: List[str], items: List[Dict[str, Any]]) -> str:
    if subjects:
        return subjects[0]
    return items[0].get("subject") if items else ""


def _build_days(
    items: List[Dict[str, Any]],
    exam_date: date,
    start_date: date,
    daily_minutes: int,
    subjects: List[str],
    rest_days: List[int],
    mode: str,
    profile: str = "standard",
    attention_count: int = 0,
) -> Dict[str, Any]:
    study_dates = _study_dates(start_date, exam_date, rest_days)
    if not study_dates:
        raise ValueError("按当前的开始日期和休息日设置，没有可安排的学习日")

    # 智能化：薄弱题很少时不要硬排 30 天重复任务。
    # · 没有明显薄弱题：只保留 3 个巩固/模拟节点；
    # · 1~3 道薄弱题：做短而密的专项计划，解决后再重新评估。
    if profile == "maintenance" and len(study_dates) > 3:
        study_dates = [study_dates[0], study_dates[len(study_dates) // 2], study_dates[-1]]
    elif profile == "micro":
        limit = min(len(study_dates), max(3, attention_count * 2 + 1))
        study_dates = study_dates[:limit]

    total_days = len(study_dates)
    used: set[int] = set()

    def in_scope(item: Dict[str, Any]) -> bool:
        return not subjects or str(item.get("subject") or "") in subjects

    foundation_pool = [
        i for i in items
        if i.get("level") in {"repeated_failure", "lapsing"} and in_scope(i)
    ]
    review_pool = [
        i for i in items
        if i.get("level") in {"overdue", "due_soon"} and in_scope(i)
    ]
    steady_pool = [
        i for i in items
        if i.get("level") in {"on_track", "fresh"} and in_scope(i)
    ]

    if total_days <= 3:
        phases = [_phase("sprint", "最后冲刺", "错题回看 + 一套模拟，不再开新战线", study_dates, "#dc2626")]
        plan_days: List[Dict[str, Any]] = []
        for offset, day in enumerate(study_dates):
            tasks: List[Dict[str, Any]] = []
            if offset == 0:
                review_items = _pick(items, {"repeated_failure", "lapsing", "overdue"}, used, 3)
                tasks = [_task(i, "回看", max(6, daily_minutes // 3)) for i in review_items]
                tasks.append({"type": "paper", "questionId": 0, "subject": _fallback_subject(subjects, items), "title": "做一套限时模拟", "detail": "按考试时间做完整一套，练的是节奏和心态，不是新知识", "minutes": max(15, daily_minutes // 2)})
            elif offset == 1:
                review_items = _pick(items, {"overdue", "due_soon", "on_track"}, used, 2)
                tasks = [_task(i, "复习", daily_minutes // 2) for i in review_items]
                tasks.append({"type": "review", "questionId": 0, "subject": _fallback_subject(subjects, items), "title": "只看错题解析", "detail": "不再做新题，把最近三套的错题解析过一遍", "minutes": daily_minutes // 2})
            else:
                tasks = [{"type": "rest", "questionId": 0, "subject": _fallback_subject(subjects, items), "title": "轻量复盘", "detail": "考试前一天只做 20 分钟错题回看，早点休息", "minutes": min(20, daily_minutes)}]
            plan_days.append({"date": day.isoformat(), "phase": "sprint", "theme": "最后冲刺", "tasks": tasks, "minutes": sum(t["minutes"] for t in tasks)})
        return {"phases": phases, "days": plan_days}

    f_ratio, r_ratio, s_ratio = MODE_RATIOS.get(mode, MODE_RATIOS["balanced"])
    foundation_days = max(0, round(total_days * f_ratio)) if foundation_pool else 0
    sprint_days = max(1, round(total_days * s_ratio))
    if foundation_days + sprint_days > total_days:
        sprint_days = max(1, total_days - foundation_days)
    review_days = max(0, total_days - foundation_days - sprint_days)
    if review_days == 0 and foundation_days > 0:
        foundation_days = max(0, total_days - sprint_days - 1)
        review_days = 1
    # 若补地基池子很小，避免把大量天数浪费在重复同一道题上
    if foundation_pool:
        foundation_days = min(foundation_days, max(1, len(foundation_pool)))
        review_days = max(0, total_days - foundation_days - sprint_days)

    phases: List[Dict[str, Any]] = []
    cursor = 0
    if foundation_days:
        dates = study_dates[cursor:cursor + foundation_days]
        phases.append(_phase("foundation", "补地基", "反复失守的题不是刷得少，是缺前置知识", dates, "#dc2626"))
        cursor += len(dates)
    if review_days:
        dates = study_dates[cursor:cursor + review_days]
        phases.append(_phase("review", "还债 + 巩固", "把欠复习的题补上，再用同科目题确认迁移", dates, "#d97706"))
        cursor += len(dates)
    sprint_dates = study_dates[cursor:]
    phases.append(_phase("sprint", "全真模拟", "按考试时间做整套，训练取舍与节奏", sprint_dates, "#2563eb"))

    plan_days: List[Dict[str, Any]] = []
    day_index = 0
    foundation_cursor = 0
    review_cursor = 0
    steady_cursor = 0
    fallback_subject = _fallback_subject(subjects, items)
    for phase in phases:
        for _ in range(int(phase["days"])):
            day = study_dates[day_index]
            day_index += 1
            tasks: List[Dict[str, Any]] = []
            if phase["key"] == "foundation":
                picks, foundation_cursor = _take(foundation_pool, foundation_cursor, 2)
                for item in picks:
                    tasks.append(_task(item, "补", max(8, daily_minutes // 2), "先看解析里的前置概念，再合上答案重做一遍"))
                if len(tasks) < 2:
                    tasks.append({"type": "concept", "questionId": 0, "subject": fallback_subject, "title": "补一个前置概念", "detail": "把今天错题涉及的概念用自己的话写一遍，写不出来就回资料里找", "minutes": max(8, daily_minutes // 3)})
                theme = "补地基 · 反复失守"
            elif phase["key"] == "review":
                picks, review_cursor = _take(review_pool, review_cursor, 2)
                for item in picks:
                    tasks.append(_task(item, "复习", max(6, daily_minutes // 3)))
                variant, steady_cursor = _take(steady_pool, steady_cursor, 1)
                for item in variant:
                    tasks.append(_task(item, "巩固", max(6, daily_minutes // 3), "换一道同科目的题，确认不是记住了答案"))
                if not tasks:
                    tasks.append({"type": "practice", "questionId": 0, "subject": fallback_subject, "title": "10 道综合小题", "detail": "从当前科目里随机抽 10 道，限时完成", "minutes": daily_minutes})
                theme = "还债 + 巩固"
            else:
                tasks.append({"type": "paper", "questionId": 0, "subject": fallback_subject, "title": "一套限时模拟", "detail": "按真实考试时长压缩到可用时间，中途不查答案", "minutes": max(20, daily_minutes // 2)})
                picks, foundation_cursor = _take(foundation_pool or review_pool, foundation_cursor, 1)
                for item in picks:
                    tasks.append(_task(item, "复盘", max(6, daily_minutes // 3), "只复盘今天模拟里错得最冤的一道"))
                theme = "全真模拟"
            budget = daily_minutes
            trimmed: List[Dict[str, Any]] = []
            for task in tasks:
                if budget <= 0:
                    break
                if task["minutes"] > budget:
                    task = {**task, "minutes": budget}
                trimmed.append(task)
                budget -= task["minutes"]
            plan_days.append(
                {
                    "date": day.isoformat(),
                    "phase": phase["key"],
                    "theme": theme,
                    "tasks": trimmed,
                    "minutes": sum(t["minutes"] for t in trimmed),
                }
            )

    return {"phases": phases, "days": plan_days}


async def build_exam_plan(
    db: AsyncSession,
    user_id: int,
    *,
    exam_name: str,
    exam_date: date,
    bank_id: Optional[int] = None,
    bank_name: str = "",
    subjects: Optional[List[str]] = None,
    start_date: Optional[date] = None,
    rest_days: Optional[List[int]] = None,
    mode: str = "balanced",
    daily_minutes: int = 40,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    moment = now or datetime.now()
    today = moment.date()
    if exam_date < today:
        raise ValueError("考试日期不能早于今天")
    start = start_date or today
    if start < today:
        raise ValueError("开始复习日期不能早于今天")
    if start >= exam_date:
        raise ValueError("开始复习日期必须早于考试日期")

    selected_subjects = [s for s in (subjects or []) if s]
    rest = sorted({int(d) for d in (rest_days or []) if 1 <= int(d) <= 7})
    mode = mode if mode in MODE_RATIOS else "balanced"

    diag = await sds.diagnose(db, user_id, limit=50)
    items = [
        it for it in (diag.get("items") or [])
        if (it.get("questionText") or "").strip() != DELETED_PLACEHOLDER
        and (it.get("bankName") or it.get("questionType") is not None)
    ]
    if not diag.get("hasData") or not items:
        return {
            "hasData": False,
            "exam": {
                "name": exam_name,
                "date": exam_date.isoformat(),
                "startDate": start.isoformat(),
                "daysLeft": max(0, (exam_date - today).days),
                "bankId": bank_id,
                "bankName": bank_name,
                "subjects": selected_subjects,
                "restDays": rest,
                "mode": mode,
                "dailyMinutes": daily_minutes,
            },
            "message": "还没有足够的作答记录，路线图没有依据。先做几道题，系统才能按你的薄弱点倒排计划。",
        }

    if bank_id:
        bank_items = [it for it in items if int(it.get("bankId") or 0) == int(bank_id)]
        if not bank_items:
            return {
                "hasData": False,
                "exam": {
                    "name": exam_name,
                    "date": exam_date.isoformat(),
                    "startDate": start.isoformat(),
                    "daysLeft": max(0, (exam_date - today).days),
                    "bankId": bank_id,
                    "bankName": bank_name,
                    "subjects": selected_subjects,
                    "restDays": rest,
                    "mode": mode,
                    "dailyMinutes": daily_minutes,
                },
                "message": f"「{bank_name or '这个题库'}」还没有可用的练习记录，先在题库里做几道题再生成计划。",
            }
        items = bank_items

    if selected_subjects:
        filtered = [it for it in items if it.get("subject") in selected_subjects]
        if not filtered:
            return {
                "hasData": False,
                "exam": {
                    "name": exam_name,
                    "date": exam_date.isoformat(),
                    "startDate": start.isoformat(),
                    "daysLeft": max(0, (exam_date - today).days),
                    "bankId": bank_id,
                    "bankName": bank_name,
                    "subjects": selected_subjects,
                    "restDays": rest,
                    "mode": mode,
                    "dailyMinutes": daily_minutes,
                },
                "message": f"「{'、'.join(selected_subjects)}」还没有可用的练习记录，先做几道这一科的题，路线图才有依据。",
            }
        items = filtered

    attention_count = sum(
        1 for it in items
        if it.get("level") in {"repeated_failure", "lapsing", "overdue", "due_soon"}
    )
    if attention_count == 0:
        profile, profile_label, profile_desc = "maintenance", "轻量巩固", "这个题库里没有明显薄弱题，安排少量模拟与错题回看即可，不制造无效任务。"
    elif attention_count <= 3:
        profile, profile_label, profile_desc = "micro", "专项突破", f"这个题库只有 {attention_count} 道题需要重点处理，集中几次解决，不排冗余的每日重复。"
    elif attention_count <= 10:
        profile, profile_label, profile_desc = "standard", "稳步提升", f"这个题库有 {attention_count} 道题需要关注，按三阶段稳步推进。"
    else:
        profile, profile_label, profile_desc = "intensive", "重点攻坚", f"这个题库有 {attention_count} 道题需要关注，计划会优先处理高频失守和欠复习。"

    built = _build_days(
        items,
        exam_date,
        start,
        max(10, min(int(daily_minutes), 240)),
        selected_subjects,
        rest,
        mode,
        profile,
        attention_count,
    )
    total_attempts = sum(int(it.get("attempts") or 0) for it in items)
    total_correct = sum(int(it.get("correctCount") or 0) for it in items)
    overall_accuracy = round(total_correct / total_attempts * 100, 1) if total_attempts else 0.0
    needs_attention = sum(
        1 for it in items
        if it.get("level") in {"repeated_failure", "lapsing", "overdue", "due_soon"}
    )

    weekday_names = ["一", "二", "三", "四", "五", "六", "日"]
    rest_text = "、".join(f"周{weekday_names[d - 1]}" for d in rest) or "无"
    return {
        "hasData": True,
        "exam": {
            "name": exam_name or "我的考试",
            "date": exam_date.isoformat(),
            "startDate": start.isoformat(),
            "daysLeft": max(0, (exam_date - today).days),
            "bankId": bank_id,
            "bankName": bank_name,
            "subjects": selected_subjects,
            "restDays": rest,
            "mode": mode,
            "dailyMinutes": max(10, min(int(daily_minutes), 240)),
        },
        "planProfile": {
            "key": profile,
            "label": profile_label,
            "description": profile_desc,
        },
        "overview": {
            "questionsSeen": len(items),
            "overallAccuracy": overall_accuracy,
            "needsAttention": needs_attention,
            "overdueCount": sum(1 for it in items if it.get("level") == "overdue"),
            "repeatedFailure": sum(1 for it in items if it.get("level") == "repeated_failure"),
        },
        "phases": built["phases"],
        "days": built["days"],
        "advice": [
            "三个阶段的顺序不能反：地基没补，模拟只会重复犯错。",
            "每天先做路线图里的题，再看解析；不要用「刷更多题」替代「弄懂一道题」。",
            f"每周休息日：{rest_text}。休息日不排任务，计划按剩余学习日自动压缩。",
        ],
    }


__all__ = ["build_exam_plan"]
