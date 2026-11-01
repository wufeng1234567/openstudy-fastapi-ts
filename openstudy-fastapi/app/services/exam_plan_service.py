"""考前倒计时路线图。

用户只输入三件事：考试名、考试日期、每天可学多久。剩下的由系统按逐题诊断
结果倒排 —— 不是「生成一份漂亮计划」，而是每天告诉用户先做哪几道题、为什么。

规划逻辑（确定性，不调用大模型）：
  · 距考试 > 10 天：补地基（反复失守/一做就错）→ 还债 + 变式（欠复习）→ 全真模拟
  · 距考试 4~10 天：还债 + 变式 → 模拟
  · 距考试 ≤ 3 天：只做「错题回看 + 一套模拟」，不再开新战线

任何时候题库不够时，任务数量会自动收缩到真实可用的题，不凑数。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import study_diagnosis_service as sds

DELETED_PLACEHOLDER = "（题目内容已不可用，可能已被删除）"


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


def _phase(
    key: str,
    title: str,
    goal: str,
    start: date,
    days: int,
    color: str,
) -> Dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "goal": goal,
        "start": start.isoformat(),
        "end": (start + timedelta(days=max(days - 1, 0))).isoformat(),
        "days": days,
        "color": color,
    }


def _take(pool: List[Dict[str, Any]], cursor: int, count: int) -> tuple[List[Dict[str, Any]], int]:
    """从池子里循环取题：错题本来就需要重复，取完一轮再从头上。

    返回 (题目列表, 下一次的游标)。池子为空时返回空列表。
    """
    if not pool:
        return [], cursor
    picked = [pool[(cursor + i) % len(pool)] for i in range(min(count, len(pool)))]
    return picked, (cursor + count) % len(pool)


def _build_days(
    items: List[Dict[str, Any]],
    exam_date: date,
    today: date,
    daily_minutes: int,
    subject: str,
) -> Dict[str, Any]:
    total_days = max(1, (exam_date - today).days)
    used: set[int] = set()

    foundation_pool = [
        i for i in items
        if i.get("level") in {"repeated_failure", "lapsing"}
        and (not subject or i.get("subject") == subject)
    ]
    review_pool = [
        i for i in items
        if i.get("level") in {"overdue", "due_soon"}
        and (not subject or i.get("subject") == subject)
    ]
    steady_pool = [
        i for i in items
        if i.get("level") in {"on_track", "fresh"}
        and (not subject or i.get("subject") == subject)
    ]

    if total_days <= 3:
        phases = [_phase("sprint", "最后冲刺", "错题回看 + 一套模拟，不再开新战线", today, total_days, "#dc2626")]
        plan_days: List[Dict[str, Any]] = []
        for offset in range(total_days):
            day = today + timedelta(days=offset)
            tasks: List[Dict[str, Any]] = []
            if offset == 0:
                review_items = _pick(items, {"repeated_failure", "lapsing", "overdue"}, used, 3)
                tasks = [_task(i, "回看", max(6, daily_minutes // 3)) for i in review_items]
                tasks.append({"type": "paper", "questionId": 0, "subject": subject, "title": "做一套限时模拟", "detail": "按考试时间做完整一套，练的是节奏和心态，不是新知识", "minutes": max(15, daily_minutes // 2)})
            elif offset == 1:
                review_items = _pick(items, {"overdue", "due_soon", "on_track"}, used, 2)
                tasks = [_task(i, "复习", daily_minutes // 2) for i in review_items]
                tasks.append({"type": "review", "questionId": 0, "subject": subject, "title": "只看错题解析", "detail": "不再做新题，把最近三套的错题解析过一遍", "minutes": daily_minutes // 2})
            else:
                tasks = [{"type": "rest", "questionId": 0, "subject": subject, "title": "轻量复盘", "detail": "考试前一天只做 20 分钟错题回看，早点休息", "minutes": min(20, daily_minutes)}]
            plan_days.append({"date": day.isoformat(), "phase": "sprint", "theme": "最后冲刺", "tasks": tasks, "minutes": sum(t["minutes"] for t in tasks)})
        return {"phases": phases, "days": plan_days}

    foundation_days = max(0, round(total_days * 0.35)) if foundation_pool else 0
    sprint_days = max(1, round(total_days * 0.25))
    review_days = max(0, total_days - foundation_days - sprint_days)
    if review_days == 0 and foundation_days > 0:
        foundation_days = max(0, total_days - sprint_days - 1)
        review_days = 1

    phases: List[Dict[str, Any]] = []
    cursor = today
    if foundation_days:
        phases.append(_phase("foundation", "补地基", "反复失守的题不是刷得少，是缺前置知识", cursor, foundation_days, "#dc2626"))
        cursor += timedelta(days=foundation_days)
    if review_days:
        phases.append(_phase("review", "还债 + 巩固", "把欠复习的题补上，再用同科目题确认迁移", cursor, review_days, "#d97706"))
        cursor += timedelta(days=review_days)
    phases.append(_phase("sprint", "全真模拟", "按考试时间做整套，训练取舍与节奏", cursor, sprint_days, "#2563eb"))

    plan_days: List[Dict[str, Any]] = []
    day_index = 0
    foundation_cursor = 0
    review_cursor = 0
    steady_cursor = 0
    for phase in phases:
        for _ in range(int(phase["days"])):
            day = today + timedelta(days=day_index)
            day_index += 1
            tasks: List[Dict[str, Any]] = []
            if phase["key"] == "foundation":
                picks, foundation_cursor = _take(foundation_pool, foundation_cursor, 2)
                for item in picks:
                    tasks.append(_task(item, "补", max(8, daily_minutes // 2), "先看解析里的前置概念，再合上答案重做一遍"))
                if len(tasks) < 2:
                    fallback_subject = subject or (items[0].get("subject") if items else "")
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
                    tasks.append({"type": "practice", "questionId": 0, "subject": subject, "title": "10 道综合小题", "detail": "从当前科目里随机抽 10 道，限时完成", "minutes": daily_minutes})
                theme = "还债 + 巩固"
            else:
                tasks.append({"type": "paper", "questionId": 0, "subject": subject, "title": "一套限时模拟", "detail": "按真实考试时长压缩到可用时间，中途不查答案", "minutes": max(20, daily_minutes // 2)})
                picks, foundation_cursor = _take(foundation_pool or review_pool, foundation_cursor, 1)
                for item in picks:
                    tasks.append(_task(item, "复盘", max(6, daily_minutes // 3), "只复盘今天模拟里错得最冤的一道"))
                theme = "全真模拟"
            # 每天不超过用户给的时间
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
    subject: str = "",
    daily_minutes: int = 40,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    moment = now or datetime.now()
    today = moment.date()
    if exam_date < today:
        raise ValueError("考试日期不能早于今天")

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
                "daysLeft": max(0, (exam_date - today).days),
                "subject": subject,
                "dailyMinutes": daily_minutes,
            },
            "message": "还没有足够的作答记录，路线图没有依据。先做几道题，系统才能按你的薄弱点倒排计划。",
        }

    if subject:
        filtered = [it for it in items if it.get("subject") == subject]
        if not filtered:
            return {
                "hasData": False,
                "exam": {
                    "name": exam_name,
                    "date": exam_date.isoformat(),
                    "daysLeft": max(0, (exam_date - today).days),
                    "subject": subject,
                    "dailyMinutes": daily_minutes,
                },
                "message": f"「{subject}」还没有可用的练习记录，先做几道这一科的题，路线图才有依据。",
            }
        items = filtered

    built = _build_days(items, exam_date, today, max(10, min(int(daily_minutes), 240)), subject)
    # 概览只统计「题目还在」的记录，与路线图里真正能做的题保持一致
    total_attempts = sum(int(it.get("attempts") or 0) for it in items)
    total_correct = sum(int(it.get("correctCount") or 0) for it in items)
    overall_accuracy = round(total_correct / total_attempts * 100, 1) if total_attempts else 0.0
    needs_attention = sum(
        1 for it in items
        if it.get("level") in {"repeated_failure", "lapsing", "overdue", "due_soon"}
    )

    return {
        "hasData": True,
        "exam": {
            "name": exam_name or "我的考试",
            "date": exam_date.isoformat(),
            "daysLeft": max(0, (exam_date - today).days),
            "subject": subject,
            "dailyMinutes": max(10, min(int(daily_minutes), 240)),
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
            "考试前三天停止开新题，只回看错题和做整套模拟。",
        ],
    }


__all__ = ["build_exam_plan"]
