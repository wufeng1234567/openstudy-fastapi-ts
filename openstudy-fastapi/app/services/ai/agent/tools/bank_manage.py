"""
`bank_manage` —— 题库管理工具（Agent 自封装）

对齐 springboot3 的 `BankManageTool`：把 list / detail / create / update / delete /
delete_by_name 收进**一个**工具，用 `action` 区分。

为什么合并成一个而不是六个工具：
- 工具清单越长，模型选错的概率越高（尤其「删除」和「按名删除」很像）；
- 描述里写清 action 的语义，模型一次就能选对；
- 参数 schema 里的 `action` 枚举天然就是「能给模型看的文档」。
"""

from __future__ import annotations

from typing import Any, Dict, List

from loguru import logger
from sqlalchemy import select

from app.models.question import QuestionBank
from app.services import question_write_service as qws
from app.services.ai.agent.base import (
    OP_RESTORE_TREE,
    REASON_MISSING_SOFT_DELETE,
    UNDO_BEFORE_KEY,
    AgentTool,
    ToolContext,
    as_list as _as_list,
    fail,
    ok,
)

#: 需要用户确认的动作（破坏性 / 会写数据）
_WRITE_ACTIONS = {"create", "update", "delete", "delete_by_name", "delete_many"}

#: 确认卡片里的样例列表最多给几条（与 `note_manage._PREVIEW_SAMPLE` 同口径）
_PREVIEW_SAMPLE = 5


