"""
`english_practice` —— 英语练习记录与学情诊断（Agent 工具）

## 为什么需要它

`english_wordbook` 让智能体能读写**词库**（静态的"我在背什么"），
但用户真正关心的是**练得怎么样**：

    「我最近英语练得多吗」
    「我听力正确率在涨吗」
    「哪些词我老是拼错」
    「我该重点复习哪几个词」

这些问题的答案不在 `words` 表里，而在 `english_practice_log`（练习记录）。
没有这个工具，智能体只能对着词库空谈，说不出任何关于"练习效果"的话。

## 与 `learning_stats` 的分工

    learning_stats     → 题库（刷题、错题本、知识点薄弱）
    english_practice   → 英语模块（听写 / 阅读 / 识词 的练习记录）

两者**不重叠**：前者读 `user_practice_log`（题库作答），后者读
`english_practice_log`（英语练习）。用户问「英语练得怎么样」时，
只有这里能答。

## 动作边界

全部**只读**（`write_operation = False`）：
  · recent —— 最近 N 次练习
  · stats  —— 各模式汇总 + 7 天趋势 + 最常错词
  · review —— 基于错词频次给出复习建议（**算出来的**，不是让 LLM 自由发挥）

⚠️ 为什么 `review` 也是只读：它只是把统计结果排个序、给个建议，
不写任何表。要真正"安排复习计划"得等未来的遗忘曲线排程，
那时再单独加写操作（并让它需要确认）。
"""

from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import func, select

from app.models.words import EnglishPracticeLog
from app.services.ai.agent.base import AgentTool, ToolContext, fail, ok

#: 一次最多看多少条记录
MAX_RECENT = 50


def _uid(ctx: ToolContext) -> int:
    return int(ctx.user_id or 0)


def _brief(row: EnglishPracticeLog) -> Dict[str, Any]:
    return {
        "id": row.id,
        "mode": row.mode,
        "title": row.title,
        "total": row.total,
        "correct": row.correct,
        "accuracy": row.accuracy,
        "duration": row.duration,
        "createTime": (
            row.create_time.strftime("%Y-%m-%d %H:%M") if row.create_time else None
        ),
    }


