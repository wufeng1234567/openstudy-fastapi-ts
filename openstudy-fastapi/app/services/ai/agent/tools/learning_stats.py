"""
`learning_stats` —— 学习统计 + 学情诊断工具（Agent 自封装）

两块能力，边界很清楚：

一、**聚合数字**（overview / by_subject / trend / error_analysis / growth）
    对齐项目里那套「学习统计」接口的语义（`app/api/v1/user_stats.py`）——
    它们在「我的学习统计」页面上也能看到，是同一批数字。
    ⚠️ 数字**必须与页面一致**，所以这里不自己写查询：直接调
    `app/services/user_stats_service.py`，由它再调那五个路由处理函数（同一份实现）。

二、**逐题诊断**（diagnose / plan_review，2026-10-20 新增）
    聚合数字回答不了「这道题我练了 12 次为什么还是错」「我明明会了它怎么还在
    错题本里」。这部分读 `user_practice_log` 的**逐题序列**，做确定性诊断，
    见 `app/services/study_diagnosis_service.py`。

    ⚠️ 为什么这不是"又一个 AI 分析"：所有分档、间隔、排序都是**算出来的**，
    同一份数据永远得到同一个结论，可复现、可测试。LLM 的职责是**表达**诊断结果，
    而不是"看着几个数字自由发挥"—— 后者正是原来那个版本被用户吐槽"别的 ai 都能做"
    的根因。

写操作口径
==========
· 聚合五个字**全部只读**（`write_operation` 由 `needs_confirmation` 按 action 分）。
· `diagnose` 只读 —— 它是本工具最常被调用的 action（用户问「我最近学得怎么样」
  就走它），给只读的东西弹确认卡等于把那句最自然的对话彻底打断。
· `plan_review` **写** `user_question_error`（`next_review_time` / `review_count`），
  所以它需要确认。

⚠️ 一个**已知的历史口径问题**（不在本轮修，别顺手改）：`trend`
用 `datetime.now()`（本地时间）与库里 `create_time` 做日期分组，而
`user_practice_log.create_time` 是应用层写进去的本地朴素时间、`server_default`
那一路则是 PG 的 UTC —— 混着用会让「今天」的边界对不上 8 小时。
这是既有端点的既有行为，改了反而会让 Agent 与页面显示不一致。
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.services import study_diagnosis_service as sds
from app.services import user_stats_service as stats
from app.services.ai.agent.base import AgentTool, ToolContext, fail, ok
from app.services.ai.agent.tools.bank_export import _human_size

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
        "**diagnose=the REAL study diagnosis — STRONGLY PREFER THIS over overview when the "
        "user asks anything like 'how am I doing' / 'where am I weak' / 'what should I "
        "study' / 'am I making progress'. It reads the per-question attempt history and "
        "tells apart things raw numbers cannot: questions failed over and over (a prerequisite "
        "gap, not a practice gap), questions that are actually mastered but still sitting in "
        "the wrong-question book, questions whose review window has already passed, and "
        "cram-style study patterns. Each item carries a `level`, `advice` and "
        "`recommendedIntervalDays`.** "
        "plan_review=WRITE the computed review schedule into the wrong-question book "
        "(sets next_review_time / review_count) so the user can query what is due today. "
        "Use it when the user asks to set up a review plan or what to review today. "
        "This one WRITES data (it needs confirmation like other writes). "
        "diagnose_report=produce a downloadable PDF study report (headline, per-level "
        "breakdown, per-question diagnosis with advice, subject breakdown, study rhythm). "
        "Use it when the user wants to keep / print / hand over their study situation "
        "('give me a report', 'export it as PDF', 'send it to me', 'I want to print it'). "
        "The reply carries a `downloadUrl`; tell the user the report is ready instead of "
        "pasting the URL. "
        "These are the SAME numbers the user sees on their statistics page. "
        "NOTES: overview/by_subject/trend/error_analysis/growth are read-only aggregates; "
        "diagnose/plan_review are per-question analysis. "
        "For the actual LIST of wrong / favourite / marked questions use "
        "`question_flag_manage` (flag_type=error / favorite / marked) instead."
    )
    #: 界面专用（只给前端看；不进 definitions() / describe()）
    label = "学习统计"
    description_zh = (
        "读学习数据：overview=总览、by_subject=按科目、trend=趋势、"
        "error_analysis=错题分析、growth=成长情况；"
        "diagnose=学情诊断（逐题分析：哪几道反复失守 / 哪几道其实会了 / 哪几道欠复习）；"
        "plan_review=把复习计划写进错题本。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Operation to perform",
                "enum": [
                    "overview",
                    "by_subject",
                    "trend",
                    "error_analysis",
                    "growth",
                    "diagnose",
                    "plan_review",
                    "diagnose_report",
                ],
            },
            "days": {
                "type": "integer",
                "description": (
                    f"How many days the trend covers (used by trend; default "
                    f"{stats.TREND_DEFAULT_DAYS}, max {MAX_TREND_DAYS})."
                ),
            },
            "limit": {
                "type": "integer",
                "description": (
                    "Max questions per level returned by diagnose / plan_review "
                    f"(default {sds.MAX_ITEMS_PER_LEVEL}, max 50)."
                ),
            },
        },
        "required": ["action"],
    }
    #: 大部分 action 只读；`plan_review` 会写库（见 `needs_confirmation`）
    write_operation = True

    #: 会写库的 action（其余仍按只读处理）
    _WRITE_ACTIONS = {"plan_review"}

    def needs_confirmation(self, params: Dict[str, Any]) -> bool:
        """只有 `plan_review` 需要确认（它会写 `user_question_error`）

        ⚠️ 为什么不是「整个工具都写操作」就一律确认：`diagnose` 是最常被调用的
        那一个（用户问「我最近学得怎么样」就会走它），给它弹卡等于**每次问学情都
        先点一次确认**，把那句最自然的对话彻底打断。而它确实不写任何数据 ——
        按 action 分，才是诚实的。
        """
        return str(params.get("action") or "") in self._WRITE_ACTIONS

    def undo_plan(
        self,
        params: Dict[str, Any],
        result: Dict[str, Any],
        before: Dict[str, Any] | None = None,
    ) -> Dict[str, Any] | None:
        """`plan_review` 写了库，但**刻意不做逆操作** —— 并说清为什么

        `plan_review` 只写 `user_question_error` 的两列：`next_review_time` 与
        `review_count`。它们存的是**系统算出来的建议值**（不是用户输入的内容），
        而且：

          · 反复调用是幂等的（同一份作答数据算出同一批日期）；
          · 用户想改计划，说一句「重新排一下复习计划」就会整批重算覆盖；
          · 撤销它没有任何实际收益 —— 把「建议什么时候复习」改回 NULL，
            用户既少了一个可用的功能，也没拿回任何东西。

        所以这里不声明逆操作，但**必须给一句人话原因**（否则用户点回退会看到
        笼统的「这个操作还没有回退实现」，那是假的 —— 我们是想清楚了不做）。
        """
        action = str(params.get("action") or "")
        if action == "plan_review":
            return {
                "undoable": False,
                "reason": "复习计划是按你的作答记录算出来的建议值，重新排一次就会覆盖，不需要撤销",
            }
        return None

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        action = str(params.get("action") or "")
        handler = {
            "overview": self._overview,
            "by_subject": self._by_subject,
            "trend": self._trend,
            "error_analysis": self._error_analysis,
            "growth": self._growth,
            "diagnose": self._diagnose,
            "plan_review": self._plan_review,
            "diagnose_report": self._diagnose_report,
        }.get(action)
        if handler is None:
            return fail(
                f"未知操作: {action}",
                "action 只能是 overview / by_subject / trend / error_analysis / growth "
                "/ diagnose / plan_review / diagnose_report",
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

    # ------------------------------------------------------------------
    # 学情诊断（2026-10-20 新增）
    # ------------------------------------------------------------------

    async def _diagnose(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        """逐题学情诊断 —— 与上面五个「聚合数字」的区别见 `study_diagnosis_service`

        ⚠️ 这里**不加**任何自然语言总结：`headline` / `suggestions` / `advice`
        都是算法给的中文判断，模型拿到后**应当复述并解释**，但**不许**自己另发明
        一套分档或数字 —— 那会让同一份数据在两次对话里说出不同结论。
        回执里的 `message` 只是一句"共诊断出什么"，不替代 headline。
        """
        raw = params.get("limit")
        limit = sds.MAX_ITEMS_PER_LEVEL
        if raw is not None:
            try:
                limit = max(1, min(int(raw), 50))
            except (TypeError, ValueError):
                limit = sds.MAX_ITEMS_PER_LEVEL

        diag = await sds.diagnose(ctx.db, ctx.user_id, limit=limit)
        if not diag.get("hasData"):
            return ok(
                action="diagnose",
                hasData=False,
                headline=diag["headline"],
                suggestions=diag["suggestions"],
                message=diag["headline"] + "（没有任何作答记录，请如实告知，不要编造诊断）",
            )

        summary = diag["summary"]
        levels = diag.get("byLevel") or {}
        level_text = "、".join(
            f"{v['text']} {v['count']} 道" for v in levels.values()
        )
        # ⚠️ `message` 的**第一句必须是 headline**（结论 / 该做什么），计数放括号里。
        #
        # 为什么这个顺序重要（2026-10-20 实测踩到）：模型极爱照抄 `message` 的开头作为
        # 回答的开头。原来这段是「诊断了 8 道题…：反复失守 2 道、欠复习 2 道…。有 2 道
        # 题已经过了复习窗口」，实测回答就变成了「整体状况：最近 30 天里你只有 2 天在
        # 练习，共做了 27 次题…」—— 又回到"复述聚合数字"那个老毛病上了。
        # 把 headline 提到最前，回答自然就以行动建议开头；这不是靠提示词求模型，
        # 而是让它唯一能抄的那句话本身就是对的。
        message = (
            f"{diag['headline']}"
            f"（依据：{summary['questionsSeen']} 道题的 {summary['totalAttempts']} 次作答，"
            f"{level_text}）"
        )
        return ok(
            action="diagnose",
            hasData=True,
            headline=diag["headline"],
            summary=summary,
            byLevel=diag["byLevel"],
            bySubject=diag["bySubject"],
            activity=diag["activity"],
            items=diag["items"],
            suggestions=diag["suggestions"],
            message=message,
        )

    async def _plan_review(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        """把诊断算出的复习间隔写回错题本（`next_review_time` / `review_count`）

        写库部分在 `study_diagnosis_service.persist_plan`（诊断与写库刻意分开：
        诊断要能随便调，写库只能由用户显式触发 —— 见该模块 docstring）。
        """
        raw = params.get("limit")
        limit = 50
        if raw is not None:
            try:
                limit = max(1, min(int(raw), 200))
            except (TypeError, ValueError):
                limit = 50

        result = await sds.persist_plan(ctx.db, ctx.user_id, limit=limit)
        return ok(action="plan_review", **result)

    async def _diagnose_report(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        """生成一份可下载的学情报告 PDF

        产物落盘与下载链路复用 `bank_export.save_export_file`（同一个 `export/` 目录、
        同一个 `/profile/...` 静态挂载、前端同一张产物卡片）—— 见那个函数的注释。

        ⚠️ 它是**只读**的（不写库），所以不进 `_WRITE_ACTIONS`：生成报告不改任何数据，
        为它弹确认卡等于让「给我一份报告」这句话多一次点击。
        """
        from datetime import datetime

        from app.services.ai.agent.tools.bank_export import save_export_file
        from app.services.diagnosis_report_service import export_diagnosis_pdf

        raw = params.get("limit")
        limit = sds.MAX_ITEMS_PER_LEVEL
        if raw is not None:
            try:
                limit = max(1, min(int(raw), 50))
            except (TypeError, ValueError):
                limit = sds.MAX_ITEMS_PER_LEVEL

        diag = await sds.diagnose(ctx.db, ctx.user_id, limit=limit)

        # 姓名：报告抬头用。取不到就留空（不印「学生：」这种半截），绝不因此失败
        user_name = ""
        try:
            from app.models.user import SysUser

            user_name = str(
                await ctx.db.scalar(
                    SysUser.__table__.select()
                    .with_only_columns(SysUser.user_name)
                    .where(SysUser.user_id == int(ctx.user_id))
                )
                or ""
            )
        except Exception:  # noqa: BLE001 - 姓名是装饰，取不到不影响报告
            user_name = ""

        try:
            pdf = export_diagnosis_pdf(diag, user_name=user_name)
        except Exception as e:  # noqa: BLE001
            return fail(
                f"生成学情报告失败：{type(e).__name__}: {e}",
                "这是服务端渲染问题，不是用户数据的问题。请如实告知报告生成失败，"
                "可以先把诊断结论用文字讲给用户（改用 action=diagnose）",
            )

        stamp = datetime.now().strftime("%Y%m%d")
        filename = f"学情诊断报告-{stamp}.pdf"
        try:
            rel_path, saved_name = save_export_file(pdf, filename)
        except OSError as e:
            return fail(
                f"报告已生成但保存失败：{e}",
                "磁盘可能已满或没有写权限。请如实告知，不要谎称生成成功",
            )

        size = len(pdf)
        return ok(
            action="diagnose_report",
            format="pdf",
            hasData=bool(diag.get("hasData")),
            headline=diag.get("headline") or "",
            fileName=saved_name,
            fileSize=size,
            fileSizeText=_human_size(size),
            downloadUrl=f"/profile/{rel_path}",
            message=(
                f"已生成学情诊断报告 PDF（{_human_size(size)}），可以直接下载"
                if diag.get("hasData")
                else f"已生成学情报告（{_human_size(size)}），但里面还没有你的作答数据"
            ),
        )


__all__ = ["LearningStatsTool", "MAX_TREND_DAYS"]
