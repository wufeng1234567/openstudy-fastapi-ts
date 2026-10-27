"""
复习卷工具 —— 把「按薄弱点生成复习卷」接进对话（2026-10-26 v3）

## 这个工具为什么必须存在

`/userStats/reviewSheet` 这个 REST 接口和页面按钮早就做好了，但在**聊天里没有对应工具**。

实测后果很具体。用户说「帮我按薄弱点生成一份复习卷」，模型找不到工具，于是
**自己想办法**：

    委派给「题库专家」子代理 → 让它新建一个题库 → 把薄弱题复制进去 → 再导出

这条路走了 180 秒还没结束（实测直接超时），而且**改了用户的数据**（凭空多出一个题库）。
用户想要的只是一份能打印的文件。

所以这个工具的作用是：**给模型一条正确的路**，别让它去造题库。

## 为什么不给 `learning_stats` 加一个 action

`learning_stats` 的每个 action 都在**读统计数据**（overview / trend / diagnose …），
返回值是给模型看的数字与结论。

而这里要产出的是**文件**（要落盘、要下载链接），与 `bank_export` 同类。
`registry` 里已经有「导出 = 独立工具」的先例（见 `bank_export.py` 的注册注释），
把产物型能力和查询型能力混在一个工具里，会让模型误判"这只是查一下"。

## 与页面按钮的关系

同一个 `review_sheet_service.build_review_sheet()`，同一份产物。
区别只在入口：用户在页面上点按钮，或者在对话里说一句。
两边不会出现「聊天生成的和页面生成的不一样」—— 因为就是同一个函数。

## 只读

这个工具**不改任何用户数据**（不建题库、不写复习计划）。
所以 `needs_confirmation` 保持默认 False —— 让它需要点确认会多一次无意义的交互：
用户点「生成复习卷」本来就是期望它直接生成。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.question import QuestionMain
from app.services.ai.agent.base import AgentTool, ToolContext, fail, ok

#: 默认收录多少题
#:
#: 与页面按钮的取值范围（10~40）保持一致：少于 10 道不成一份卷子，
#: 多于 40 道用户一次做不完，"按优先级"就失去意义了。
DEFAULT_COUNT = 20
MIN_COUNT = 5
MAX_COUNT = 60


class ReviewSheetTool(AgentTool):
    name = "review_sheet"
    #: ⚠️ 描述与参数说明一律英文（进系统提示词 `{{TOOLS}}` 与 Function Calling）
    description = (
        "Generate a personalised review worksheet (复习卷) as a REAL Word (.docx) "
        "file the user can print and hand out. "
        "It reads the user's own practice history, works out which questions "
        "deserve attention (repeatedly failed / past their review window / nearly "
        "mastered), and lays them out as a printable paper:\n"
        "  · head: mastery-level table + subject table\n"
        "  · body: the picked questions in priority order, with room to write\n"
        "  · tail: a 7-day review plan table\n"
        "  · last page: answers & explanations (separate page, easy to tear off)\n"
        "Use it when the user asks for 复习卷 / 复习计划 / 薄弱点练习 / "
        "'what should I practise' / 'make me a practice sheet' / "
        "'print out the questions I keep getting wrong'. "
        "This produces a FILE only — it does NOT create or modify any question bank. "
        "If the user wants an existing bank exported as-is, use `bank_export` instead. "
        "The reply carries a `downloadUrl`; tell the user the file is ready, "
        "do NOT paste the raw URL."
    )
    #: 界面专用（只给前端看；不进 definitions() / describe()）
    label = "复习卷"
    description_zh = (
        "按薄弱点生成一份可打印的 Word 复习卷：卷首掌握度与学科表、"
        "正文按优先级排的题目（留作答空间）、卷尾七天复习计划表、附页答案。"
        "只产出文件，不改任何题库。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "count": {
                "type": "integer",
                "description": (
                    f"How many questions to include (default {DEFAULT_COUNT}, "
                    f"{MIN_COUNT}-{MAX_COUNT}). Pick a small number for "
                    "'just a few', larger when the user wants a full set. "
                    "If the user does not say, omit this field and the default is used."
                ),
            }
        },
        "required": [],
    }

    async def preview(  # noqa: D401 - 与基类同签名
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        """确认前不必展示额外信息：这个工具只读，产物是一份文件"""
        count = self._count(params)
        return {"title": "生成复习卷", "detail": f"最多收录 {count} 道题", "readOnly": True}

    @staticmethod
    def _count(params: Dict[str, Any]) -> int:
        """把模型可能给出的各种"数量"形式收敛成一个安全整数"""
        raw = params.get("count")
        try:
            n = int(raw)
        except (TypeError, ValueError):
            return DEFAULT_COUNT
        return max(MIN_COUNT, min(MAX_COUNT, n))

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        from app.services.ai.agent.tools.bank_export import save_export_file
        from app.services.review_sheet_service import build_review_sheet
        from app.services.study_diagnosis_service import diagnose

        count = self._count(params)

        # ① 诊断：决定"复习哪几道"
        #
        # ⚠️ diagnose 的 limit 是「**每一档**最多几道」，不是总数
        #    （七档乘起来能到好几十题）。所以取完再按总数截断一次。
        diag = await diagnose(ctx.db, user_id=ctx.user_id, limit=count)
        if not diag.get("hasData"):
            return fail(
                "还没有足够的练习记录来生成复习卷",
                "告诉用户先做几道题，诊断才有依据。不要编造一份空的复习卷，"
                "也不要说'已生成'。可以建议他从任意题库开始练 10 道左右。",
            )

        items: List[Dict[str, Any]] = list(diag.get("items") or [])[:count]
        if not items:
            return fail(
                "诊断没有挑出需要复习的题目",
                "这说明用户的作答记录都比较健康（或刚清空）。如实告诉用户"
                "暂时没有需要重点复习的题，不要改为'随机抽题'——那会误导用户。",
            )

        # ② 取完整题目
        #
        # ⚠️ 不能用 `diag["items"][i]["questionText"]`：那是**截断到 120 字**的
        #    预览文本，只够列表展示，粘到卷子上会缺内容。
        qids = [int(it["questionId"]) for it in items if it.get("questionId")]
        if not qids:
            return fail("诊断结果里没有可用的题目 id", "请如实告诉用户这次没能生成，建议重试")

        rows = (
            await ctx.db.execute(
                select(QuestionMain)
                .options(selectinload(QuestionMain.sub_questions))
                .where(QuestionMain.id.in_(qids), QuestionMain.status == "0")
            )
        ).scalars().all()

        # 题目被删/停用时会缺几条，这是正常的；按诊断的优先级顺序还原
        from app.api.v1.questions import format_question

        by_id = {q.id: format_question(q) for q in rows}
        level_of = {
            int(it["questionId"]): it.get("levelText")
            for it in items
            if it.get("questionId")
        }
        ordered: List[Dict[str, Any]] = []
        for qid in qids:
            q = by_id.get(qid)
            if not q:
                continue
            q["_levelText"] = level_of.get(qid)
            ordered.append(q)

        if not ordered:
            return fail(
                "诊断出的题目都已被删除或停用",
                "如实告诉用户这些题不在了（可能被删过），建议先做几道新题。"
                "不要用别的题顶上——那会让复习卷和诊断结论对不上。",
            )

        # ③ 出文件
        try:
            data = build_review_sheet(diag, ordered)
        except Exception as e:  # noqa: BLE001 - 渲染失败要给人话原因
            return fail(
                f"生成复习卷失败：{type(e).__name__}: {e}",
                "这是服务端渲染问题，不是用户数据的问题。请如实告诉用户生成失败，"
                "不要说成功；可以让他在『我的学习 → 学情统计』页面上用按钮再试一次。",
            )

        stamp = datetime.now().strftime("%Y%m%d")
        try:
            rel_path, filename = save_export_file(data, f"薄弱点复习卷_{stamp}.docx")
        except OSError as e:
            return fail(
                f"文件已生成但保存失败：{e}",
                "磁盘可能已满或没有写权限。请告诉用户稍后重试，不要谎称已生成",
            )

        summary = diag.get("summary") or {}
        return ok(
            action="review_sheet",
            reviewCount=len(ordered),
            fileName=filename,
            fileSize=len(data),
            # 前端产物卡片据此渲染「下载」按钮
            downloadUrl=f"/profile/{rel_path}",
            headline=diag.get("headline") or "",
            needsAttention=summary.get("needsAttention"),
            overdueCount=summary.get("overdueCount"),
            overallAccuracy=summary.get("overallAccuracy"),
            message=(
                f"已生成复习卷（{len(ordered)} 道题，含七天复习计划与答案页）。"
                f"{diag.get('headline') or ''}"
            ),
        )
