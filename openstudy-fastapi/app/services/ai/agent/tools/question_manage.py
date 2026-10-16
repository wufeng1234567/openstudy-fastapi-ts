"""
`question_manage` —— 题目管理工具（Agent 自封装）

对齐 springboot3 的 `QuestionManageTool`。**AI 自动建题库的关键在 `batch_import`**：
模型读文档 → 转成题目 JSON 数组 → 一次工具调用批量入库。

这里承担了三件「不做就一定会翻车」的事：

1. **JSON 三级修复**（`json_repair.parse_json_array`）
   模型吐的长 JSON 数组经常带 markdown 围栏 / LaTeX 未转义反斜杠 / 被截断，
   任何一种都会让整批导入报废。三级回退能把大部分批次救回来。

2. **逐题 SAVEPOINT**
   一道题的数据有问题（题干过长、题型越界）不该拖垮另外 40 道。
   每题一个 `begin_nested()`，失败的题只回滚自己，其余照常入库。

3. **【图N】标记替换**
   文档里的插图位置由标记承载；上传的图片先落盘成 `/profile/upload/...`
   再回填成 `<img>`，和前端 AI 搭建题库的导入结果保持一致。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import String, cast, delete, func, or_, select

from app.models.question import QuestionBank, QuestionMain, QuestionSub
from app.services import question_write_service as qws
from app.services.ai.agent import json_repair
from app.services.ai.agent.base import (
    AgentTool,
    ToolContext,
    as_list as _as_list,
    fail,
    ok,
)

#: 需要用户确认的动作
_WRITE_ACTIONS = {
    "create",
    "batch_import",
    "update",
    "delete",
    "delete_many",
    "clear_questions",
}

#: `【图0】` 形式的图片占位标记
_IMAGE_MARKER = re.compile(r"【图(\d+)】")

#: 一次 batch_import 最多导入多少题（与提示词里的「每批 ≤15 题」相呼应，留余量）
MAX_BATCH_SIZE = 60

#: 确认卡片里的样例题干最多给几条（与 `note_manage._PREVIEW_SAMPLE` 同口径）
_PREVIEW_SAMPLE = 5

#: 题干最长字符数（question_main.question_text 是 TEXT，但过长没有意义）
MAX_QUESTION_TEXT = 20000


def _replace_image_markers(text: str, image_urls: List[str]) -> tuple:
    """把 `【图N】` 换成 `<img src="...">`；返回 (新文本, 被丢弃的标记列表)"""
    if not text or "【图" not in text:
        return text, []

    dropped: List[str] = []

    def _sub(match: "re.Match[str]") -> str:
        index = int(match.group(1))
        if 0 <= index < len(image_urls) and image_urls[index]:
            url = image_urls[index]
            return (
                f'<img src="{url}" '
                'style="max-width:100%;height:auto;margin:10px 0;border-radius:4px;" />'
            )
        dropped.append(match.group(0))
        return ""

    return _IMAGE_MARKER.sub(_sub, text), dropped


class QuestionManageTool(AgentTool):
    name = "question_manage"
    #: ⚠️ 描述与参数说明一律英文 —— 同 `bank_manage`，它们会进系统提示词与
    #: Function Calling 定义两条注入通道，必须与全英文的系统提示词保持同一语言。
    description = (
        "Manage questions inside a question bank. "
        "action values: list=list questions of a bank (pass `bank_id` or `bank_name`), "
        "detail=show one question (options / answer / analysis / sub-questions), "
        "search=search questions by keyword (matches question text / analysis / reading "
        "material / options; `bank_id`/`bank_name` are OPTIONAL — omit them to search ALL "
        "your banks), create=create ONE question, "
        "batch_import=**bulk import questions (the AI bank-building path; pass one JSON "
        "array of question objects)**, update=update a question, delete=delete ONE question, "
        "delete_many=delete SEVERAL questions at once (pass `question_ids` and/or "
        "`question_indexes` for one bank), clear_questions=delete ALL questions of a bank. "
        "NOTE: to work with the BANKS themselves, use `bank_manage` instead."
    )
    #: 界面专用（只给前端看；不进 definitions() / describe()）
    label = "题目管理"
    description_zh = (
        "题库里题目的增删改查：list=列某个库的题、detail=看一道题的详情（选项 / 答案 / 解析 / 小题）、"
        "search=按关键词搜题、create=录题、batch_import=批量导入、update=改题、"
        "delete=删题、delete_many=批量删、clear_questions=清空某库的全部题目。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Operation to perform",
                "enum": [
                    "list",
                    "detail",
                    "search",
                    "create",
                    "batch_import",
                    "update",
                    "delete",
                    "delete_many",
                    "clear_questions",
                ],
            },
            "bank_id": {
                "type": "integer",
                "description": "Bank ID (alternative to bank_name)",
            },
            "bank_name": {
                "type": "string",
                "description": (
                    "Bank name (alternative to bank_id). Using the name directly is fine; "
                    "no need to look up the ID first."
                ),
            },
            "question_id": {
                "type": "integer",
                "description": (
                    "Question ID (alternative to question_index for detail/update/delete)"
                ),
            },
            "question_index": {
                "type": "integer",
                "description": (
                    "1-based position of the question in the bank "
                    "(e.g. 'show me question 3' -> 3)"
                ),
            },
            "question_type": {
                "type": "integer",
                "description": (
                    "Question type: 1=single choice 2=multiple choice 3=true/false "
                    "4=fill-in-the-blank 5=short answer 6=reading comprehension 7=cloze"
                ),
            },
            "question_text": {
                "type": "string",
                "description": (
                    "Question text (required for create; optional for update; used as the "
                    "search keyword for search)"
                ),
            },
            "options": {
                "type": "array",
                "description": (
                    'Options array for choice questions, e.g. ["option A","option B"]'
                ),
                "items": {"type": "string"},
            },
            "answer": {
                "type": "string",
                "description": (
                    'Correct answer: single choice -> index as string "0"/"1"/"2"; '
                    'multiple choice -> "0,1,2"; true/false -> "true"/"false"; '
                    "fill-in / short answer -> the content itself"
                ),
            },
            "analysis": {
                "type": "string",
                "description": "Explanation / analysis (optional)",
            },
            "difficulty": {
                "type": "integer",
                "description": "1=easy 2=medium (default) 3=hard 4=very hard",
            },
            "content": {
                "type": "string",
                "description": (
                    "Reading material body (used by composite question types such as "
                    "reading comprehension)"
                ),
            },
            "has_sub_questions": {
                "type": "integer",
                "description": (
                    "Whether the question has sub-questions: 0=no, 1=yes "
                    "(reading comprehension / cloze)"
                ),
            },
            "sub_questions": {
                "type": "array",
                "description": "Sub-question array (composite question types)",
                "items": {"type": "object"},
            },
            "questions": {
                "type": "string",
                "description": (
                    "**Required for batch_import**: the question array as a JSON STRING. "
                    'Each item looks like {"questionType":1,"questionText":"...",'
                    '"options":["A","B"],"answer":"0","analysis":"..."}. '
                    "NOTE: it is a string, not an array, and inner double quotes must be "
                    "escaped. Max 15 questions per call; split larger sets into several calls."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Max number of questions returned by list (default 20)",
            },
            "offset": {
                "type": "integer",
                "description": (
                    "0-based offset for list (default 0). Use with `limit` to page through a "
                    "bank with more questions than one page shows; the reply includes `total` "
                    "and `hasMore`."
                ),
            },
            "question_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Question IDs to delete in bulk (used by delete_many).",
            },
            "question_indexes": {
                "type": "array",
                "items": {"type": "integer"},
                "description": (
                    "1-based positions to delete in bulk (used by delete_many). Requires "
                    "`bank_id` or `bank_name`; resolved against the same order as list."
                ),
            },
        },
        "required": ["action"],
    }
    write_operation = True

    #: 删除类动作：即使 autoConfirm 开着也必须二次确认
    _DESTRUCTIVE_ACTIONS = {"delete", "delete_many", "clear_questions"}

    def needs_confirmation(self, params: Dict[str, Any]) -> bool:
        return str(params.get("action") or "") in _WRITE_ACTIONS

    def is_destructive(self, params: Dict[str, Any]) -> bool:
        return str(params.get("action") or "") in self._DESTRUCTIVE_ACTIONS

    async def preview(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        """确认前把「影响范围」讲清楚：哪个题库、多少题、前几题长什么样

        · `batch_import`：导入多少条 + 前几题题干
        · `delete` / `update`：题目题干
        · `delete_many`：`count` + `sample`（题干前 80 字）
        · `clear_questions`：`bankName` + `count`
        ⚠️ 破坏性动作的题库名一律**只读反查**（`_preview_bank`）后给出，**不回显**模型传进来的
           字符串 —— 否则卡片会显示一个库里并不存在的题库名，用户确认的和实际删的不是一回事。
        """
        try:
            action = str(params.get("action") or "")
            preview: Dict[str, Any] = {"action": action}

            if action in ("batch_import",):
                items, _, _ = self._parse_questions(params)
                preview["count"] = len(items)
                preview["sample"] = [
                    str(q.get("questionText") or q.get("question_text") or "")[:60]
                    for q in items[:5]
                ]
                # 需求二：给前端一份**完整可编辑草稿**（题库信息 + 全部题目）。
                # 旧的 count / sample 键保留（向后兼容）；draft 是新增键，
                # 老前端不认识也不会因此变哑。
                bank, _why = await self._preview_bank(params, ctx)
                preview["draft"] = self._build_import_draft(bank, params, items)
            elif action in ("update", "delete"):
                question = await self._resolve_question(params, ctx)
                if question is not None and not isinstance(question, dict):
                    preview["questionText"] = (question.question_text or "")[:80]
            elif action in ("delete_many", "clear_questions"):
                preview.update(await self._preview_delete_scope(action, params, ctx))

            # 其余 action 才回显模型给的 bank_name（上面两个破坏性动作用的是真实题库名，
            # 不能被覆盖回去）
            if "bankName" not in preview and params.get("bank_name"):
                preview["bankName"] = params["bank_name"]
            return preview
        except Exception as e:  # noqa: BLE001 - 预览失败不影响执行
            logger.warning("[agent] question_manage preview 失败: {}", e)
            return {}

    async def _preview_bank(self, params: Dict[str, Any], ctx: ToolContext):
        """预览专用的**只读**题库定位：返回 `(bank, 一句人话)`

        不复用 `_resolve_bank`：它给的是 `fail()` 信封（那是给**模型**看的），
        而预览要的是「给**用户**看的一句人话」。两者受众不同，别硬凑一份。
        """
        bank_id = params.get("bank_id")
        bank_name = (params.get("bank_name") or "").strip()
        if bank_id is not None:
            try:
                bank = await ctx.db.get(QuestionBank, int(bank_id))
            except (TypeError, ValueError):
                return None, "（题库不存在：bank_id 无法识别）"
            # ⚠️「不存在」与「不属于你」回**同一句**（与 `_resolve_bank` 同口径，2026-09-22 补）：
            #    预览文案会原样出现在确认卡片上，分开说同样是「这个 id 存在」的探测预言机。
            if bank is None or int(bank.user_id or 0) != int(ctx.user_id):
                return None, "（题库不存在或不属于你：请先用 bank_manage list 确认）"
            return bank, ""
        if bank_name:
            bank = await qws.find_bank_by_name(ctx.db, ctx.user_id, bank_name)
            if bank is None:
                return None, "（没有找到这个题库：名称需要与题库列表完全一致）"
            return bank, ""
        return None, "（未指定题库）"

    async def _preview_delete_scope(
        self, action: str, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        """`delete_many` / `clear_questions` 的影响面（**只读**：查询可以，写一律不许）"""
        bank, why = await self._preview_bank(params, ctx)
        if bank is None:
            # 查不到就**明说**，不回显模型给的字符串
            return {"bankName": why or "（题库不存在）"}

        out: Dict[str, Any] = {"bankName": bank.bank_name}

        if action == "clear_questions":
            # 与真删除同口径：`_clear_questions` 连「已软删/非正常状态」的题目一起清
            out["count"] = int(
                await ctx.db.scalar(
                    select(func.count()).where(QuestionMain.bank_id == bank.id)
                )
                or 0
            )
            return out

        # delete_many：按与真删除**同一套**解析口径算出「会删哪几条」
        ids: List[int] = []
        for value in _as_list(params.get("question_ids")):
            try:
                ids.append(int(value))
            except (TypeError, ValueError):
                continue
        indexes: List[int] = []
        for value in _as_list(params.get("question_indexes")):
            try:
                indexes.append(int(value))
            except (TypeError, ValueError):
                continue
        if indexes:
            ordered = await self._ordered_question_ids(ctx, bank.id)
            ids.extend(ordered[i - 1] for i in indexes if 1 <= i <= len(ordered))

        final_ids = list(dict.fromkeys(ids))
        texts: List[str] = []
        if final_ids:
            rows = (
                await ctx.db.execute(
                    select(QuestionMain.question_text).where(
                        QuestionMain.id.in_(final_ids),
                        QuestionMain.bank_id == bank.id,
                    )
                )
            ).all()
            texts = [str(r[0] or "")[:80] for r in rows]

        out["count"] = len(texts)
        out["sample"] = texts[:_PREVIEW_SAMPLE] or ["（没有找到要删除的题目）"]
        return out

    # ------------------------------------------------------------------

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        action = str(params.get("action") or "")
        handlers = {
            "list": self._list,
            "detail": self._detail,
            "search": self._search,
            "create": self._create,
            "batch_import": self._batch_import,
            "update": self._update,
            "delete": self._delete,
            "delete_many": self._delete_many,
            "clear_questions": self._clear_questions,
        }
        handler = handlers.get(action)
        if handler is None:
            return fail(
                f"未知操作: {action}",
                "action 只能是 list / detail / search / create / batch_import / update / delete",
            )
        return await handler(params, ctx)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    async def _list(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        bank = await self._resolve_bank(params, ctx)
        if isinstance(bank, dict):  # fail 信封
            return bank

        limit = max(int(params.get("limit") or 20), 1)
        offset = max(int(params.get("offset") or 0), 0)
        query = select(QuestionMain).where(
            QuestionMain.bank_id == bank.id, QuestionMain.status == "0"
        )
        if params.get("question_type") is not None:
            query = query.where(QuestionMain.question_type == int(params["question_type"]))
        if params.get("difficulty") is not None:
            query = query.where(QuestionMain.difficulty == int(params["difficulty"]))
        query = (
            query.order_by(QuestionMain.sort_order, QuestionMain.id)
            .offset(offset)
            .limit(limit)
        )

        result = await ctx.db.execute(query)
        questions = list(result.scalars().all())
        total = int(
            await ctx.db.scalar(
                select(func.count()).where(
                    QuestionMain.bank_id == bank.id, QuestionMain.status == "0"
                )
            )
            or 0
        )

        return ok(
            action="list",
            bankName=bank.bank_name,
            bankId=bank.id,
            offset=offset,
            count=len(questions),
            total=total,
            hasMore=offset + len(questions) < total,
            questions=[
                qws.question_brief(q, with_detail=False) for q in questions
            ],
        )

    async def _detail(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        question = await self._resolve_question(params, ctx)
        if isinstance(question, dict):
            return question

        subs = await self._load_subs(ctx, question.id)
        return ok(
            action="detail",
            question=qws.question_brief(question, len(subs), with_detail=True),
            subQuestions=[
                {
                    "questionType": s.question_type,
                    "questionText": s.question_text,
                    "options": s.options,
                    "answer": s.answer,
                    "analysis": s.analysis,
                }
                for s in subs
            ],
        )

    async def _search(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        keyword = (params.get("question_text") or "").strip()
        if not keyword:
            return fail("搜索需要 question_text 作为关键词", "请把要搜索的关键词放在 question_text 里")

        limit = max(int(params.get("limit") or 20), 1)
        offset = max(int(params.get("offset") or 0), 0)
        like = f"%{keyword}%"
        # 搜索范围扩到：题干 / 解析 / 阅读材料正文 / 选项
        #（options 是 JSON 列，MySQL 需先 CAST 成字符串才能 LIKE）
        # 条件先攒起来，因为「查一页」和「数总量」要共用同一套过滤。
        conditions = [
            QuestionMain.status == "0",
            or_(
                QuestionMain.question_text.like(like),
                QuestionMain.analysis.like(like),
                QuestionMain.content.like(like),
                cast(QuestionMain.options, String).like(like),
            ),
        ]
        # 题库是**可选**的：
        #   给了 bank_id / bank_name → 只在该题库内搜；
        #   没给（「帮我找关于二次函数的题」）→ 在「我自己的全部题库」里搜。
        # 两种情况都限定在用户自己的题库（Agent 不该搜到别人的题）。
        if params.get("bank_id") is not None or (params.get("bank_name") or "").strip():
            bank = await self._resolve_bank(params, ctx)
            if isinstance(bank, dict):  # fail 信封
                return bank
            scoped_banks = [bank]
        else:
            scoped_banks = await qws.list_user_banks(ctx.db, ctx.user_id)

        bank_ids = [b.id for b in scoped_banks]
        if not bank_ids:
            return ok(action="search", count=0, total=0, questions=[], keyword=keyword)
        conditions.append(QuestionMain.bank_id.in_(bank_ids))

        # 命中总量必须单独数一次：只回一页的话，模型和前端都无从知道「还有多少条」，
        # 卡片摘要就会把「本次返回 20 条」说成「共 20 条」。
        total = int(await ctx.db.scalar(select(func.count()).where(*conditions)) or 0)

        result = await ctx.db.execute(
            select(QuestionMain)
            .where(*conditions)
            .order_by(QuestionMain.sort_order, QuestionMain.id)
            .offset(offset)
            .limit(limit)
        )
        questions = list(result.scalars().all())
        bank_names = {b.id: b.bank_name for b in scoped_banks}
        return ok(
            action="search",
            keyword=keyword,
            offset=offset,
            count=len(questions),
            total=total,
            hasMore=offset + len(questions) < total,
            questions=[
                {**qws.question_brief(q), "bankName": bank_names.get(q.bank_id)}
                for q in questions
            ],
        )

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    async def _create(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        bank = await self._resolve_bank(params, ctx)
        if isinstance(bank, dict):
            return bank
        if bank is None:
            return fail("未指定题库", "请提供 bank_name 或 bank_id")

        question_text = str(params.get("question_text") or "").strip()
        if not question_text:
            return fail("创建题目需要题干", "请提供 question_text")

        text, dropped = _replace_image_markers(
            question_text, list((ctx.extra or {}).get("image_urls") or [])
        )
        question = await qws.create_question(
            ctx.db,
            bank_id=bank.id,
            question_type=self._question_type(params),
            question_text=text,
            answer=str(params.get("answer") or ""),
            options=params.get("options"),
            analysis=params.get("analysis"),
            content=params.get("content"),
            difficulty=int(params.get("difficulty") or 2),
            sort_order=await self._next_sort_order(ctx, bank.id),
            sub_questions=params.get("sub_questions"),
        )
        return ok(
            action="create",
            questionId=question.id,
            bankName=bank.bank_name,
            message=f"已在「{bank.bank_name}」中创建题目（ID={question.id}）",
            droppedMarkers=dropped,
        )

    @staticmethod
    def _parse_questions(params: Dict[str, Any]) -> tuple:
        """把 `questions` 参数解析成题目列表（**预览与导入共用**，避免两条路漂移）

        返回 `(items, warnings, strategy)`：
          · `items` 已按 `MAX_BATCH_SIZE` 截断（与真正导入的上限**同一个**，
            所以预览草稿不会比实际导入的更大）；
          · `warnings` / `strategy` 是 `json_repair.parse_json_array` 的产物。
        ⚠️ 解析失败时返回空列表（不抛）—— 调用方各自决定把失败讲成什么话。
        """
        raw = params.get("questions")
        if isinstance(raw, list):  # 模型偶尔直接给数组
            raw = _dumps(raw)
        items, warnings, strategy = json_repair.parse_json_array(str(raw or ""))
        if len(items) > MAX_BATCH_SIZE:
            items = items[:MAX_BATCH_SIZE]
            warnings.append(f"单批最多 {MAX_BATCH_SIZE} 题，超出部分已忽略")
        return items, warnings, strategy

    @staticmethod
    def _build_import_draft(
        bank: Any, params: Dict[str, Any], items: List[Any]
    ) -> Dict[str, Any]:
        """组装建库导入的**可编辑草稿**（需求二）

        形状（字段用 camelCase，前端直接渲染）::

            {
              "kind": "question_bank_import",
              "bank": {"bankId": 12, "bankName": "…", "subject": "…",
                       "description": "…", "isPublic": 0},
              "questions": [ {...}, ... ]   # 与真正导入完全同一份（同一解析器 + 同一上限）
            }

        题库还没解析到时（例如模型打算先 create）用参数里的 bank_id / bank_name 兜底，
        其余字段留空 —— 前端仍能渲染「待建题库」的编辑框。
        """
        if bank is not None:
            bank_info = {
                "bankId": bank.id,
                "bankName": bank.bank_name,
                "subject": bank.subject,
                "description": bank.description,
                "isPublic": bank.is_public,
            }
        else:
            bank_info = {
                "bankId": params.get("bank_id"),
                "bankName": (params.get("bank_name") or "").strip() or None,
                "subject": None,
                "description": None,
                "isPublic": 0,
            }
        return {
            "kind": "question_bank_import",
            "bank": bank_info,
            "questions": list(items),
        }

    async def _batch_import(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        """批量导入 —— AI 自动建题库的主通道"""
        bank = await self._resolve_bank(params, ctx)
        if isinstance(bank, dict):
            return bank
        if bank is None:
            return fail("未指定题库", "请提供 bank_name 或 bank_id")

        raw = params.get("questions")
        if isinstance(raw, list):  # 模型偶尔直接给数组
            raw = _dumps(raw)
        if not raw:
            return fail(
                "batch_import 缺少 questions",
                'questions 必须是题目数组的 JSON 字符串，形如 [{"questionType":1,'
                '"questionText":"...","answer":"0"}]',
            )

        items, warnings, strategy = self._parse_questions(params)
        if not items:
            detail = "；".join(warnings[-2:]) if warnings else "内容不是合法的 JSON 数组"
            return fail(
                f"题目 JSON 解析失败（已尝试多种修复策略）：{detail}",
                "请重新输出 questions，确保是合法的 JSON 数组字符串，"
                "且内部双引号使用 \\\" 转义",
            )

        image_urls = list((ctx.extra or {}).get("image_urls") or [])
        start_order = await self._next_sort_order(ctx, bank.id)

        imported = 0
        failed = 0
        errors: List[str] = []
        dropped_markers: List[str] = []

        for index, item in enumerate(items):
            try:
                # 逐题 SAVEPOINT：单题失败不牵连整批
                async with ctx.db.begin_nested():
                    question_text = str(
                        item.get("questionText") or item.get("question_text") or ""
                    ).strip()
                    if not question_text:
                        raise ValueError("缺少 questionText（题干）")
                    if len(question_text) > MAX_QUESTION_TEXT:
                        raise ValueError(f"题干过长（{len(question_text)} 字）")

                    question_type = self._question_type(item)
                    if not 1 <= question_type <= 7:
                        raise ValueError(f"questionType 越界：{question_type}（应为 1-7）")

                    text, dropped = _replace_image_markers(question_text, image_urls)
                    dropped_markers.extend(dropped)

                    analysis, dropped_analysis = _replace_image_markers(
                        str(item.get("analysis") or ""), image_urls
                    )
                    dropped_markers.extend(dropped_analysis)

                    subs = item.get("sub_questions") or item.get("subQuestions") or []
                    if not isinstance(subs, list):
                        subs = []

                    await qws.create_question(
                        ctx.db,
                        bank_id=bank.id,
                        question_type=question_type,
                        question_text=text,
                        answer=str(item.get("answer") if item.get("answer") is not None else ""),
                        options=item.get("options"),
                        analysis=analysis or None,
                        content=item.get("content"),
                        difficulty=int(item.get("difficulty") or 2),
                        sort_order=start_order + index,
                        sub_questions=subs,
                        recalc_total=False,
                    )
                imported += 1
            except Exception as e:  # noqa: BLE001 - 单题失败继续下一题
                failed += 1
                snippet = str(
                    item.get("questionText") or item.get("question_text") or ""
                )[:30]
                errors.append(f"第 {index + 1} 题（{snippet}…）导入失败：{e}")
                logger.warning("[agent] batch_import 第 {} 题失败: {}", index + 1, e)

        total = await qws.recalc_bank_total(ctx.db, bank.id)

        if imported == 0:
            return fail(
                f"整批导入失败（{failed} 题全部报错）：" + "；".join(errors[:3]),
                "请修正题目数据后重新调用 batch_import，每道题都必须有 "
                "questionText，且 questionType 在 1-7 之间",
                step="insert",
            )

        return ok(
            action="batch_import",
            bankId=bank.id,
            bankName=bank.bank_name,
            imported=imported,
            failed=failed,
            bankTotal=total,
            parseStrategy=strategy,
            errors=errors[:10],
            warnings=warnings[-3:],
            droppedImageMarkers=sorted(set(dropped_markers)),
            message=(
                f"已向「{bank.bank_name}」导入 {imported} 道题目"
                + (f"（{failed} 道失败）" if failed else "")
                + f"，题库现有 {total} 题"
            ),
        )

    async def _update(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        question = await self._resolve_question(params, ctx)
        if isinstance(question, dict):
            return question

        changed: List[str] = []
        if params.get("question_type") is not None:
            question.question_type = self._question_type(params)
            changed.append("question_type")
        if (params.get("question_text") or "").strip():
            question.question_text = params["question_text"].strip()
            changed.append("question_text")
        if params.get("answer") is not None:
            question.answer = str(params["answer"])
            changed.append("answer")
        if params.get("options") is not None:
            question.options = qws.normalize_options(params["options"])
            changed.append("options")
        if (params.get("analysis") or "").strip():
            question.analysis = params["analysis"].strip()
            changed.append("analysis")
        if params.get("difficulty") is not None:
            question.difficulty = int(params["difficulty"])
            changed.append("difficulty")

        if not changed:
            return fail(
                "没有提供任何要修改的字段",
                "请至少给出 question_text / answer / options / analysis / question_type 之一",
            )

        subs = params.get("sub_questions")
        if isinstance(subs, list):
            # 子题全量替换（与后台 update 接口口径一致）
            for old in await self._load_subs(ctx, question.id):
                await ctx.db.delete(old)
            await ctx.db.flush()
            await qws.insert_sub_questions(ctx.db, question.id, subs)
            question.has_sub_questions = 1 if subs else 0
            changed.append("sub_questions")

        await ctx.db.flush()
        return ok(
            action="update",
            questionId=question.id,
            changed=changed,
            message=f"已更新题目（ID={question.id}）：{', '.join(changed)}",
        )

    async def _purge_questions(self, ctx: ToolContext, question_ids: List[int]) -> int:
        """物理删除一批题目（含子题、笔记关联），返回**真正删掉**的条数

        统一走 **Core 批量 delete**：
          · ORM `db.delete(question)` 会把 `question_sub.main_id` 置空（NOT NULL）→ IntegrityError；
          · ⚠️ **PG 里这批外键全是 `delete_rule=NO ACTION`（没有 ON DELETE CASCADE）** ——
            2026-09-22 实测 `information_schema.referential_constraints`：
            `question_sub.main_id → question_main`、`note_question.question_id → question_main`、
            `user_question_{error,favorite,marked}.question_id → question_main` 全部 NO ACTION。
            （旧注释写的是「DB 对 question_sub / user_question_* 有 CASCADE、而 note_question
            没有外键」——**两句都不对**，实测两个外键都在、也都没有级联。）
            所以子表必须由应用层**先删**：下面每一步都是为此存在的，别因为「反正有 CASCADE」
            把它们当成冗余删掉 —— 删掉就是 ForeignKeyViolation。

        ⚠️⚠️ **归属闸门放在这里**（2026-09-22 修的越权缺陷）：本函数是**物理删**，
        一旦执行**收不回来**，所以不能只靠「调用方已经把 id 解析成自己的了」这条口头约定
        （`_delete` / `_delete_many` / `_clear_questions` 三条路各有一份解析逻辑，
        哪天有人加第四条路、或者解析被改坏，爆炸半径就是「删掉别人的数据」）。
        这里落一道**结构性**的过滤：只留「题库属于当前用户」的 id。
        多出来的 id 静默丢弃（返回的计数就是真实删除数，调用方据此回报）。
        """
        ids = [int(i) for i in question_ids if i is not None]
        if not ids:
            return 0

        owned_rows = (
            await ctx.db.execute(
                select(QuestionMain.id)
                .join(QuestionBank, QuestionBank.id == QuestionMain.bank_id)
                .where(
                    QuestionMain.id.in_(ids),
                    QuestionBank.user_id == ctx.user_id,
                )
            )
        ).all()
        owned = {int(r[0]) for r in owned_rows}
        ids = [i for i in dict.fromkeys(ids) if i in owned]
        if not ids:
            return 0

        from app.models.note_question import NoteQuestion
        from app.models.question import (
            UserQuestionError,
            UserQuestionFavorite,
            UserQuestionMarked,
        )

        await ctx.db.execute(delete(QuestionSub).where(QuestionSub.main_id.in_(ids)))
        await ctx.db.execute(
            delete(NoteQuestion).where(NoteQuestion.question_id.in_(ids))
        )
        # ⚠️ 三类「个人题目标记」（错题本 / 收藏 / 斩题）必须**先于** `question_main` 删掉。
        #    2026-09-22 实测：`user_question_*.question_id → question_main` 的
        #    `delete_rule=NO ACTION`（**没有** ON DELETE CASCADE），漏了这一步就是
        #    `ForeignKeyViolationError: update or delete on table "question_main" violates
        #    foreign key constraint "user_question_favorite_question_id_fkey"` ——
        #    用户看到的是「工具执行异常：IntegrityError…」而题**删不掉**（实测原始响应见
        #    `tests/_evidence/p_group_flag_delete_before_fix_20260922.txt`）。
        #    这条路径以前走不到（没有任何工具能造出「已被标记的题」），本轮加了
        #    `question_flag_manage` 之后，「先收藏、再让助手删掉这道题」就是日常操作了。
        for _marked_model in (UserQuestionError, UserQuestionFavorite, UserQuestionMarked):
            await ctx.db.execute(
                delete(_marked_model).where(_marked_model.question_id.in_(ids))
            )
        await ctx.db.execute(delete(QuestionMain).where(QuestionMain.id.in_(ids)))
        await ctx.db.flush()
        return len(ids)

    async def _ordered_question_ids(self, ctx: ToolContext, bank_id: int) -> List[int]:
        """题库内题目的有序 ID 列表（与 list/detail 同一排序：sort_order, id）

        `question_index`（第 N 题）以它为准，保证「第 3 题」在各 action 间口径一致。
        """
        rows = (
            await ctx.db.execute(
                select(QuestionMain.id)
                .where(QuestionMain.bank_id == bank_id, QuestionMain.status == "0")
                .order_by(QuestionMain.sort_order, QuestionMain.id)
            )
        ).all()
        return [int(r[0]) for r in rows]

    async def _delete(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        question = await self._resolve_question(params, ctx)
        if isinstance(question, dict):
            return question

        bank_id = question.bank_id
        await self._purge_questions(ctx, [question.id])
        total = await qws.recalc_bank_total(ctx.db, bank_id)
        return ok(
            action="delete",
            questionId=question.id,
            bankTotal=total,
            message=f"已删除题目（ID={question.id}），题库现有 {total} 题",
        )

    async def _delete_many(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        """一次删除多道题（`question_ids` 和/或 `question_indexes`，需给出题库）

        覆盖「删掉第 1、3、5 题」「把这几道题都删了」这类请求 ——
        不必让模型一道道 delete（又慢又容易中途打转）。
        """
        bank = await self._resolve_bank(params, ctx)
        if isinstance(bank, dict):
            return bank
        if bank is None:
            return fail("未指定题库", "请提供 bank_name 或 bank_id")

        ids: List[int] = []
        for value in _as_list(params.get("question_ids")):
            try:
                ids.append(int(value))
            except (TypeError, ValueError):
                continue

        indexes: List[int] = []
        for value in _as_list(params.get("question_indexes")):
            try:
                indexes.append(int(value))
            except (TypeError, ValueError):
                continue

        if not ids and not indexes:
            return fail(
                "delete_many 需要 question_ids 或 question_indexes",
                "请给出要删除的题目 ID 列表（question_ids）或题号列表（question_indexes）",
            )

        out_of_range: List[int] = []
        if indexes:
            ordered = await self._ordered_question_ids(ctx, bank.id)
            out_of_range = [i for i in indexes if i < 1 or i > len(ordered)]
            ids.extend(ordered[i - 1] for i in indexes if 1 <= i <= len(ordered))

        if not ids:
            return fail(
                "没有可删除的题目（题号越界）",
                "请先用 action=list 确认该题库的题目数量与题号",
                outOfRange=out_of_range,
            )

        # 只删「属于这个题库」的题目：模型给错 id 时不会误删别的题库
        owned_rows = (
            await ctx.db.execute(
                select(QuestionMain.id).where(
                    QuestionMain.id.in_(ids), QuestionMain.bank_id == bank.id
                )
            )
        ).all()
        owned = {int(r[0]) for r in owned_rows}
        final_ids = [i for i in dict.fromkeys(ids) if i in owned]

        if not final_ids:
            return fail(
                "没有可删除的题目",
                "这些题目不属于该题库，请先用 action=list 确认",
                outOfRange=out_of_range,
            )

        removed = await self._purge_questions(ctx, final_ids)
        total = await qws.recalc_bank_total(ctx.db, bank.id)
        parts = [f"已删除 {removed} 道题", f"题库「{bank.bank_name}」现有 {total} 题"]
        if out_of_range:
            parts.append(f"题号越界已忽略：{out_of_range}")
        return ok(
            action="delete_many",
            bankId=bank.id,
            bankName=bank.bank_name,
            deleted=removed,
            bankTotal=total,
            outOfRange=out_of_range,
            message="；".join(parts),
        )

    async def _clear_questions(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        """清空某个题库的**全部题目**（题库本身保留）"""
        bank = await self._resolve_bank(params, ctx)
        if isinstance(bank, dict):
            return bank
        if bank is None:
            return fail("未指定题库", "请提供 bank_name 或 bank_id")

        ids = await self._ordered_question_ids(ctx, bank.id)
        # 清空时要连「已软删/非正常状态」的题目一起清掉，避免残留
        rows = (
            await ctx.db.execute(
                select(QuestionMain.id).where(QuestionMain.bank_id == bank.id)
            )
        ).all()
        ids = sorted({*ids, *(int(r[0]) for r in rows)})

        removed = await self._purge_questions(ctx, ids)
        total = await qws.recalc_bank_total(ctx.db, bank.id)
        return ok(
            action="clear_questions",
            bankId=bank.id,
            bankName=bank.bank_name,
            deleted=removed,
            bankTotal=total,
            message=f"已清空题库「{bank.bank_name}」的 {removed} 道题目，题库本身保留",
        )

    # ------------------------------------------------------------------
    # 定位辅助
    # ------------------------------------------------------------------

    async def _resolve_bank(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Optional[Any]:
        """按 bank_id / bank_name 定位题库（返回 None 或 fail 信封）"""
        bank_id = params.get("bank_id")
        bank_name = (params.get("bank_name") or "").strip()

        if bank_id is not None:
            bank = await ctx.db.get(QuestionBank, int(bank_id))
            # ⚠️「不存在」与「不是你的」必须回**同一句**（2026-09-22 补）：
            #    这里原先分成两句（`题库不存在：bank_id=X` / `只能操作自己的题库`），
            #    等于给攻击者一个「这个 id 存在」的探测预言机 —— 拿一串 id 试一遍就能
            #    数出别人有多少题库（下面 `_resolve_question` 与 `bank_manage._resolve_bank`
            #    上一轮已经统一成同口径，这条是同一个类里漏掉的第三处）。
            #    `int(... or 0)` 是防 `user_id` 为空的脏行被 `!=` 判成「不是你的」而误拒。
            if bank is None or int(bank.user_id or 0) != int(ctx.user_id):
                return fail(
                    f"题库不存在或不属于你：bank_id={bank_id}",
                    "请先用 bank_manage list 查询**你自己的**题库（只能操作自己的题库）",
                )
            return bank

        if bank_name:
            bank = await qws.find_bank_by_name(ctx.db, ctx.user_id, bank_name)
            if bank is None:
                return fail(
                    f"没有找到名为「{bank_name}」的题库",
                    "请先用 bank_manage list 查看你的题库名称；"
                    "如果题库还没建，请先用 bank_manage create 创建",
                )
            return bank

        return fail("需要 bank_id 或 bank_name", "请提供其中一个")

    async def _resolve_question(self, params: Dict[str, Any], ctx: ToolContext):
        """按 question_id 或 question_index 定位题目（返回 None / 模型 / fail 信封）

        ⚠️⚠️ **`question_id` 分支必须校验归属**（2026-09-22 修的越权缺陷）：
        这里原来是 `ctx.db.get(QuestionMain, int(question_id))` —— **没有任何 user 过滤**，
        而 `_detail` / `_update` / `_delete` 三条路**共用**这一个解析函数，于是
        「拿别人的 question_id 读题干 / 改答案 / 物理删掉」全都能成立。
        「按名字」那一路（`_resolve_bank` 的 name 分支）本来就有过滤，所以换个名字问
        会被拒 —— 这正是这个洞**没被按名字的用例发现**的原因。

        题目表没有 user_id（归属在题库上），所以走判断题 -> 题库 的归属。
        """
        question_id = params.get("question_id")
        if question_id is not None:
            question = await ctx.db.get(QuestionMain, int(question_id))
            # 「不存在」与「不是你的」**刻意回同一句**：分开说等于给攻击者一个
            # 「这个 id 存在」的探测预言机（与 knowledge_search 那边的口径一致）。
            if question is not None:
                owner = await ctx.db.scalar(
                    select(QuestionBank.user_id).where(
                        QuestionBank.id == question.bank_id
                    )
                )
                if owner is None or int(owner) != int(ctx.user_id):
                    question = None
            if question is None:
                return fail(
                    f"题目不存在或不属于你：question_id={question_id}",
                    "请先用 action=list 确认题目 ID（只能操作**自己题库里**的题目；"
                    "如果只知道题号，请改用 question_index + bank_id/bank_name）",
                )
            return question

        question_index = params.get("question_index")
        if question_index is not None:
            bank = await self._resolve_bank(params, ctx)
            if isinstance(bank, dict):
                return bank
            if bank is None:
                return fail(
                    "用 question_index 定位题目时必须同时给出题库",
                    "请提供 bank_id 或 bank_name",
                )
            offset = max(int(question_index) - 1, 0)  # 序号从 1 开始
            result = await ctx.db.execute(
                select(QuestionMain)
                .where(QuestionMain.bank_id == bank.id, QuestionMain.status == "0")
                .order_by(QuestionMain.sort_order, QuestionMain.id)
                .offset(offset)
                .limit(1)
            )
            question = result.scalars().first()
            if question is None:
                return fail(
                    f"题库「{bank.bank_name}」里没有第 {question_index} 题",
                    "请先 list 查看该题库的题目数量",
                )
            return question

        return fail("需要 question_id 或 question_index", "请提供其中一个")

    async def _load_subs(self, ctx: ToolContext, main_id: int) -> List[Any]:
        """读取某道主题的全部子题（按 sort_order 排序）"""
        from app.models.question import QuestionSub

        result = await ctx.db.execute(
            select(QuestionSub)
            .where(QuestionSub.main_id == main_id)
            .order_by(QuestionSub.sort_order, QuestionSub.id)
        )
        return list(result.scalars().all())

    async def _next_sort_order(self, ctx: ToolContext, bank_id: int) -> int:
        current = await ctx.db.scalar(
            select(func.max(QuestionMain.sort_order)).where(QuestionMain.bank_id == bank_id)
        )
        return int(current or 0) + 1

    @staticmethod
    def _question_type(source: Dict[str, Any]) -> int:
        value = source.get("question_type")
        if value is None:
            value = source.get("questionType")
        try:
            return int(value or 1)
        except (TypeError, ValueError):
            return 1


def _dumps(value: Any) -> str:
    import json

    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        return str(value)


__all__ = ["QuestionManageTool", "MAX_BATCH_SIZE"]