class BankManageTool(AgentTool):
    name = "bank_manage"
    #: ⚠️ 描述与参数说明一律英文 —— 它们会同时进两处「提示词注入」通道：
    #:   ① `registry.describe()` → 系统提示词的 `{{TOOLS}}` 占位
    #:   ② `registry.definitions()` → Function Calling 的 `tools` 参数
    #: 系统提示词是全英文的，这里混中文会让模型面对两套语言约定。
    description = (
        "Manage question banks. Use for creating, reading, updating and deleting banks. "
        "action values: list=list my banks (optional fuzzy `bank_name` keyword, optional "
        "`subject` filter), detail=show one bank's details, create=create a bank, "
        "update=update bank fields, delete=delete by `bank_id`, "
        "delete_by_name=delete by exact bank name, "
        "delete_many=delete SEVERAL banks at once (pass `bank_ids` and/or exact `bank_names` lists). "
        "NOTE: to work with the QUESTIONS inside a bank, use `question_manage` instead."
    )
    #: 界面专用（只给前端看；不进 definitions() / describe()）
    label = "题库管理"
    description_zh = (
        "题库的增删改查：list=列我的题库（可按名称模糊找、按科目筛）、"
        "detail=看某个库的详情、create=建库、update=改库、delete=按 id 删库、"
        "delete_by_name=按库名删库、delete_many=一次删多个。"
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
                    "create",
                    "update",
                    "delete",
                    "delete_by_name",
                    "delete_many",
                ],
            },
            "bank_id": {
                "type": "integer",
                "description": "Bank ID (used by detail/update/delete)",
            },
            "bank_name": {
                "type": "string",
                "description": (
                    "Bank name. Used as the fuzzy keyword for list; required for "
                    "create and delete_by_name."
                ),
            },
            "bank_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Bank IDs to delete in bulk (used by delete_many).",
            },
            "bank_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Exact bank names to delete in bulk (used by delete_many). "
                    "`bank_ids` is preferred when known."
                ),
            },
            "subject": {
                "type": "string",
                "description": "Subject, e.g. Java / Python / Math",
            },
            "limit": {
                "type": "integer",
                "description": "Max number of banks returned by list (default 20)",
            },
            "offset": {
                "type": "integer",
                "description": (
                    "0-based offset for list (default 0). Use with `limit` when a user has "
                    "more banks than one page shows; the reply includes `total` and `hasMore`."
                ),
            },
            "description": {
                "type": "string",
                "description": "Bank description (optional; auto-generated when omitted)",
            },
            "is_public": {
                "type": "integer",
                "description": "0=public (default), 1=private",
            },
        },
        "required": ["action"],
    }
    write_operation = True

    #: 删除类动作：即使 autoConfirm 开着也必须二次确认
    _DESTRUCTIVE_ACTIONS = {"delete", "delete_by_name", "delete_many"}

    def needs_confirmation(self, params: Dict[str, Any]) -> bool:
        return str(params.get("action") or "") in _WRITE_ACTIONS

    def is_destructive(self, params: Dict[str, Any]) -> bool:
        return str(params.get("action") or "") in self._DESTRUCTIVE_ACTIONS

    def confirm_policy(self, params: Dict[str, Any]) -> bool:
        """`create` 一次只建一个题库（规模固定），不额外强制确认"""
        return False

    async def preview(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        """确认卡片上给「会动到什么」，而不是光秃秃一个 id / 一句 action

        · `delete` / `update`：按 `bank_id` 反查题库名（原行为，不动）
        · `delete_by_name`：按名字**只读反查** —— 卡片必须说清「删的是哪个库」，
          名字对不上就明说没找到，**绝不回显模型传进来的字符串**
        · `delete_many`：`count` + `sample`（题库名），照 `note_manage._preview_delete` 的样板
        · `create`：`bankName` / `subject`（建之前先让用户确认建的是什么）

        ⚠️ 为什么 `delete_by_name` 不能回显参数里的名字：名字是**模型给的**，可能是简称/错字。
        回显的话卡片会显示一个库里并不存在的名字 —— 用户确认的是 A、实际删的是 B 或什么都没删。
        失败**不允许**抛出（循环层会兜住，但别依赖它）。
        """
        action = str(params.get("action") or "")
        try:
            if action == "create":
                return self._preview_create(params)
            if action == "delete_by_name":
                return await self._preview_delete_by_name(params, ctx)
            if action == "delete_many":
                return await self._preview_delete_many(params, ctx)
        except Exception:  # noqa: BLE001 - 预览失败不能影响主流程
            return {}

        bank_id = params.get("bank_id")
        if bank_id is None:
            return {}
        try:
            bank = await ctx.db.get(QuestionBank, int(bank_id))
        except Exception:  # noqa: BLE001 - 预览失败不能影响主流程
            return {}
        # ⚠️ 归属校验（2026-09-22 修的越权缺陷）：只读反查**同样**是信息出口 ——
        #    不挡的话，确认卡片会把**别人的**题库名 / 科目 / 题数打在用户脸上。
        #    查不到或不是自己的都回空 dict（卡片信息少一点，绝不泄漏、也不抛）。
        if bank is None or int(bank.user_id or 0) != int(ctx.user_id):
            return {}
        return {
            "bankName": bank.bank_name,
            "subject": bank.subject,
            "totalQuestions": bank.total_questions or 0,
        }

    @staticmethod
    def _preview_create(params: Dict[str, Any]) -> Dict[str, Any]:
        """建库前先让用户看清「要建的是什么」（只读参数，不碰库）"""
        out: Dict[str, Any] = {}
        bank_name = (params.get("bank_name") or "").strip()
        if bank_name:
            out["bankName"] = bank_name
        subject = (params.get("subject") or "").strip()
        if subject:
            out["subject"] = subject
        return out

    async def _preview_delete_by_name(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        """按名删除的预览：**只读反查**出真实题库，卡片才说得清「删的是哪个」"""
        bank_name = (params.get("bank_name") or "").strip()
        if not bank_name:
            return {}
        bank = await qws.find_bank_by_name(ctx.db, ctx.user_id, bank_name)
        if bank is None:
            # 不能回显模型的名字（那会显示一个库里不存在的题库），明确说没找到
            return {"bankName": "（没有找到这个题库：名称需要与题库列表完全一致）"}
        return {
            "bankName": bank.bank_name,
            "subject": bank.subject,
            "totalQuestions": bank.total_questions or 0,
        }

    async def _preview_delete_many(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        """批量删除的预览：`count` + `sample`（题库名）+ 找不到的名字分开放

        名字同样**只读反查**；查不到的单列（否则用户以为删 3 个、实际只删了 1 个）。
        """
        ids: List[int] = []
        for value in _as_list(params.get("bank_ids")):
            try:
                ids.append(int(value))
            except (TypeError, ValueError):
                continue

        missing_names: List[str] = []
        for name in _as_list(params.get("bank_names")):
            name = str(name).strip()
            if not name:
                continue
            bank = await qws.find_bank_by_name(ctx.db, ctx.user_id, name)
            if bank is None:
                missing_names.append(name)
            else:
                ids.append(bank.id)

        ids = list(dict.fromkeys(ids))
        if not ids and not missing_names:
            return {}

        rows = []
        if ids:
            rows = (
                await ctx.db.execute(
                    select(
                        QuestionBank.id,
                        QuestionBank.bank_name,
                        QuestionBank.total_questions,
                    ).where(
                        QuestionBank.id.in_(ids),
                        QuestionBank.user_id == ctx.user_id,
                    )
                )
            ).all()
        names = [str(r[1]) for r in rows]

        out: Dict[str, Any] = {
            "count": len(names),
            "sample": names[:_PREVIEW_SAMPLE] or ["（没有找到属于你的题库）"],
        }
        # 勾选卡（用户 2026-10-17 需求）：一张卡列出全部待删题库，用户可逐条反悔。
        # 没有这份 draft 时模型会为了删 N 个库循环调 N 次 delete → N 张卡。
        if rows:
            order = {int(i): n for n, i in enumerate(ids)}
            items = [
                {
                    "key": f"bank:{r[0]}",
                    "id": int(r[0]),
                    "title": str(r[1] or ""),
                    "subtitle": f"{int(r[2] or 0)} 道题",
                }
                for r in rows
            ]
            items.sort(key=lambda it: order.get(it["id"], 9999))
            out["draft"] = {
                "kind": "batch_delete",
                "entity": "bank",
                "entityLabel": "题库",
                "items": items,
            }
        if missing_names:
            # 键名用 `missingNames`：前端已有中文标签「未找到的名称」，别用自造键
            # （认不出来的键会**原样打印英文键名**，那就是给用户看 JSON）
            out["missingNames"] = missing_names[:_PREVIEW_SAMPLE]
        return out

    # ------------------------------------------------------------------
    # 回退（2026-10-20 新增）
    # ------------------------------------------------------------------

    def undo_plan(
        self,
        params: Dict[str, Any],
        result: Dict[str, Any],
        before: Dict[str, Any] | None = None,
    ) -> Dict[str, Any] | None:
        """声明这一笔题库操作怎么撤（契约见 `base.AgentTool.undo_plan`）

        | action                              | 逆操作                         |
        |-------------------------------------|--------------------------------|
        | create                              | **不可回退**（见下）            |
        | delete / delete_by_name / delete_many | `restore_tree`（快照整树重插） |
        | update                              | **不可回退**（见下）            |

        ⚠️ 删除为什么不走 `restore`（逻辑删）：`question_bank` 没有 `del_flag`，
        且删除是**应用层级联**（一次清掉题目/子题/三张个人标记表/笔记关联/分享）。
        我们**实测否决**了「加 del_flag + 全仓补过滤」那条路：`with_loader_criteria`
        对 Core 列 select 无效，而全仓有 129 处方库/题目的读点 —— 漏一处就是
        「已删题库重新出现在列表里」，比不能回退严重得多。详见 `bank_tree_snapshot`。

        删除的回退数据来自 `_delete` 系列在**删除之前**塞进回执的
        `UNDO_BEFORE_KEY`（`_execute_tool` 会摘掉它交给账本，模型与界面都看不到）。

        ⚠️ `create` 为什么不可回退：`question_write_service.delete_banks` 是**物理删**
        且级联清个人标记 —— 用它去撤一次误建，会把用户在那个题库里积累的错题/收藏
        一起抹掉（那些是**别的行为**留下的数据，不该被「撤销建库」牵连）。
        用户真要删，走 delete（那个才带快照）。
        ⚠️ `update` 为什么不可回退：`qws.update_bank` 只接受「改成什么」，不返回改前值，
        而 `bank_manage._update` 没留快照。改错了题库名/科目的挽回成本极低（再改一次），
        不值得为此动一个被路由共用的服务函数。
        """
        action = str(params.get("action") or "")
        if action in ("delete", "delete_by_name", "delete_many"):
            # ⚠️ 快照来自 `before` 参数，**不是** `result`：
            #    `_execute_tool` 会先 `pop(UNDO_BEFORE_KEY)` 再调 `record_op`，
            #    而 `record_op` 才调本函数 → `result` 里永远看不到快照。
            #    （第一版从这里读 result 的 `__snapshot__`，结果快照永远是 None，
            #      回退静默变成「快照不可用」—— 由 e2e 测试发现。）
            snapshot = before if isinstance(before, dict) else None
            if not snapshot or not snapshot.get("rowCount"):
                return {"undoable": False, "reason": REASON_MISSING_SOFT_DELETE}
            if snapshot.get("skipped"):
                return {
                    "undoable": False,
                    "reason": str(snapshot.get("reason") or "too_large"),
                }
            return {
                "op": OP_RESTORE_TREE,
                "targetTable": "question_bank",
                # 整树恢复走快照，不靠 id 列表；但契约要求 targetIds 能定位到行，
                # 否则 `record_op` 会判 `MISSING_TARGET_ID`（见那里的守卫）。
                "targetIds": [int(i) for i in (snapshot.get("bankIds") or [])],
                "before": snapshot,
                "undoable": True,
            }
        # ⚠️ 下面两条拿到的是**给用户看的具体原因**，不是笼统的「还没实现」。
        #
        # 为什么 `create` 不撤销：撤「建库」最自然的做法是把它删掉，但
        # `qws.delete_banks` 是物理删且**级联清个人标记** —— 用它去撤一次误建，
        # 会把用户在那个库里积累的错题/收藏一起抹掉（那些是**别的行为**留下的数据，
        # 不该被「撤销建库」牵连）。用户真要删，走 delete（那个带快照、能再撤回来）。
        if action == "create":
            return {
                "undoable": False,
                "reason": "新建的题库不会自动撤销（删除题库会连带清掉其中的错题与收藏）；"
                "要删的话说一句「删掉这个题库」即可，删除本身是能回退的",
            }
        # 为什么 `update` 不撤销：`qws.update_bank` 只接受「改成什么」、不返回改前值，
        # 本工具也没留快照。改错了题库名/科目的挽回成本极低（再改一次），
        # 不值得为此动一个被 API 路由共用的服务函数。
        if action == "update":
            return {
                "undoable": False,
                "reason": "题库信息的修改不会自动撤销（改名 / 改科目再改一次即可，成本很低）",
            }
        return None

    # ------------------------------------------------------------------

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        action = str(params.get("action") or "")
        handlers = {
            "list": self._list,
            "detail": self._detail,
            "create": self._create,
            "update": self._update,
            "delete": self._delete,
            "delete_by_name": self._delete_by_name,
            "delete_many": self._delete_many,
        }
        handler = handlers.get(action)
        if handler is None:
            return fail(
                f"未知操作: {action}",
                "action 只能是 list / detail / create / update / delete / delete_by_name",
            )
        return await handler(params, ctx)

    # ------------------------------------------------------------------
    # 各 action
    # ------------------------------------------------------------------

    async def _list(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        """列自己的题库（支持 `bank_name` 模糊 / `subject` 过滤 + 分页）

        分页口径与 `question_manage._list` **逐字对齐**：`limit`（默认 20）/ `offset`（默认 0），
        返回 `offset` / `count`（**本页**条数）/ `total`（符合过滤条件的总数）/ `hasMore`。
        只回一页而不报总量的话，模型与前端都会把「本次返回 20 个」当成「一共 20 个」。
        """
        banks = await qws.list_user_banks(
            ctx.db,
            ctx.user_id,
            keyword=(params.get("bank_name") or "").strip() or None,
            subject=(params.get("subject") or "").strip() or None,
        )
        limit = max(int(params.get("limit") or 20), 1)
        offset = max(int(params.get("offset") or 0), 0)
        total = len(banks)
        page = banks[offset : offset + limit]
        return ok(
            action="list",
            offset=offset,
            count=len(page),
            total=total,
            hasMore=offset + len(page) < total,
            banks=[qws.bank_brief(b) for b in page],
        )

    async def _detail(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        bank = await self._resolve_bank(params, ctx)
        if isinstance(bank, dict):  # fail 信封
            return bank

        # 顺带把题型分布带上，模型回答「这个题库都有什么」时不用再查一次
        from sqlalchemy import func

        from app.models.question import QuestionMain

        rows = await ctx.db.execute(
            select(QuestionMain.question_type, func.count())
            .where(QuestionMain.bank_id == bank.id, QuestionMain.status == "0")
            .group_by(QuestionMain.question_type)
        )
        distribution = {
            qws.QUESTION_TYPE_TEXT.get(int(qtype), str(qtype)): int(count)
            for qtype, count in rows.all()
        }
        return ok(action="detail", bank=qws.bank_brief(bank), questionTypes=distribution)

    async def _create(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        bank_name = (params.get("bank_name") or "").strip()
        if not bank_name:
            return fail("创建题库需要题库名称", "请提供 bank_name")

        existing = await qws.find_bank_by_name(ctx.db, ctx.user_id, bank_name)
        if existing is not None:
            return fail(
                f"已存在同名题库「{bank_name}」",
                "请换一个名字，或改用 action=detail 查看已有题库",
                bankId=existing.id,
            )

        bank = await qws.create_bank(
            ctx.db,
            user_id=ctx.user_id,
            bank_name=bank_name,
            subject=params.get("subject"),
            description=params.get("description"),
            is_public=params.get("is_public"),
        )
        return ok(
            action="create",
            bank=qws.bank_brief(bank),
            message=f"题库「{bank.bank_name}」创建成功（ID={bank.id}）",
            # 2026-10-26：写成功后给出落地页，前端渲染成「去看看」按钮。
            # 原来只有英语类工具带 jumpUrl，题库创建完用户还得自己去侧边栏找 ——
            # 这是「智能体说建好了，但我看不到」的典型断点。
            jumpUrl=f"/front/questionPractice/{int(bank.id)}",
        )

    async def _update(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        bank = await self._resolve_bank(params, ctx)
        if isinstance(bank, dict):
            return bank
        if bank.user_id != ctx.user_id:
            return fail("只能修改自己的题库", "请确认 bank_id 是否属于你")

        # 字段应用口径收在 `question_write_service.update_bank`（与「可编辑草稿确认」
        # 路径共用，避免两处各写一份、早晚漂移）。返回值 `(changed, conflict)`。
        changed, conflict = await qws.update_bank(
            ctx.db,
            bank,
            bank_name=(params.get("bank_name") or "").strip(),
            subject=params.get("subject"),
            description=params.get("description"),
            is_public=params.get("is_public"),
        )
        if conflict is not None:
            return fail(
                f"已存在同名题库「{conflict.bank_name}」（ID={conflict.id}）",
                "请换一个名字；若要合并，请先把那个题库改名或删除",
                bankId=conflict.id,
            )
        if not changed:
            return fail(
                "没有提供任何要修改的字段",
                "请至少给出 bank_name / subject / description / is_public 之一",
            )
        return ok(
            action="update",
            bank=qws.bank_brief(bank),
            changed=changed,
            message=f"题库「{bank.bank_name}」已更新（{', '.join(changed)}）",
        )

    async def _delete(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        bank_id = params.get("bank_id")
        if bank_id is None:
            return fail("删除题库需要 bank_id", "如果只知道名称，请用 action=delete_by_name")
        # ⚠️ 快照必须在**删除之前**抓（删完就查不到了）—— 见 `bank_tree_snapshot`
        snapshot = await self._snapshot(ctx, [int(bank_id)])
        result = await qws.delete_banks(ctx.db, ctx.user_id, [int(bank_id)])
        if not result["deleted"]:
            return fail(
                f"题库不存在或不属于你：bank_id={bank_id}",
                "请先用 action=list 确认题库 ID",
            )
        names = "、".join(f"「{b['bankName']}」" for b in result["deleted"])
        return ok(
            action="delete",
            deleted=result["deleted"],
            message=f"已删除题库{names}",
            **{UNDO_BEFORE_KEY: snapshot},
        )

    async def _delete_by_name(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        bank_name = (params.get("bank_name") or "").strip()
        if not bank_name:
            return fail("按名删除需要 bank_name", "请提供要删除的题库名称")

        bank = await qws.find_bank_by_name(ctx.db, ctx.user_id, bank_name)
        if bank is None:
            # 名称可能带前缀/简称，给模型一个可执行的下一步，而不是干巴巴报错
            candidates = await qws.list_user_banks(ctx.db, ctx.user_id, keyword=bank_name)
            hint = "请先用 action=list 确认准确的题库名称"
            if candidates:
                names = "、".join(b.bank_name for b in candidates[:5])
                hint = f"名称需要完全一致。名称里包含「{bank_name}」的题库有：{names}"
            return fail(f"没有找到名为「{bank_name}」的题库", hint)

        snapshot = await self._snapshot(ctx, [bank.id])
        result = await qws.delete_banks(ctx.db, ctx.user_id, [bank.id])
        return ok(
            action="delete_by_name",
            deleted=result["deleted"],
            message=f"已删除题库「{bank_name}」及其全部题目",
            **{UNDO_BEFORE_KEY: snapshot},
        )

    async def _delete_many(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        """一次删除多个题库（`bank_ids` 和/或 精确 `bank_names`）

        「把英语和物理题库都删了」「删掉这几个题库」这类请求只需**一次**调用，
        不必让模型逐个 delete（又慢又容易在中途打转）。
        只删**属于当前用户**的题库；找不到的名字如实回报，方便模型下一轮纠正。
        """
        ids: List[int] = []
        for value in _as_list(params.get("bank_ids")):
            try:
                ids.append(int(value))
            except (TypeError, ValueError):
                continue

        names = [
            str(n).strip() for n in _as_list(params.get("bank_names")) if str(n).strip()
        ]
        if not ids and not names:
            return fail(
                "delete_many 需要 bank_ids 或 bank_names",
                "请给出要删除的题库 ID 列表（bank_ids）或精确名称列表（bank_names）",
            )

        missing_names: List[str] = []
        for name in names:
            bank = await qws.find_bank_by_name(ctx.db, ctx.user_id, name)
            if bank is None:
                missing_names.append(name)
            else:
                ids.append(bank.id)

        snapshot = await self._snapshot(ctx, ids)
        result = await qws.delete_banks(ctx.db, ctx.user_id, ids)
        deleted = result["deleted"]
        parts = [f"已删除 {len(deleted)} 个题库"]
        if deleted:
            parts.append("、".join(f"「{b['bankName']}」" for b in deleted))
        if missing_names:
            parts.append("未找到：" + "、".join(f"「{n}」" for n in missing_names))
        if result["missing"]:
            parts.append("不存在或不属于你：" + ", ".join(str(i) for i in result["missing"]))
        return ok(
            action="delete_many",
            deleted=deleted,
            missingIds=result["missing"],
            missingNames=missing_names,
            message="；".join(parts),
            **{UNDO_BEFORE_KEY: snapshot},
        )

    @staticmethod
    async def _snapshot(
        ctx: ToolContext, bank_ids: List[int]
    ) -> Dict[str, Any]:
        """抓删除前快照（**只读**；失败时返回空快照，绝不阻断删除本身）

        ⚠️ 快照失败**不能让删除也失败**：用户要的是「删掉这个题库」，
        而快照只是「万一他后悔了能救回来」的增强项。抓不到快照时宁可
        「删了但回退不了（并如实告知）」，也不该「因为存不下快照所以删不掉」。
        """
        from app.services.ai.agent import bank_tree_snapshot as snap

        try:
            return await snap.snapshot_banks(ctx.db, ctx.user_id, bank_ids)
        except Exception as e:  # noqa: BLE001
            logger.warning("[bank_manage] 删除前快照失败（不影响删除）: {}", e)
            return {"kind": "bank_tree", "rowCount": 0}

    # ------------------------------------------------------------------

    async def _resolve_bank(self, params: Dict[str, Any], ctx: ToolContext):
        """按 bank_id 或 bank_name 定位题库；失败时返回 `fail()` 信封（dict）

        ⚠️⚠️ **`bank_id` 分支必须校验归属**（2026-09-22 修的越权缺陷）：这里原来
        `ctx.db.get(QuestionBank, int(bank_id))` 后**直接 return**，于是 `_detail`
        能读到别人的题库（题库名 / 科目 / 题数）。
        `_update` / `_delete` 各自另有兜底（`bank.user_id` 检查 / `delete_banks(user_id)`），
        所以此前只有**读**这条口子漏了 —— 但那也是别人的数据。
        「按名字」那一路本来就有过滤（`find_bank_by_name(..., ctx.user_id, ...)`）。

        「不存在」与「不是你的」**刻意回同一句**：分开说等于给攻击者一个
        「这个 id 存在」的探测预言机（与 knowledge_search / question_manage 同口径）。
        """
        bank_id = params.get("bank_id")
        bank_name = (params.get("bank_name") or "").strip()

        if bank_id is not None:
            bank = await ctx.db.get(QuestionBank, int(bank_id))
            if bank is not None and int(bank.user_id or 0) != int(ctx.user_id):
                bank = None
            if bank is None:
                return fail(
                    f"题库不存在或不属于你：bank_id={bank_id}",
                    "请先用 action=list 查询**你自己的**题库（只能操作自己的题库）",
                )
            return bank

        if bank_name:
            bank = await qws.find_bank_by_name(ctx.db, ctx.user_id, bank_name)
            if bank is None:
                return fail(
                    f"没有找到名为「{bank_name}」的题库",
                    "请先用 action=list 查看你的题库名称（需完全一致）",
                )
            return bank

        return fail("需要 bank_id 或 bank_name", "请提供其中一个")


__all__ = ["BankManageTool"]
