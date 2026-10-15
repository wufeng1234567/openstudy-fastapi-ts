"""
`question_flag_manage` —— 三类「个人题目标记」（错题本 / 收藏 / 斩题）合成**一个**工具

为什么是「一个工具 + `flag_type`」而不是三个工具（2026-09-22 改）
----------------------------------------------------------------
第一版把三张表做成三个工具（`error_book_manage` / `favorite_manage` / `marked_manage`），
理由是「工具名本身就是最不容易错的那层区分」。**那个理由不足以抵消它的代价**：

· `registry.describe()` 会把每个工具的 `description` 整段注入系统提示词的 `{{TOOLS}}`，
  三份「同一形状、只有表名不同」的描述占了三段 prompt，而这轮工具总数从 5 涨到 12；
· 项目既有约定写在 `tools/bank_manage.py` 的模块 docstring 里：「同一域的
  list/detail/create/update/delete **收进一个工具、用 `action` 区分**」，
  理由是**工具清单越长，模型选错的概率越高**（尤其形近动作）；
· 三类记录在领域层本来就共用一份实现（`question_record_service`），
  拆三个工具是唯一一处「同一份域逻辑被三份 schema 描述包了三遍」。

代价（说清楚，别以为是白拿的）
------------------------------
合并后 `flag_type` 选错**不会报错**，只会写进另一张表 —— 这是第一版想避开的
「静默写错表」。对它做了两处封堵，改这个工具时别把这两处删掉：

1. **`flag_type` 是必填项**（`required`），不给默认值 —— 模型必须显式表态，
   漏了会拿到一句带 hint 的 `fail()`，而不是「悄悄按 error 处理」；
2. **每个动作的结果与确认卡片都回 `flagType` + `flagTypeText`（「错题本 / 收藏 / 斩题」）**
   —— 选错了用户当轮就能看见，不必等下次打开页面发现数据跑错地方。

`master` 只对错题本有意义
------------------------
`_ACTIONS_BY_TYPE` 是每个 `flag_type` 各自支持的 action：`favorite` / `marked`
没有 `master`，传了会拿到「收藏不支持 master」+ 可选值清单（而不是静默当 `remove`）。
`master`（标记已掌握）**不是删除**：记录留着（`status=0`），再答错时
`POST /questionPractice/report` 会把它重新激活。把它当破坏性动作会让用户每标一次
都要确认，纯属噪声。`remove` 才是真删（与前端「取消收藏 / 取消斩题 / 删除错题」一致，
物理 delete）。

⚠️ **结果字段按 `flag_type` 分别命名，不是统一成一个 `recordId`**
---------------------------------------------------------------
`list` 的数组键与 id 键沿用三张表各自的名字（`errors`/`errorId`、
`favorites`/`favoriteId`、`markedQuestions`/`markedId`），因为前端
`components/AgentToolDetail/index.vue` 的 `FIELD_LABELS` 与既有列表页都按这套键做中文标签
（三个键各写一份标签，比新造 `recordId` 再多一层「这是哪张表的 id」的解读更省事）。
**但入参统一成 `record_id`**：参数是给模型看的、结果是给用户看的，两者不必同形；
入参一个名字，模型就不会出现「flag_type=marked 却传了 error_id」这种错配。

⚠️ 每一处「按 id 定位」都在服务层带 `user_id`
-------------------------------------------
`record_id` 落到的是三张表的**全局自增主键**：只按 id 取，任何登录用户拿别人的 id
就能读、能删别人的记录（本轮 API 侧正在修同一类越权）。所以全部走
`question_record_service.get_record(db, user_id, kind, id)` —— `user_id` 写在 SQL 的
WHERE 里，**不在调用方**（调用方漏一次就是越权）。`add` 也不含糊：题目 id 同样全局自增，
所以先过 `resolve_visible_question()`（必须在用户可见的题库里），否则就是
「借自己的账号读别人的题」。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.services import question_record_service as qrs
from app.services.ai.agent.base import (
    OP_DELETE_RECORD,
    OP_INSERT_RECORD,
    OP_RESTORE_FIELDS,
    REASON_MISSING_TARGET_ID,
    UNDO_BEFORE_KEY,
    AgentTool,
    ToolContext,
    fail,
    ok,
)

#: 列表分页（与 `question_manage._list` 同口径）
from app.services.question_record_service import DEFAULT_LIMIT, MAX_LIMIT

#: 确认卡片 / 回执里的题干最多显示多少字
_PREVIEW_CHARS = 80

#: `flag_type` 取值 → 给用户看的中文名（回执与确认卡片直接用）
_FLAG_TYPE_TEXT: Dict[str, str] = {
    qrs.KIND_ERROR: "错题本",
    qrs.KIND_FAVORITE: "收藏",
    qrs.KIND_MARKED: "斩题",
}

#: 每个 `flag_type` 各自支持的 action（`master` 只对错题本有意义）
_ACTIONS_BY_TYPE: Dict[str, List[str]] = {
    qrs.KIND_ERROR: ["list", "add", "master", "remove"],
    qrs.KIND_FAVORITE: ["list", "add", "remove"],
    qrs.KIND_MARKED: ["list", "add", "remove"],
}

#: `flag_type` → 结果里的 id 键 / 数组键（沿用三张表各自的名字，前端已有中文标签）
_ID_KEY: Dict[str, str] = {
    qrs.KIND_ERROR: "errorId",
    qrs.KIND_FAVORITE: "favoriteId",
    qrs.KIND_MARKED: "markedId",
}
_ITEMS_KEY: Dict[str, str] = {
    qrs.KIND_ERROR: "errors",
    qrs.KIND_FAVORITE: "favorites",
    qrs.KIND_MARKED: "markedQuestions",
}


#: 回退时要**写回**的字段（`add` 命中已有行 / `master` 的逆操作）
#:
#: ⚠️ 只列「这次操作真的会动」的列 —— 不是整行。列多了会把无关字段也写回去
#: （比如把 `review_count` 倒退回旧值，而那是用户练习时该涨的数字）。
_MARK_RESTORE_FIELDS: Dict[str, tuple] = {
    qrs.KIND_ERROR: ("error_count", "last_error_time", "status", "is_mastered", "notes", "tags"),
    qrs.KIND_FAVORITE: ("favorite_status", "notes", "tags"),
    qrs.KIND_MARKED: (
        "marked_status",
        "marked_type",
        "is_mastered",
        "bank_id",
        "notes",
        "tags",
    ),
}

#: 回退时要**插回**的字段（`remove` 是物理删，逆操作只能重新插入一行）
#:
#: ⚠️ 主键不回填（`rollback_service._Target._PROTECTED` 里挡着）：让库重新分配一个 id。
#:    硬把旧主键插回去要跟序列玩「谁大谁小」，收益只是「id 长得跟原来一样」，
#:    不值得 —— 记录本身（题目、次数、备注）才是用户关心的。
_MARK_INSERT_FIELDS: Dict[str, tuple] = {
    qrs.KIND_ERROR: (
        "question_id",
        "bank_id",
        "error_count",
        "error_time",
        "last_error_time",
        "status",
        "is_mastered",
        "notes",
        "tags",
    ),
    qrs.KIND_FAVORITE: (
        "question_id",
        "bank_id",
        "favorite_status",
        "error_times",
        "correct_times",
        "review_count",
        "is_starred",
        "notes",
        "tags",
    ),
    qrs.KIND_MARKED: (
        "question_id",
        "bank_id",
        "marked_status",
        "marked_type",
        "is_mastered",
        "difficulty_level",
        "error_times_before_mark",
        "correct_times_before_mark",
        "review_count",
        "notes",
        "tags",
    ),
}


#: `master`（标记已掌握）的逆操作要写回的列：`mark_mastered` 只动这两个
#: （`is_mastered=1, status=0`，见 `question_record_service.mark_mastered`）
_MASTER_UNDO_FIELDS = ("is_mastered", "status")


def _snapshot(record: Any, fields: tuple) -> Dict[str, Any]:
    """抓一条记录的「改前值」快照（普通 Python 值，不是 ORM 引用）"""
    return {name: getattr(record, name, None) for name in fields}


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _norm_tags(value: Any) -> Optional[str]:
    """`tags` 统一成 `user_question_*.tags`（varchar）里的逗号串

    模型的入参形态不定（数组 / 逗号串 / 单个词），这里收一处 —— 与
    `note_write_service.normalize_tags` 的取向一致，但落库格式不同（那边是 JSON）。
    """
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text.replace("，", ",") if text else None
    if isinstance(value, (list, tuple, set)):
        items = [str(v).strip() for v in value if str(v).strip()]
        return ",".join(items) if items else None
    return str(value)


class QuestionFlagManageTool(AgentTool):
    name = "question_flag_manage"
    #: ⚠️ 描述与参数说明一律英文 —— 它们会同时进两处「提示词注入」通道：
    #:   ① `registry.describe()` → 系统提示词的 `{{TOOLS}}` 占位
    #:   ② `registry.definitions()` → Function Calling 的 `tools` 参数
    description = (
        "Manage the user's personal marks on individual questions. Choose `flag_type` "
        "FIRST — it selects which list you work with:\n"
        "  error = WRONG-QUESTION BOOK (错题本); auto-filled when the user answers wrong.\n"
        "  favorite = questions BOOKMARKED for later.\n"
        "  marked = questions flagged as KEY TARGETS to conquer (斩题).\n"
        "action values: "
        "list=list records of that flag_type (optional `keyword` on question text, optional "
        "`bank_id`, paged via `limit`/`offset`; reply carries `total`), "
        "add=put a question into that list by `question_id` (optional `notes`/`tags`; for "
        "flag_type=marked also optional `marked_type`; adding an existing question "
        "reactivates the record instead of duplicating), "
        "master=ONLY for flag_type=error: mark a wrong question MASTERED by `record_id` "
        "(leaves the list but NOT deleted — answering wrong again brings it back), "
        "remove=delete the record permanently by `record_id`. "
        "For aggregate numbers (how many wrong, mastery rate, by difficulty) use "
        "`learning_stats` action=error_analysis instead. Every id is checked against the "
        "current user."
    )
    #: 界面专用（只给前端看；不进 definitions() / describe()）
    label = "题目标记"
    description_zh = (
        "管理单道题上的个人标记（先定 flag_type：error=错题本、favorite=收藏、marked=标记）："
        "list=列出、add=加入、master=标记为已掌握、remove=移出。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Operation to perform",
                "enum": ["list", "add", "master", "remove"],
            },
            "flag_type": {
                "type": "string",
                "description": (
                    "Which list to work with — decide this BEFORE the action: "
                    "error=the wrong-question book, favorite=bookmarked questions, "
                    "marked=questions flagged as key targets. It is required, and picking "
                    "the wrong one writes to a different list."
                ),
                "enum": list(_FLAG_TYPE_TEXT),
            },
            "record_id": {
                "type": "integer",
                "description": (
                    "The record to act on (used by master/remove). Take it from action=list: "
                    "it is the `errorId` when flag_type=error, `favoriteId` when "
                    "flag_type=favorite, `markedId` when flag_type=marked."
                ),
            },
            "question_id": {
                "type": "integer",
                "description": (
                    "Only for add: the question to add. Find it with `question_manage` "
                    "search/list."
                ),
            },
            "bank_id": {
                "type": "integer",
                "description": (
                    "Only for list: restrict to one question bank. Get the ID from "
                    "`bank_manage` list. Omit to look at every bank."
                ),
            },
            "keyword": {
                "type": "string",
                "description": (
                    "Only for list: fuzzy match inside the QUESTION TEXT. Use the words the "
                    "user mentioned, e.g. '二次函数'."
                ),
            },
            "limit": {
                "type": "integer",
                "description": f"Max items per page (default {DEFAULT_LIMIT}, max {MAX_LIMIT}).",
            },
            "offset": {
                "type": "integer",
                "description": (
                    "0-based offset for list (default 0). The reply includes `total` and "
                    "`hasMore`, so you can tell the user how many there are in total."
                ),
            },
            "notes": {
                "type": "string",
                "description": "Optional free-text note (used by add).",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional tags, e.g. [\"Math\", \"Review\"] (used by add).",
            },
            "marked_type": {
                "type": "integer",
                "description": (
                    "Only for flag_type=marked with add: why it is marked - "
                    "1=wrong question 2=hard 3=key point 4=easy to slip 5=technique "
                    "(default 1)."
                ),
                "enum": sorted(qrs.MARKED_TYPE_TEXT),
            },
        },
        # ⚠️ `flag_type` 必填：不给默认值，否则「模型漏传」会静默写成错题本
        "required": ["action", "flag_type"],
    }
    write_operation = True

    #: 会写库的动作 —— ⚠️ `GET /ai/agent/tools` 的 write 清单是**逐个 action 枚举**探测的
    #: （`ai.py:_agent_tools_payload` 只传 `{"action": a}`，不带 flag_type），
    #: 所以这里按 action 判定，不做 flag_type 分支，否则 `master` 会从清单里消失。
    _WRITE_ACTIONS = {"add", "master", "remove"}

    #: 破坏性动作：只有 `remove` 是真删（`master` 保留记录 —— 见模块 docstring）
    _DESTRUCTIVE_ACTIONS = {"remove"}

    def needs_confirmation(self, params: Dict[str, Any]) -> bool:
        return str(params.get("action") or "") in self._WRITE_ACTIONS

    def is_destructive(self, params: Dict[str, Any]) -> bool:
        return str(params.get("action") or "") in self._DESTRUCTIVE_ACTIONS

    def undo_plan(self, params: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any] | None:
        """声明「这一笔标记操作用什么撤」（契约见 `base.AgentTool.undo_plan`）

        三类记录形状一样但逆操作分三种（都在这个工具里，`flag_type` 决定表名）：

          · `add` 且是**新造**的一行（回执 `created=True`）→ 物理删掉它（`delete_record`）
          · `add` 命中**已有**行（upsert：错题 `error_count += 1`、状态位复苏）→
            把改前值写回（`restore_fields`，旧值走 `UNDO_BEFORE_KEY`，见 `_add`）
          · `remove`（**物理删**）→ 按改前值**重新插一行**（`insert_record`）。
            ⚠️ 主键不回填，新行会拿到新的 `errorId/favoriteId/markedId`
            —— 记录本身（题目、次数、备注）回来了，这才是用户要的。
          · `master` → 把 `is_mastered` / `status` 写回旧值
        """
        kind, err = self._flag_type(params)
        if err or kind is None:
            return None
        action = str(params.get("action") or "")
        table = qrs.KINDS[kind].model.__tablename__
        # `add` 的 id 键按 flag_type 各自命名（`errorId`/`favoriteId`/`markedId`），
        # `remove`/`master` 用统一的 `recordId`（见模块 docstring）
        rid = _to_int(result.get(_ID_KEY[kind])) if action == "add" else _to_int(
            result.get("recordId")
        )
        if rid is None:
            return {"undoable": False, "reason": REASON_MISSING_TARGET_ID}
        if action == "add":
            return {
                "op": OP_DELETE_RECORD if result.get("created") else OP_RESTORE_FIELDS,
                "targetTable": table,
                "targetIds": [rid],
                "undoable": True,
            }
        if action == "remove":
            return {
                "op": OP_INSERT_RECORD,
                "targetTable": table,
                "targetIds": [rid],
                "undoable": True,
            }
        if action == "master":
            return {
                "op": OP_RESTORE_FIELDS,
                "targetTable": table,
                "targetIds": [rid],
                "undoable": True,
            }
        return None

    # ------------------------------------------------------------------ 参数归一

    @staticmethod
    def _flag_type(params: Dict[str, Any]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """归一 `flag_type`；不合法时返回 `(None, fail 信封)`"""
        raw = str(params.get("flag_type") or "").strip().lower()
        if raw not in _FLAG_TYPE_TEXT:
            given = params.get("flag_type")
            return None, fail(
                f"未知的标记类型：{given if given not in (None, '') else '（没有传 flag_type）'}",
                "flag_type 只能是 "
                + " / ".join(f"{k}={v}" for k, v in _FLAG_TYPE_TEXT.items())
                + "（错题本用 error，题目收藏用 favorite，斩题用 marked）",
            )
        return raw, None

    # ------------------------------------------------------------------ 预览

    async def preview(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        """确认卡片上给出**反查出来的真实内容**，不是模型传进来的字符串

        · `remove` / `master`：按 `record_id` **只读反查**（带 user_id）出记录 +
          它对应的题干与题库名，卡片才说得清「动的是哪道题、动的是哪个列表」
        · `add`：反查题目与所属题库（题目 id 同样不可信）

        卡片一律带 `flagType` / `flagTypeText` —— 这是 `flag_type` 选错时唯一的
        当轮可见信号（见模块 docstring）。

        失败**不允许**抛出 —— 循环层会兜住，但别依赖它。
        """
        kind, err = self._flag_type(params)
        if err:
            return {}
        action = str(params.get("action") or "")
        try:
            if action in ("remove", "master"):
                return await self._preview_record(params, ctx, kind)
            if action == "add":
                return await self._preview_question(params, ctx, kind)
        except Exception:  # noqa: BLE001 - 预览失败不影响主流程
            return {}
        return {}

    @staticmethod
    def _type_fields(kind: str) -> Dict[str, Any]:
        return {"flagType": kind, "flagTypeText": _FLAG_TYPE_TEXT[kind]}

    async def _preview_record(
        self, params: Dict[str, Any], ctx: ToolContext, kind: str
    ) -> Dict[str, Any]:
        rid = _to_int(params.get("record_id"))
        if rid is None:
            return {}
        # 只读反查（get_record 的 WHERE 里带 user_id）
        record = await qrs.get_record(ctx.db, ctx.user_id, kind, rid)
        label = _FLAG_TYPE_TEXT[kind]
        if record is None:
            # 查不到就**明说**，绝不回显模型给的 id 当成「找到了」
            return {
                **self._type_fields(kind),
                "recordId": rid,
                "preview": f"（没有找到属于你的{label}记录：record_id={rid}）",
            }
        brief = await qrs.brief_of(ctx.db, ctx.user_id, kind, record)
        return {
            **self._type_fields(kind),
            "recordId": brief.get(_ID_KEY[kind]),
            "preview": brief.get("preview") or "（这道题的题干是空的）",
            "bankName": brief.get("bankName"),
            "questionId": brief.get("questionId"),
        }

    async def _preview_question(
        self, params: Dict[str, Any], ctx: ToolContext, kind: str
    ) -> Dict[str, Any]:
        question, bank, err = await qrs.resolve_visible_question(
            ctx.db, ctx.user_id, params.get("question_id")
        )
        if err or question is None or bank is None:
            return {
                **self._type_fields(kind),
                "preview": f"（{err or '没有找到这道题'}）",
            }
        text = question.question_text or ""
        return {
            **self._type_fields(kind),
            "preview": text[:_PREVIEW_CHARS] + ("…" if len(text) > _PREVIEW_CHARS else ""),
            "bankName": bank.bank_name,
            "questionId": question.id,
        }

    # ------------------------------------------------------------------ 执行

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        kind, err = self._flag_type(params)
        if err:
            return err

        action = str(params.get("action") or "")
        allowed = _ACTIONS_BY_TYPE[kind]
        if action not in allowed:
            label = _FLAG_TYPE_TEXT[kind]
            hint = f"flag_type={kind} 时 action 只能是 {' / '.join(allowed)}"
            if action == "master":
                hint = "master（标记已掌握）只对错题本有意义；" + hint
            return fail(f"{label}不支持「{action}」操作", hint)

        handler = {
            "list": self._list,
            "add": self._add,
            "master": self._master,
            "remove": self._remove,
        }[action]
        return await handler(params, ctx, kind)

    async def _list(
        self, params: Dict[str, Any], ctx: ToolContext, kind: str
    ) -> Dict[str, Any]:
        limit = _to_int(params.get("limit")) or DEFAULT_LIMIT
        limit = max(1, min(MAX_LIMIT, limit))
        offset = max(_to_int(params.get("offset")) or 0, 0)
        bank_id = _to_int(params.get("bank_id"))
        keyword = (params.get("keyword") or "").strip() or None

        rows, total = await qrs.list_records(
            ctx.db,
            ctx.user_id,
            kind,
            bank_id=bank_id,
            keyword=keyword,
            limit=limit,
            offset=offset,
        )
        items = [
            await qrs.brief_of(ctx.db, ctx.user_id, kind, record, question, bank_name)
            for record, question, bank_name in rows
        ]

        label = _FLAG_TYPE_TEXT[kind]
        if total == 0:
            where = "该题库里没有" if bank_id else "一共 0 条"
            message = (
                f"没有找到{'包含该关键词的' if keyword else ''}{label}记录"
                f"（{where}），请如实告知。"
            )
        else:
            message = f"共 {total} 条{label}记录"
            if bank_id:
                message += "（已按题库筛选）"
            if keyword:
                message += f"（关键词「{keyword}」）"
            message += f"，本次返回 {len(items)} 条"
        return ok(
            **{
                **self._type_fields(kind),
                "action": "list",
                "offset": offset,
                "count": len(items),
                "total": total,
                "hasMore": offset + len(items) < total,
                _ITEMS_KEY[kind]: items,
                "message": message,
            }
        )

    async def _add(
        self, params: Dict[str, Any], ctx: ToolContext, kind: str
    ) -> Dict[str, Any]:
        label = _FLAG_TYPE_TEXT[kind]
        question_id = params.get("question_id")
        if question_id is None:
            return fail(
                f"把题目加入{label}需要 question_id",
                "请先用 question_manage 的 search/list 找到这道题的 questionId",
            )

        question, bank, err = await qrs.resolve_visible_question(
            ctx.db, ctx.user_id, question_id
        )
        if err or question is None or bank is None:
            return fail(
                err or "题目不存在",
                "请先用 question_manage 确认这道题的 questionId（只能操作你能看到的题库里的题）",
            )

        marked_type = None
        if kind == qrs.KIND_MARKED and params.get("marked_type") is not None:
            marked_type = _to_int(params.get("marked_type"))
            if marked_type not in qrs.MARKED_TYPE_TEXT:
                return fail(
                    f"未知的斩题类型：{params.get('marked_type')}",
                    "marked_type 只能是 "
                    + " / ".join(f"{k}={v}" for k, v in qrs.MARKED_TYPE_TEXT.items()),
                )

        # ⚠️ 回退需要「改前值」：`add` 是 upsert —— 命中已有行时会**累加**（错题
        #    `error_count += 1`、状态位置 1），调用返回后旧值就没了。所以先读一次。
        #    谓词与 `add_record` 内部那份**同一个函数**（`get_record_by_question`），不会漂。
        existing = await qrs.get_record_by_question(ctx.db, ctx.user_id, kind, question.id)
        before = _snapshot(existing, _MARK_RESTORE_FIELDS[kind]) if existing is not None else None

        record, created = await qrs.add_record(
            ctx.db,
            ctx.user_id,
            kind,
            question,
            bank.id,
            notes=params.get("notes"),
            tags=_norm_tags(params.get("tags")),
            marked_type=marked_type,
        )
        text = (question.question_text or "")[:_PREVIEW_CHARS]

        if kind == qrs.KIND_ERROR:
            message = (
                f"已把「{text}」加入错题本（第 1 次记录）"
                if created
                else f"「{text}」已在错题本里，错误次数 +1（现 {record.error_count} 次）"
            )
        elif kind == qrs.KIND_FAVORITE:
            message = (
                f"已收藏题目「{text}」" if created else f"「{text}」本来就在收藏里，已恢复"
            )
        else:
            type_text = qrs.MARKED_TYPE_TEXT.get(record.marked_type, "未知")
            message = (
                f"已把「{text}」加入斩题（类型：{type_text}）"
                if created
                else f"「{text}」本来就在斩题里，已恢复为「{type_text}」"
            )

        payload: Dict[str, Any] = {
            **self._type_fields(kind),
            "action": "add",
            "created": created,
            # ⚠️ 取的是**列属性名**（`error_id`），不是对外字段名（`errorId`）
            _ID_KEY[kind]: getattr(record, qrs.KINDS[kind].id_column.key),
            "questionId": question.id,
            "bankId": bank.id,
            "bankName": bank.bank_name,
            "questionText": text,
            "message": message,
        }
        if before is not None:
            # 命中已有行 → 回退要把这些列写回旧值；走信封的私有键（不进回执/不进模型）
            payload[UNDO_BEFORE_KEY] = before
        return ok(**payload)

    async def _remove(
        self, params: Dict[str, Any], ctx: ToolContext, kind: str
    ) -> Dict[str, Any]:
        label = _FLAG_TYPE_TEXT[kind]
        rid = _to_int(params.get("record_id"))
        if rid is None:
            return fail(
                f"删除{label}记录需要 record_id",
                f"请先用 action=list（flag_type={kind}）找到要删除的那条记录的 "
                f"{_ID_KEY[kind]}，把它传给 record_id",
            )

        # ⚠️ user_id 在 SQL 里（本轮重点验收项）：只按 id 取 = 能删别人的记录
        record = await qrs.get_record(ctx.db, ctx.user_id, kind, rid)
        if record is None:
            return fail(
                f"没有找到属于你的{label}记录：record_id={rid}",
                f"请先用 action=list（flag_type={kind}）确认 {_ID_KEY[kind]}"
                "（别人的记录在这里一律查不到）",
            )

        brief = await qrs.brief_of(ctx.db, ctx.user_id, kind, record)
        # ⚠️ `remove` 是**物理删**（见模块 docstring），逆操作只能「按改前值重新插一行」，
        #    所以必须在删之前把要插回的那些列抓下来
        before = _snapshot(record, _MARK_INSERT_FIELDS[kind])
        removed = await qrs.remove_record(ctx.db, ctx.user_id, kind, record)
        if not removed:
            return fail(
                f"删除失败：record_id={rid}",
                "这条记录可能刚被别处删掉了，请重新 list 确认",
            )
        text = brief.get("preview") or f"题目 {brief.get('questionId')}"
        verb = {
            qrs.KIND_FAVORITE: "已取消收藏",
            qrs.KIND_MARKED: "已取消斩题",
            qrs.KIND_ERROR: "已从错题本删除",
        }[kind]
        return ok(
            **{
                **self._type_fields(kind),
                "action": "remove",
                "deleted": 1,
                "recordId": rid,
                "questionId": brief.get("questionId"),
                "message": f"{verb}：{text}",
                UNDO_BEFORE_KEY: before,
            }
        )

    async def _master(
        self, params: Dict[str, Any], ctx: ToolContext, kind: str
    ) -> Dict[str, Any]:
        label = _FLAG_TYPE_TEXT[kind]
        rid = _to_int(params.get("record_id"))
        if rid is None:
            return fail(
                "标记已掌握需要 record_id",
                f"请先用 action=list（flag_type={kind}）找到那道题的 {_ID_KEY[kind]}",
            )
        record = await qrs.get_record(ctx.db, ctx.user_id, kind, rid)
        if record is None:
            return fail(
                f"没有找到属于你的{label}记录：record_id={rid}",
                f"请先用 action=list（flag_type={kind}）确认 {_ID_KEY[kind]}",
            )
        brief = await qrs.brief_of(ctx.db, ctx.user_id, kind, record)
        # 改前值（回退要把这两个状态位写回去；见 `_MARK_RESTORE_FIELDS[error]`）
        before = _snapshot(record, _MASTER_UNDO_FIELDS)
        if int(record.is_mastered or 0) == 1:
            return ok(
                **{
                    **self._type_fields(kind),
                    "action": "master",
                    "recordId": rid,
                    "isMastered": 1,
                    UNDO_BEFORE_KEY: before,
                    "message": f"这道题已经是「已掌握」了：{brief.get('preview')}",
                }
            )
        await qrs.mark_mastered(ctx.db, ctx.user_id, record)
        return ok(
            **{
                **self._type_fields(kind),
                "action": "master",
                "recordId": rid,
                "isMastered": 1,
                UNDO_BEFORE_KEY: before,
                "message": (
                    f"已把「{brief.get('preview')}」标记为「已掌握」"
                    "（记录保留；以后再做错会自动回到错题本）"
                ),
            }
        )


__all__ = ["QuestionFlagManageTool"]