class EnglishPracticeTool(AgentTool):
    name = "english_practice"
    description = (
        "Read the user's ENGLISH practice history and diagnose how they are doing. "
        "This covers the three English modules: 单词听写 (dictation), 阅读练习 "
        "(reading comprehension), and 拍照识词 (OCR vocabulary capture). "
        "Use it whenever the user asks about their English practice rather than their "
        "word books: 'do I practise English often', 'is my dictation accuracy going up', "
        "'which words do I keep misspelling', 'what English should I review', "
        "'how did my last reading exercise go'. "
        "action values: "
        "stats=overall numbers: total sessions, overall accuracy, per-mode breakdown "
        "(dictation / reading / ocr), the last-7-days trend, and the words most often "
        "answered wrong. **PREFER THIS for any 'how am I doing in English' question.** "
        "recent=list the most recent practice sessions (pass `limit`, default 10, max 50). "
        "review=the computed review list: which words to re-practise, ordered by how "
        "often they were wrong. Each item carries `word`, `wrongCount` and `advice`. "
        "NOTE: this tool is read-only. To add or change word books use "
        "`english_wordbook`; for question-bank study stats use `learning_stats`. "
        "If the user has never practised, say so honestly — do NOT invent numbers."
    )
    label = "英语练习"
    description_zh = (
        "读英语练习记录：stats=总览（各模式正确率/7天趋势/最常错词）、"
        "recent=最近几次练习、review=该重点复习哪些词。只读。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Operation to perform",
                "enum": ["stats", "recent", "review"],
            },
            "limit": {
                "type": "integer",
                "description": "For recent: how many sessions to return (default 10, max 50).",
            },
        },
        "required": ["action"],
    }
    #: 全部只读，永不弹确认卡
    write_operation = False

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        action = str(params.get("action") or "")
        handler = {
            "stats": self._stats,
            "recent": self._recent,
            "review": self._review,
        }.get(action)
        if handler is None:
            return fail(
                f"未知操作: {action}",
                "action 只能是 stats / recent / review",
            )
        try:
            return await handler(params, ctx)
        except Exception as e:  # noqa: BLE001
            return fail(
                f"读取英语练习记录失败：{e}",
                "可以稍后重试；不要凭空编造练习数据",
            )

    # ------------------------------------------------------------------

    async def _recent(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        raw = params.get("limit")
        try:
            limit = max(1, min(int(raw), MAX_RECENT)) if raw is not None else 10
        except (TypeError, ValueError):
            limit = 10

        rows = (
            await ctx.db.execute(
                select(EnglishPracticeLog)
                .where(
                    EnglishPracticeLog.user_id == _uid(ctx),
                    EnglishPracticeLog.del_flag == "0",
                )
                .order_by(EnglishPracticeLog.create_time.desc())
                .limit(limit)
            )
        ).scalars().all()

        sessions = [_brief(r) for r in rows]
        if not sessions:
            return ok(
                action="recent",
                count=0,
                sessions=[],
                message="该用户还没有任何英语练习记录（没练过听写/阅读/识词）。请如实告知。",
            )

        return ok(
            action="recent",
            count=len(sessions),
            sessions=sessions,
            message=f"最近 {len(sessions)} 次英语练习：" + "、".join(
                f"{s['title']}（{s['accuracy']}%）" for s in sessions[:5]
            ),
        )

    async def _stats(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        uid = _uid(ctx)

        # ① 各模式累计
        rows = (
            await ctx.db.execute(
                select(
                    EnglishPracticeLog.mode,
                    func.count().label("sessions"),
                    func.sum(EnglishPracticeLog.total).label("total"),
                    func.sum(EnglishPracticeLog.correct).label("correct"),
                )
                .where(
                    EnglishPracticeLog.user_id == uid,
                    EnglishPracticeLog.del_flag == "0",
                )
                .group_by(EnglishPracticeLog.mode)
            )
        ).all()

        by_mode: Dict[str, Dict[str, Any]] = {}
        for mode, sessions, total, correct in rows:
            t = int(total or 0)
            c = int(correct or 0)
            by_mode[str(mode)] = {
                "sessions": int(sessions or 0),
                "total": t,
                "correct": c,
                "accuracy": int(round(c * 100.0 / t)) if t else 0,
            }

        if not by_mode:
            return ok(
                action="stats",
                sessions=0,
                accuracy=0,
                byMode={},
                trend=[],
                topWrong=[],
                message="该用户还没有任何英语练习记录。请如实告知，不要说'你练得不错'这类无依据的话。",
            )

        # ② 最近 7 天趋势
        recent_rows = (
            await ctx.db.execute(
                select(
                    func.date(EnglishPracticeLog.create_time).label("d"),
                    func.sum(EnglishPracticeLog.total).label("total"),
                    func.sum(EnglishPracticeLog.correct).label("correct"),
                )
                .where(
                    EnglishPracticeLog.user_id == uid,
                    EnglishPracticeLog.del_flag == "0",
                    EnglishPracticeLog.create_time
                    >= func.now() - func.make_interval(0, 0, 0, 7),
                )
                .group_by(func.date(EnglishPracticeLog.create_time))
            )
        ).all()

        trend = [
            {
                "date": str(d),
                "total": int(t or 0),
                "accuracy": (
                    int(round(int(c or 0) * 100.0 / int(t))) if int(t or 0) else 0
                ),
            }
            for d, t, c in recent_rows
        ]

        # ③ 最常错的词（扫最近 20 次明细）
        details = (
            await ctx.db.execute(
                select(EnglishPracticeLog.detail)
                .where(
                    EnglishPracticeLog.user_id == uid,
                    EnglishPracticeLog.del_flag == "0",
                )
                .order_by(EnglishPracticeLog.create_time.desc())
                .limit(20)
            )
        ).scalars().all()

        counter: Dict[str, int] = {}
        for detail in details:
            for item in detail or []:
                if isinstance(item, dict) and not item.get("ok"):
                    w = str(item.get("word") or "").strip()
                    if w:
                        counter[w] = counter.get(w, 0) + 1

        top_wrong = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:10]

        total = sum(v["total"] for v in by_mode.values())
        correct = sum(v["correct"] for v in by_mode.values())
        sessions = sum(v["sessions"] for v in by_mode.values())

        parts = [f"共练习 {sessions} 次、{total} 题"]
        for mode, label in (
            ("dictation", "听写"),
            ("reading", "阅读"),
            ("ocr", "识词"),
        ):
            m = by_mode.get(mode)
            if m:
                parts.append(f"{label} {m['sessions']} 次 {m['accuracy']}%")
        if top_wrong:
            parts.append(
                "最常错：" + "、".join(w for w, _ in top_wrong[:5])
            )

        return ok(
            action="stats",
            sessions=sessions,
            total=total,
            correct=correct,
            accuracy=int(round(correct * 100.0 / total)) if total else 0,
            byMode=by_mode,
            trend=trend,
            topWrong=[{"word": w, "count": c} for w, c in top_wrong],
            message="；".join(parts),
            jumpUrl="/front/english/listening",
        )

    async def _review(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        """复习清单：按错次排序，给出确定性建议

        ⚠️ 建议是**算出来的**，不是让模型自由发挥：
        错 3 次以上 → 必须重学（可能根本没记住）
        错 2 次     → 重点复习
        错 1 次     → 过一遍即可
        同一份数据永远得到同一个结论，可复现、可解释。
        """
        uid = _uid(ctx)

        details = (
            await ctx.db.execute(
                select(EnglishPracticeLog.detail)
                .where(
                    EnglishPracticeLog.user_id == uid,
                    EnglishPracticeLog.del_flag == "0",
                )
                .order_by(EnglishPracticeLog.create_time.desc())
                .limit(20)
            )
        ).scalars().all()

        counter: Dict[str, int] = {}
        for detail in details:
            for item in detail or []:
                if isinstance(item, dict) and not item.get("ok"):
                    w = str(item.get("word") or "").strip()
                    if w:
                        counter[w] = counter.get(w, 0) + 1

        if not counter:
            return ok(
                action="review",
                count=0,
                items=[],
                message="最近没有错词，暂时不需要重点复习。可以换个更难的词库继续练。",
            )

        items: List[Dict[str, Any]] = []
        for word, cnt in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:20]:
            if cnt >= 3:
                advice = "连续错多次，建议回到词库重学这个词再练"
                level = "high"
            elif cnt == 2:
                advice = "错了两次，重点复习"
                level = "medium"
            else:
                advice = "错了一次，过一遍即可"
                level = "low"
            items.append(
                {"word": word, "wrongCount": cnt, "level": level, "advice": advice}
            )

        high = sum(1 for i in items if i["level"] == "high")
        return ok(
            action="review",
            count=len(items),
            highPriority=high,
            items=items,
            message=(
                f"有 {len(items)} 个词需要复习"
                + (f"，其中 {high} 个是反复错的（建议优先处理）" if high else "")
            ),
            jumpUrl="/front/english/listening",
        )


__all__ = ["EnglishPracticeTool", "MAX_RECENT"]
