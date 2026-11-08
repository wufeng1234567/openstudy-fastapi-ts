"""学习周报：把最近 7 天的真实作答流水，整理成一张可分享的「成长故事」。

设计原则和 `learning_loop_service` 一致：
· 全部数字来自 `user_practice_log` / `user_question_marked` / 逐题诊断；
· 不调用大模型，不做「你最近表现很棒」这类无依据的评价；
· 没有数据就明确返回 `hasData=false`，前端显示空状态。

周报回答四个问题：
1. 这周我到底学了多少？（题量 / 正确率 / 活跃天数 / 连续天数）
2. 比上周是进步还是退步？（同口径对比）
3. 这周发生了什么值得记住的事？（斩题、消灭老对手、黄金时段）
4. 下周最该做什么？（最多 3 条，按优先级）
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import (
    QuestionBank,
    QuestionMain,
    UserPracticeLog,
    UserQuestionMarked,
)
from app.services import study_diagnosis_service as sds

DELETED_PLACEHOLDER = "（题目内容已不可用，可能已被删除）"


def _period_stats(rows: List[Any], start: datetime, end: datetime) -> Dict[str, Any]:
    """rows: [(create_time, is_correct, question_id, bank_id)]"""
    inside = [r for r in rows if start <= r[0] < end]
    total = len(inside)
    correct = sum(1 for r in inside if int(r[1] or 0) == 1)
    daily: Dict[str, Dict[str, int]] = {}
    for r in inside:
        key = r[0].strftime("%Y-%m-%d")
        bucket = daily.setdefault(key, {"practiceCount": 0, "correctCount": 0})
        bucket["practiceCount"] += 1
        bucket["correctCount"] += int(r[1] or 0)
    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total * 100, 1) if total else 0.0,
        "activeDays": len(daily),
        "daily": daily,
    }


def _longest_streak(daily: Dict[str, Dict[str, int]], today: date) -> int:
    """从今天（或最近有记录的一天）往回数连续学习天数"""
    if not daily:
        return 0
    cursor = today
    if cursor.strftime("%Y-%m-%d") not in daily:
        cursor = cursor - timedelta(days=1)
    streak = 0
    while cursor.strftime("%Y-%m-%d") in daily:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _hour_phrase(hour: int) -> str:
    if hour < 6:
        return f"凌晨 {hour} 点"
    if hour < 12:
        return f"上午 {hour} 点"
    if hour < 14:
        return f"中午 {hour} 点"
    if hour < 18:
        return f"下午 {hour} 点"
    return f"晚上 {hour - 12 if hour > 12 else 12} 点"


def _pct_change(current: int, previous: int) -> Optional[float]:
    if previous <= 0:
        return None
    return round((current - previous) / previous * 100, 1)


def _empty(moment: datetime) -> Dict[str, Any]:
    return {
        "hasData": False,
        "generatedAt": moment.isoformat(timespec="seconds"),
        "range": {"start": "", "end": "", "label": "", "isCurrent": False},
        "headline": "还没有足够的学习记录，先做几道题再来领周报",
    }


async def build_weekly_report(
    db: AsyncSession, user_id: int, *, now: Optional[datetime] = None
) -> Dict[str, Any]:
    moment = now or datetime.now()
    # 最近 7 个自然日（含今天） vs 前 7 个自然日
    today_start = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=6)
    prev_start = week_start - timedelta(days=7)
    end = moment
    is_current = True

    # 如果用户最近两周都没打开过，仍然给他看「最近一次学习的那 7 天」——
    # 周报的意义是复盘，而不是用「本周空白」惩罚一个暂时停下来的用户。
    # 只统计题目仍存在的流水：题目被物理删除后的孤儿流水无法复盘，
    # 也不该把「这周做了 70 题」说成真实可回看的练习量。
    latest = await db.scalar(
        select(func.max(UserPracticeLog.create_time))
        .select_from(
            UserPracticeLog.__table__.join(
                QuestionMain.__table__, UserPracticeLog.question_id == QuestionMain.id
            )
        )
        .where(UserPracticeLog.user_id == int(user_id))
    )
    if latest is None:
        return _empty(moment)
    if latest < week_start:
        end = latest + timedelta(seconds=1)
        today_start = end.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=6)
        prev_start = week_start - timedelta(days=7)
        is_current = False

    rows = (
        await db.execute(
            select(
                UserPracticeLog.create_time,
                UserPracticeLog.is_correct,
                UserPracticeLog.question_id,
                UserPracticeLog.bank_id,
            )
            .select_from(
                UserPracticeLog.__table__.join(
                    QuestionMain.__table__, UserPracticeLog.question_id == QuestionMain.id
                )
            )
            .where(
                UserPracticeLog.user_id == int(user_id),
                UserPracticeLog.create_time >= prev_start,
                UserPracticeLog.create_time <= end,
            )
            .order_by(UserPracticeLog.create_time.asc())
        )
    ).all()
    if not rows:
        return _empty(moment)

    current = _period_stats(list(rows), week_start, end)
    previous = _period_stats(list(rows), prev_start, week_start)
    if current["total"] == 0:
        return _empty(moment)

    # 科目正确率（本周，至少 3 次作答才展示，避免 1 题 100% 的噪音）
    bank_ids = sorted({int(r[3]) for r in rows if r[3] is not None})
    bank_subject: Dict[int, str] = {}
    if bank_ids:
        bank_rows = (
            await db.execute(
                select(QuestionBank.id, QuestionBank.subject).where(
                    QuestionBank.id.in_(bank_ids)
                )
            )
        ).all()
        bank_subject = {int(r[0]): (r[1] or "未分类") for r in bank_rows}

    subject_agg: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        if not (week_start <= r[0] < end):
            continue
        # 题库被删除后流水仍在（刻意不加外键）。这类记录无法归属到科目，
        # 也不该被归进「未分类」拉低某一科的正确率 —— 直接跳过科目维度。
        if r[3] is None or int(r[3]) not in bank_subject:
            continue
        subject = bank_subject[int(r[3])]
        bucket = subject_agg.setdefault(subject, {"subject": subject, "attempts": 0, "correct": 0})
        bucket["attempts"] += 1
        bucket["correct"] += int(r[1] or 0)
    subjects = [
        {
            "subject": v["subject"],
            "attempts": v["attempts"],
            "accuracy": round(v["correct"] / v["attempts"] * 100, 1) if v["attempts"] else 0.0,
        }
        for v in subject_agg.values()
        if v["attempts"] >= 3
    ]
    subjects.sort(key=lambda s: s["accuracy"])

    # 黄金时段：本周按小时统计作答量
    hour_counter: Dict[int, int] = {}
    for r in rows:
        if week_start <= r[0] < end:
            hour_counter[r[0].hour] = hour_counter.get(r[0].hour, 0) + 1
    peak_hour, peak_hour_count = (None, 0)
    if hour_counter:
        peak_hour, peak_hour_count = max(hour_counter.items(), key=lambda kv: kv[1])

    # 本周斩题
    marked_rows = (
        await db.execute(
            select(UserQuestionMarked.marked_id).where(
                UserQuestionMarked.user_id == int(user_id),
                UserQuestionMarked.marked_status == 1,
                UserQuestionMarked.create_time >= week_start,
                UserQuestionMarked.create_time <= end,
            )
        )
    ).all()
    marked_count = len(marked_rows)

    # 逐题诊断：找出「本周刚被判定为已歼灭」的老对手
    diag = await sds.diagnose(db, user_id, limit=50)
    cleared_this_week: List[Dict[str, Any]] = []
    for item in diag.get("items") or []:
        if item.get("level") != "mastered":
            continue
        if (item.get("questionText") or "").strip() == DELETED_PLACEHOLDER:
            continue
        last_time = str(item.get("lastPracticeTime") or "")
        if not last_time:
            continue
        try:
            if datetime.fromisoformat(last_time) >= week_start:
                cleared_this_week.append(item)
        except ValueError:
            continue
    cleared_this_week.sort(key=lambda it: -int(it.get("attempts") or 0))

    # 已归档 / 可归档（诊断说「连续答对很多次」）
    can_archive = int((diag.get("summary") or {}).get("canArchive") or 0)
    overdue = int((diag.get("summary") or {}).get("overdueCount") or 0)

    # 本周对比
    # 上周样本太小时百分比没有意义（2 -> 70 会算出 3400%），直接不给百分比
    delta_practice = _pct_change(current["total"], previous["total"]) if previous["total"] >= 5 else None
    delta_accuracy = round(current["accuracy"] - previous["accuracy"], 1) if previous["total"] >= 3 else None

    streak_days = _longest_streak(current["daily"], end.date())
    period_word = "这周" if is_current else "最近 7 天"

    # 一句话结论（按「有行动价值」排序）
    if current["total"] >= 30:
        headline = f"{period_word}你完成了 {current['total']} 道题，量已经上来了，接下来要比的是「记住多少」"
    elif current["activeDays"] >= 4:
        headline = f"{period_word}有 {current['activeDays']} 天在学，节奏比一次刷很多更值钱"
    else:
        headline = f"{period_word}你完成了 {current['total']} 道题，先把节奏找回来"

    # 亮点（只写真实发生的事）
    highlights: List[Dict[str, Any]] = []
    if cleared_this_week:
        top = cleared_this_week[0]
        highlights.append(
            {
                "type": "cleared",
                "title": "消灭了一个老对手",
                "detail": f"「{str(top.get('questionText') or '')[:28]}」已经连续答对，退出错题本",
            }
        )
    if marked_count:
        highlights.append(
            {
                "type": "marked",
                "title": "主动斩题",
                "detail": f"本周标记了 {marked_count} 道「已经会了」的题",
            }
        )
    if peak_hour is not None:
        highlights.append(
            {
                "type": "time",
                "title": "你的黄金时段",
                "detail": f"{_hour_phrase(peak_hour)} 做题最多（{peak_hour_count} 次），下次可以固定这个时间",
            }
        )
    if current["activeDays"] >= 4:
        highlights.append(
            {
                "type": "consistency",
                "title": "节奏保持住了",
                "detail": f"本周 {current['activeDays']} 天有学习记录，最长连续 {streak_days} 天",
            }
        )

    # 下周建议：最多 3 条，按优先级
    next_week: List[Dict[str, Any]] = []
    if overdue:
        next_week.append(
            {
                "title": f"先还清 {overdue} 道欠复习的题",
                "detail": "它们已经过了记忆窗口，现在练收益最高。打开「学习计划」会自动排在最前面。",
            }
        )
    if subjects:
        weakest = subjects[0]
        next_week.append(
            {
                "title": f"把「{weakest['subject']}」往上推一档",
                "detail": f"本周正确率 {weakest['accuracy']}%，建议每天 10 分钟只练这一科的高频错题。",
            }
        )
    if can_archive:
        next_week.append(
            {
                "title": f"给错题本减负：归档 {can_archive} 道已经会的题",
                "detail": "连续答对 4 次以上的题继续留在错题本里，只会让真正该看的题被淹没。",
            }
        )
    if current["activeDays"] < 4 and len(next_week) < 3:
        next_week.append(
            {
                "title": "把学习拆成 4 天 × 20 分钟",
                "detail": "本周活跃天数偏少。短而稳的节奏，比周末一次突击更容易形成长期记忆。",
            }
        )
    if len(next_week) < 3:
        next_week.append(
            {
                "title": "给下周留一次 20 分钟的整块练习",
                "detail": "选一个你最容易拖到晚上的科目，固定在同一个时间做，先把「开始」这件事变容易。",
            }
        )

    return {
        "hasData": True,
        "generatedAt": moment.isoformat(timespec="seconds"),
        "range": {
            "start": week_start.strftime("%Y-%m-%d"),
            "end": end.strftime("%Y-%m-%d"),
            "label": f"{week_start.strftime('%m.%d')} - {end.strftime('%m.%d')}",
            "isCurrent": is_current,
        },
        "headline": headline,
        "stats": {
            "practiceCount": current["total"],
            "correctCount": current["correct"],
            "accuracy": current["accuracy"],
            "activeDays": current["activeDays"],
            "longestStreak": streak_days,
            "markedCount": marked_count,
            "deltaPractice": delta_practice,
            "deltaAccuracy": delta_accuracy,
            "prevPracticeCount": previous["total"],
            "prevAccuracy": previous["accuracy"],
        },
        # 补齐本周 7 天（没练的那天也显示 0，图表不会跳日）
        "daily": [
            {
                "date": (week_start + timedelta(days=i)).strftime("%Y-%m-%d"),
                "weekday": "一二三四五六日"[(week_start + timedelta(days=i)).weekday()],
                "practiceCount": current["daily"]
                .get((week_start + timedelta(days=i)).strftime("%Y-%m-%d"), {})
                .get("practiceCount", 0),
            }
            for i in range(7)
        ],
        "subjects": subjects,
        "peakHour": peak_hour,
        "highlights": highlights,
        "nextWeek": next_week[:3],
    }


__all__ = ["build_weekly_report"]
