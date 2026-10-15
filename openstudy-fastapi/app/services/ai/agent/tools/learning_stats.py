"""
`learning_stats` —— 学习统计工具（Agent 自封装，**只读**）

对齐项目里那套「学习统计」接口的语义（`app/api/v1/user_stats.py` 的
overview / bySubject / trend / errorAnalysis / growth）—— 它们是同一批数字，
用户在「我的学习统计」页面上看到的就是这些。

⚠️ 数字**必须与页面一致**，所以这里不自己写查询：直接调
`app/services/user_stats_service.py`，由它再调那五个路由处理函数（同一份实现）。
理由与越权说明见那个模块的 docstring。

只读的三个证据（改之前先看一眼）
-------------------------------
· `write_operation = False` —— 它不写库，也不该被 `memory_hook` 记进长期记忆
  （否则「用户问了一次正确率」都会被记成一条操作记录，把真正有用的记忆淹没）
· `needs_confirmation` 保持默认 False —— 前端不会为它弹二次确认卡片
· `is_destructive` 保持默认 False

⚠️ 一个**已知的历史口径问题**（不在本轮修，别顺手改）：`trend`
用 `datetime.now()`（本地时间）与库里 `create_time` 做日期分组，而
`user_practice_log.create_time` 是应用层写进去的本地朴素时间、`server_default`
那一路则是 PG 的 UTC —— 混着用会让「今天」的边界对不上 8 小时。
这是既有端点的既有行为，改了反而会让 Agent 与页面显示不一致。
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.services import user_stats_service as stats
from app.services.ai.agent.base import AgentTool, ToolContext, fail, ok

#: 一次趋势最多看多少天（与路由签名上的 `le=90` 一致）
MAX_TREND_DAYS = stats.TREND_MAX_DAYS


class LearningStatsTool(AgentTool):
    name = "learning_stats"
    #: ⚠️ 描述与参数说明一律英文（进系统提示词 `{{TOOLS}}` 与 Function Calling）
    description = (
        "Read the user's study statistics. Use it whenever the user asks how they are "
        "doing: 'how many questions have I done', 'what's my accuracy', 'my wrong "
        "questions', 'which subject is my weakest', 'how many days have I studied', "
        "'show me my progress / trend'. "
        "action values: overview=the headline numbers (favourite questions, banks, wrong "
        "questions, marked questions, practice count, accuracy, favourite notes), "
        "by_subject=per-subject breakdown, trend=the last N days (pass `days`, default 7), "
        "error_analysis=wrong-question analysis (total / still active / mastered / mastery "
        "rate, by difficulty, by question type, by subject, top 5 most-often-wrong), "
        "growth=join date, study days, streak and achievements. "
        "These are the SAME numbers the user sees on their statistics page. Read-only. "
        "NOTE: for the actual list of wrong / favourite / marked questions use "
        "`question_flag_manage` (flag_type=error / favorite / marked) instead."
    )
    #: 界面专用（只给前端看；不进 definitions() / describe()）
    label = "学习统计"
    description_zh = (
        "读学习数据（只读）：overview=总览、by_subject=按科目、trend=趋势、"
        "error_analysis=错题分析、growth=成长情况。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Operation to perform",
                "enum": ["overview", "by_subject", "trend", "error_analysis", "growth"],
            },
            "days": {
                "type": "integer",
                "description": (
                    f"How many days the trend covers (used by trend; default "
                    f"{stats.TREND_DEFAULT_DAYS}, max {MAX_TREND_DAYS})."
                ),
            },
        },
        "required": ["action"],
    }
    #: 只读 —— 不写库，也不会出现在 `/ai/agent/tools` 的写操作清单里
    write_operation = False

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        action = str(params.get("action") or "")
        handler = {
            "overview": self._overview,
            "by_subject": self._by_subject,
            "trend": self._trend,
            "error_analysis": self._error_analysis,
            "growth": self._growth,
        }.get(action)
        if handler is None:
            return fail(
                f"未知操作: {action}",
                "action 只能是 overview / by_subject / trend / error_analysis / growth",
            )
        try:
            return await handler(params, ctx)
        except Exception as e:  # noqa: BLE001 - 统计查询失败也要给模型一个可读的说明
            return fail(
                f"查询学习统计失败：{e}",
                "可以稍后重试；不要凭空编造统计数字",
            )

    # ------------------------------------------------------------------

    async def _overview(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        data = await stats.overview(ctx.db, ctx.user_id)
        total_practice = int(data.get("totalPracticeCount") or 0)
        if total_practice <= 0:
            message = "该用户还没有任何作答记录（其余数字都是 0），请如实告知，不要编造。"
        else:
            message = (
                f"共作答 {total_practice} 次，正确率 {data.get('correctRate')}%；"
                f"收藏题目 {data.get('totalQuestions') or 0} 道、"
                f"错题 {data.get('totalErrors') or 0} 道、"
                f"斩题 {data.get('totalMarked') or 0} 道"
            )
        return ok(**{**data, "action": "overview", "message": message})

    async def _by_subject(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        rows: List[Dict[str, Any]] = await stats.by_subject(ctx.db, ctx.user_id)
        if not rows:
            return ok(
                action="by_subject",
                count=0,
                bySubject=[],
                message="还没有按科目统计的数据（收藏题库/题目、错题、斩题都为空），请如实告知。",
            )
        top = max(rows, key=lambda r: int(r.get("errorCount") or 0))
        return ok(
            action="by_subject",
            count=len(rows),
            bySubject=rows,
            message=(
                f"共 {len(rows)} 个科目有记录"
                + (
                    f"，错题最多的是「{top.get('subject')}」（{top.get('errorCount')} 道）"
                    if int(top.get("errorCount") or 0) > 0
                    else ""
                )
            ),
        )

    async def _trend(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        raw = params.get("days")
        days = raw if raw is not None else stats.TREND_DEFAULT_DAYS
        rows: List[Dict[str, Any]] = await stats.trend(ctx.db, ctx.user_id, days)
        total = sum(int(r.get("practiceCount") or 0) for r in rows)
        correct = sum(int(r.get("correctCount") or 0) for r in rows)
        return ok(
            action="trend",
            days=len(rows),
            count=len(rows),
            trend=rows,
            message=(
                f"最近 {len(rows)} 天共作答 {total} 次，答对 {correct} 次"
                + ("（这段时间没有作答记录）" if total == 0 else "")
            ),
        )

    async def _error_analysis(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        data = await stats.error_analysis(ctx.db, ctx.user_id)
        total = int(data.get("totalErrors") or 0)
        if total <= 0:
            message = "错题本是空的（没有任何错题记录），请如实告知。"
        else:
            message = (
                f"错题共 {total} 道，其中待消灭 {data.get('activeErrors') or 0} 道、"
                f"已掌握 {data.get('mastered') or 0} 道（掌握率 {data.get('masterRate')}%）"
            )
        return ok(**{**data, "action": "error_analysis", "message": message})

    async def _growth(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        data = await stats.growth(ctx.db, ctx.user_id)
        return ok(
            **{
                **data,
                "action": "growth",
                "message": (
                    f"累计学习 {data.get('studyDays') or 0} 天，"
                    f"连续 {data.get('consecutiveDays') or 0} 天；"
                    f"收藏题库 {data.get('totalBanks') or 0} 个、"
                    f"笔记 {data.get('totalNotes') or 0} 篇"
                ),
            }
        )


__all__ = ["LearningStatsTool", "MAX_TREND_DAYS"]
