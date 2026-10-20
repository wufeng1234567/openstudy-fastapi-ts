"""
`bank_share_manage` —— 题库分享 / 领取 / 复制工具（Agent 自封装）

先把三件事说清楚（**读代码得来，不是猜的**）
------------------------------------------
· **分享（share）**：只有**题库主**能为自己名下的题库生成「分享码 + 分享链接」。
  库里落一行 `bank_share`（status='0' 有效、permission='read'）。
  ⚠️ 现有实现里**没有「分享给某个用户」这回事** —— 分享产出的是 token/分享码，
  谁拿到谁能领取。所以确认卡片**不可能**显示「目标用户」（没有这个字段），
  它显示的是「哪个题库、多少题、有效期多久」。想成「发给某个人」是误解。
· **领取（receive）**：别人用 token/分享码换取**只读**访问 —— 在**领取方**名下
  写一条题库收藏 + 一条领取记录；首次领取还会让题库主的 `receive_count` +1
  并**给他发一条通知**。题库能不能编辑永远由 `question_bank.user_id` 决定。
· **复制（copy）**：领取方想要「可编辑的自己的一份」时做深拷贝
  （`bank_copy_service.copy_bank_to_user`）。非题库主复制时**必须**题库主开放
  `allow_fork`（0=不允许）。

三个动作对第三方的影响不同，确认策略也不同
----------------------------------------
· `share`：产生一把「谁拿到谁能看」的钥匙 → 写操作，要确认
· `receive`：给**题库主**发通知、给自己的收藏夹加一条 → 写操作，要确认
· `revoke`：撤销不可逆，且会**让已经领取的人失效**（还给他们各发一条通知）
  → 按破坏性处理，即使 autoConfirm 开着也要二次确认
· `copy` / `list_shares`：前者在自己名下建库（写，要确认），后者只读

⚠️ 按 id 定位的地方都带归属条件
------------------------------
`share_id` → `bank_share_service.get_own_share`（WHERE 里带 `owner_id`）；
`bank_id` → 分享时必须是自己的库（服务层校验）、复制时过可见性 + allow_fork。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.question import QuestionBank
from app.services import bank_share_service as bss
from app.services import question_write_service as qws
from app.services.ai.agent.base import (
    OP_RESTORE,
    OP_SOFT_DELETE,
    REASON_AFFECTS_OTHERS,
    REASON_MISSING_TARGET_ID,
    AgentTool,
    ToolContext,
    fail,
    ok,
)
from app.services.bank_copy_service import copy_bank_to_user, copy_suffix_name
from app.services.bank_share_service import ShareError

#: 我发出的分享列表一页最多几条
MAX_SHARES_PAGE = 100
DEFAULT_SHARES_PAGE = 20

#: 确认卡片里的题干/名称最多多少字
_PREVIEW_CHARS = 60


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _share_brief(row: Dict[str, Any]) -> Dict[str, Any]:
    """把 `format_share` 的输出摊平成工具结果。

    ⚠️ 唯一改动：分享记录自带的那条**留言**从 `message` 改名成 `shareMessage`。
    工具结果的 `message` 是「给用户看的人话回执」的固定字段（前端
    `AgentToolDetail` 的 `HIDDEN_KEYS` 里就有它），两者同名会互相覆盖 ——
    覆盖掉的恰好是用户自己写的那句话。
    """
    out = dict(row)
    out["shareMessage"] = out.pop("message", None)
    return out


class BankShareManageTool(AgentTool):
    name = "bank_share_manage"
    #: ⚠️ 描述与参数说明一律英文（进系统提示词 `{{TOOLS}}` 与 Function Calling）
    description = (
        "Share question banks, claim a share, or copy a bank into the user's own account. "
        "Use it for 'share my bank with a friend', 'generate a share code', 'I got a share "
        "code, claim it for me', 'copy this bank so I can edit it', 'revoke that share'. "
        "action values: "
        "list_shares=list the shares THIS user has created (with code, expiry, how many "
        "people claimed it), "
        "share=create a share for one of the user's OWN banks by `bank_id` (optional "
        "`expire_days`; omit for never-expiring; optional `message` note) and return the "
        "share code to hand out, "
        "revoke=revoke a share the user created by `share_id` (irreversible; everyone who "
        "claimed it loses the link and gets a notification), "
        "receive=claim someone else's share by `token` or `code` — this only grants "
        "READ-ONLY access and adds the bank to the user's favourite banks, "
        "copy=deep-copy a bank into the user's own editable account by `bank_id` (optional "
        "`new_name`; defaults to '<name>（副本）'). The source must be visible to the user "
        "and, when it is not their own bank, its owner must allow copying. "
        "NOTE: 'sharing' produces a code/link — there is no way to share to one specific "
        "user. Use `bank_manage` to create/rename the bank itself."
    )
    #: 界面专用（只给前端看；不进 definitions() / describe()）
    label = "题库分享"
    description_zh = (
        "分享与领取题库：list_shares=我发出去的分享、share=生成分享码、"
        "revoke=撤销分享、receive=用分享码领取、copy=把别人的库复制到我的账号。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Operation to perform",
                "enum": ["list_shares", "share", "revoke", "receive", "copy"],
            },
            "bank_id": {
                "type": "integer",
                "description": (
                    "Bank ID (used by share= must be the user's own bank, and by copy= the "
                    "bank to copy). Get it from `bank_manage` list."
                ),
            },
            "share_id": {
                "type": "integer",
                "description": (
                    "Share ID (used by revoke; the `shareId` from list_shares — only shares "
                    "this user created can be revoked)."
                ),
            },
            "token": {
                "type": "string",
                "description": "Share token/link the user received (used by receive).",
            },
            "code": {
                "type": "string",
                "description": "6-character share code the user received (used by receive).",
            },
            "expire_days": {
                "type": "integer",
                "description": (
                    "Used by share: how many days the share stays valid. Omit (or 0) for a "
                    "share that never expires."
                ),
            },
            "message": {
                "type": "string",
                "description": "Used by share: an optional short note stored on the share.",
            },
            "new_name": {
                "type": "string",
                "description": (
                    "Used by copy: name for the new bank. Defaults to the source name plus "
                    "'（副本）'; it must not clash with a bank the user already owns."
                ),
            },
            "limit": {
                "type": "integer",
                "description": (
                    f"Max items per page (used by list_shares; default "
                    f"{DEFAULT_SHARES_PAGE}, max {MAX_SHARES_PAGE})."
                ),
            },
            "offset": {
                "type": "integer",
                "description": (
                    "0-based offset for list_shares (default 0). The reply carries `total` "
                    "and `hasMore`."
                ),
            },
        },
        "required": ["action"],
    }
    write_operation = True

    _WRITE_ACTIONS = {"share", "revoke", "receive", "copy"}
    #: 撤销不可逆、且会让第三方手里的收藏失效 → 按破坏性处理（永远二次确认）
    _DESTRUCTIVE_ACTIONS = {"revoke"}

    def needs_confirmation(self, params: Dict[str, Any]) -> bool:
        return str(params.get("action") or "") in self._WRITE_ACTIONS

    def is_destructive(self, params: Dict[str, Any]) -> bool:
        return str(params.get("action") or "") in self._DESTRUCTIVE_ACTIONS

    def confirm_policy(self, params: Dict[str, Any]) -> bool:
        """`share` / `copy` 都是轻量的一步操作（不影响他人、可撤销），不额外强制确认"""
        return False

    # ------------------------------------------------------------------ 预览

    async def preview(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        """确认卡片要说清「会动到哪个题库 / 影响多少人」

        一律**只读反查**（`ctx.db.get` 后判归属 / `get_own_share` / `share_info`），
        绝不回显模型传进来的字符串 —— 否则用户确认的是 A、实际动的是 B。
        """
        action = str(params.get("action") or "")
        try:
            if action == "share":
                return await self._preview_share(params, ctx)
            if action == "revoke":
                return await self._preview_revoke(params, ctx)
            if action == "receive":
                return await self._preview_receive(params, ctx)
            if action == "copy":
                return await self._preview_copy(params, ctx)
        except Exception:  # noqa: BLE001 - 预览失败不能影响主流程
            return {}
        return {}

    async def _preview_share(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        bank_id = _to_int(params.get("bank_id"))
        if bank_id is None:
            return {}
        bank = await ctx.db.get(QuestionBank, bank_id)
        if bank is None or int(bank.user_id or 0) != int(ctx.user_id):
            # 不能回显模型给的名字：库里有没有这个题库还没确定
            return {"bankName": "（没有找到属于你的题库：只有自己的题库能分享）"}
        out: Dict[str, Any] = {
            "bankName": bank.bank_name,
            "totalQuestions": bank.total_questions or 0,
        }
        days = _to_int(params.get("expire_days"))
        out["expireText"] = f"{days} 天后过期" if days else "永不过期"
        note = (params.get("message") or "").strip()
        if note:
            out["shareMessage"] = note[:_PREVIEW_CHARS]
        return out

    async def _preview_revoke(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        share_id = _to_int(params.get("share_id"))
        if share_id is None:
            return {}
        try:
            # ⚠️ get_own_share 的 WHERE 里带 owner_id：别人的分享在这里查不到
            share = await bss.get_own_share(ctx.db, ctx.user_id, share_id)
        except ShareError:
            return {"shareId": share_id, "bankName": "（没有找到你发出的这条分享）"}

        bank = await ctx.db.get(QuestionBank, int(share.bank_id))
        active = await bss.count_active_receivers(ctx.db, share.id)
        out: Dict[str, Any] = {
            "shareId": share.id,
            "bankName": bank.bank_name if bank else "（原题库已删除）",
            "receiveCount": share.receive_count or 0,
        }
        if active:
            out["invalidatedReceivers"] = active
        if share.status != "0":
            out["bankName"] = f"（这条分享已经撤销过了）{out['bankName']}"
        return out

    async def _preview_receive(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        token = (params.get("token") or "").strip() or None
        code = (params.get("code") or "").strip() or None
        if not token and not code:
            return {}
        try:
            info = await bss.share_info(ctx.db, ctx.user_id, token=token, code=code)
        except ShareError as e:
            return {"bankName": f"（{e.message}）"}
        return {
            "bankName": info.get("bankName"),
            "ownerName": info.get("ownerName"),
            "totalQuestions": info.get("totalQuestions"),
            "permission": info.get("permission"),
            "expireTime": info.get("expireTime"),
            "received": info.get("received"),
        }

    async def _preview_copy(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        bank_id = _to_int(params.get("bank_id"))
        if bank_id is None:
            return {}
        try:
            bank = await bss.load_copyable_bank(ctx.db, ctx.user_id, bank_id)
        except ShareError as e:
            return {"bankName": f"（不能复制：{e.message}）"}
        new_name = (params.get("new_name") or "").strip() or copy_suffix_name(bank.bank_name)
        return {
            "bankName": bank.bank_name,
            "totalQuestions": bank.total_questions or 0,
            "newBankName": new_name,
            "allowFork": int(getattr(bank, "allow_fork", 1) or 0),
        }

    # ------------------------------------------------------------------ 执行

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        action = str(params.get("action") or "")
        handler = {
            "list_shares": self._list_shares,
            "share": self._share,
            "revoke": self._revoke,
            "receive": self._receive,
            "copy": self._copy,
        }.get(action)
        if handler is None:
            return fail(
                f"未知操作: {action}",
                "action 只能是 list_shares / share / revoke / receive / copy",
            )
        return await handler(params, ctx)

    # ------------------------------------------------------------------
    # 回退（2026-10-20 新增）
    # ------------------------------------------------------------------

    def undo_plan(self, params: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any] | None:
        """声明这一笔分享操作怎么撤（契约见 `base.AgentTool.undo_plan`）

        | action  | 逆操作                              | 代价 / 边界                    |
        |---------|-------------------------------------|--------------------------------|
        | share   | `soft_delete`（status '0'→'1'）      | 全撤，无副作用                  |
        | revoke  | `restore`（status '1'→'0'）          | ⚠️ **部分回退**，见下           |
        | receive | `restore`（领取记录 status '1'→'0'） | 收藏题库那行由收藏表自身处理     |
        | copy    | **不可回退**                         | 见下                            |

        ⚠️ `revoke` 为什么只能「部分回退」：
        `revoke_share` 做三件事 —— ① 把 `bank_share.status` 置 '1'；② 把全部
        `bank_share_receive.status` 置 '1'；③ **给每个领取方发一条通知**。
        ①② 能翻回来（本函数声明了），③ **收不回来** —— 通知已经推到别人手机上。
        所以声明 `undoable=True` 的同时带上 `reason=REASON_AFFECTS_OTHERS`：
        回退会执行，界面上标「部分回退」并说清「通知已发出」，这才是诚实的。
        （原来 `rollback_service._TOOL_ACTION_REASONS` 里写的是「revoke 不可回退」；
        现在有了 status 翻转能力，从「拒绝回退」升级成「撤了但告知副作用」，
        那个表项已随之删除 —— 两处声明必然漂移，只留这一处。）

        ⚠️ `copy` 为什么不可回退：它用 `question_write_service` 深拷出一个**新题库**
        （新 id、新题目行）。删掉它可以（`bank_manage` 的 delete 能做到），但那是
        「删一个题库」的语义，应当通过题库域的回退去做；在这里声明会导致
        同一次 copy 产生两条账单、点一次回退撤两遍。返回 `None` = 交给用户显式删除。
        """
        action = str(params.get("action") or "")

        if action == "share":
            sid = _to_int(result.get("shareId"))
            if sid is None:
                return {"undoable": False, "reason": REASON_MISSING_TARGET_ID}
            return {
                "op": OP_SOFT_DELETE,
                "targetTable": "bank_share",
                "targetIds": [sid],
                "undoable": True,
            }

        if action == "revoke":
            sid = _to_int(result.get("shareId")) or _to_int(params.get("share_id"))
            if sid is None:
                return {"undoable": False, "reason": REASON_MISSING_TARGET_ID}
            return {
                "op": OP_RESTORE,
                "targetTable": "bank_share",
                "targetIds": [sid],
                "undoable": True,
                # ⚠️ 非空 = **部分回退**：分享本身恢复了，但已经发出去的通知收不回
                "reason": REASON_AFFECTS_OTHERS,
            }

        if action == "receive":
            rid = _to_int(result.get("receiveId")) or _to_int(result.get("id"))
            if rid is None:
                # 领取记录 id 不一定在回执里（幂等命中已有记录时是 `exists`）——
                # 拿不到就如实说「回退不了」，绝不用 bank_id 猜一行（会撤错人）
                return {"undoable": False, "reason": REASON_MISSING_TARGET_ID}
            return {
                "op": OP_RESTORE,
                "targetTable": "bank_share_receive",
                "targetIds": [rid],
                "undoable": True,
            }

        return None

    async def _list_shares(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        try:
            rows: List[Dict[str, Any]] = await bss.my_shares(ctx.db, ctx.user_id)
        except Exception as e:  # noqa: BLE001
            return fail(f"查询分享列表失败：{e}", "请稍后重试")

        limit = _to_int(params.get("limit")) or DEFAULT_SHARES_PAGE
        limit = max(1, min(MAX_SHARES_PAGE, limit))
        offset = max(_to_int(params.get("offset")) or 0, 0)
        total = len(rows)
        page = [_share_brief(r) for r in rows[offset : offset + limit]]

        if total == 0:
            message = "这个用户还没有发出过任何题库分享"
        else:
            effective = sum(1 for r in page if r.get("effective"))
            message = (
                f"共发出 {total} 条分享，本次返回 {len(page)} 条"
                + (f"（其中 {effective} 条仍然有效）" if effective else "（都已失效）")
            )
        return ok(
            **{
                "action": "list_shares",
                "offset": offset,
                "count": len(page),
                "total": total,
                "hasMore": offset + len(page) < total,
                "shares": page,
                "message": message,
            }
        )

    async def _share(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        bank_id = _to_int(params.get("bank_id"))
        if bank_id is None:
            return fail(
                "分享题库需要 bank_id",
                "请先用 bank_manage list 拿到题库 ID（只能分享自己的题库）",
            )
        try:
            share, bank = await bss.create_share(
                ctx.db,
                ctx.user_id,
                bank_id,
                expire_days=params.get("expire_days"),
                message=params.get("message"),
            )
        except ShareError as e:
            hint = (
                "只有自己的题库能分享。请先用 bank_manage list 确认 bank_id 属于你"
                if e.code == 403
                else "请先用 bank_manage list 确认题库 ID"
            )
            return fail(e.message, hint)

        row = _share_brief(bss.format_share(share, bank))
        expire_text = row.get("expireTime") or "永不过期"
        return ok(
            **{
                "action": "share",
                **row,
                "expireText": expire_text,
                "message": (
                    f"题库「{bank.bank_name}」的分享已创建，分享码 {share.share_code}"
                    f"（有效期：{expire_text}）—— 把分享码发给别人，他就能领取（只读）"
                ),
            }
        )

    async def _revoke(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        share_id = _to_int(params.get("share_id"))
        if share_id is None:
            return fail(
                "撤销分享需要 share_id",
                "请先用 action=list_shares 找到要撤销的 shareId",
            )
        try:
            info = await bss.revoke_share(ctx.db, ctx.user_id, share_id)
        except ShareError as e:
            return fail(e.message, "请先用 action=list_shares 确认这是你发出的分享")
        return ok(
            **{
                "action": "revoke",
                "revoked": 1,
                **info,
                "message": (
                    f"已撤销题库「{info['bankName']}」的分享"
                    + (
                        f"，{info['invalidatedReceivers']} 位领取方已失效并收到通知"
                        if info.get("invalidatedReceivers")
                        else "（当时没有人领取）"
                    )
                ),
            }
        )

    async def _receive(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        token = (params.get("token") or "").strip() or None
        code = (params.get("code") or "").strip() or None
        if not token and not code:
            return fail(
                "领取分享需要 token 或 code",
                "请让用户提供分享链接（token）或 6 位分享码（code）",
            )
        try:
            info = await bss.receive_share(ctx.db, ctx.user_id, token=token, code=code)
        except ShareError as e:
            return fail(
                e.message,
                "请确认分享码/链接是否完整、是否已过期或被撤销；"
                "已经领取过的再领一次是安全的（幂等）",
            )
        status_text = {
            "created": "已领取",
            "restored": "已重新领取（之前取消过收藏）",
            "exists": "之前就已经领取过",
        }.get(str(info.get("resultStatus")), "已领取")
        return ok(
            **{
                "action": "receive",
                **info,
                # ⚠️ `resultStatus` 是机器码（created/restored/exists，非恒定值域），
                #    必须同时给一份人话 —— 否则执行结果面板上就是一行英文 `created`。
                #    值域出处：`bank_share_service.receive_share` L493-498；这里用**同一份**
                #    `status_text`，不另抄一张表（抄两份必然漂）。
                "resultStatusText": status_text,
                "message": (
                    f"{status_text}题库「{info['bankName']}」—— "
                    "只读访问，已加入你的收藏题库"
                ),
            }
        )

    async def _copy(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        bank_id = _to_int(params.get("bank_id"))
        if bank_id is None:
            return fail(
                "复制题库需要 bank_id",
                "请先用 bank_manage list（或 question_manage 的结果）拿到题库 ID",
            )
        try:
            bank = await bss.load_copyable_bank(ctx.db, ctx.user_id, bank_id)
        except ShareError as e:
            return fail(
                e.message,
                "只有你能看到的题库才能复制；别人的题库还需要主人开放复制权限",
            )

        new_name = (params.get("new_name") or "").strip() or copy_suffix_name(bank.bank_name)
        # ⚠️ 重名校验：question_bank.bank_name 在库里**没有**唯一约束，但
        #    `bank_manage` 的按名定位（find_bank_by_name）用 `.first()` —— 一旦出现
        #    同名，按名删/按名查的行为就不确定了。所以这里主动挡一道（与
        #    bank_manage._update 的重名校验同一理由）。
        dup = await qws.find_bank_by_name(ctx.db, ctx.user_id, new_name)
        if dup is not None:
            return fail(
                f"你名下已经有名为「{new_name}」的题库（bankId={dup.id}）",
                "请用 new_name 指定另一个名字（例如加个日期），"
                "或者先用 bank_manage 处理同名的那个题库",
            )

        try:
            new_bank = await copy_bank_to_user(ctx.db, bank, ctx.user_id, new_name=new_name)
        except Exception as e:  # noqa: BLE001 - 深拷贝可能因数据问题失败
            return fail(
                f"复制题库失败：{type(e).__name__}: {e}",
                "可以稍后重试；如果一直失败，请联系管理员检查这个题库的数据",
            )

        return ok(
            **{
                "action": "copy",
                "bank": qws.bank_brief(new_bank),
                "sourceBankId": bank.id,
                "sourceBankName": bank.bank_name,
                "allowFork": int(getattr(bank, "allow_fork", 1) or 0),
                "message": (
                    f"已把「{bank.bank_name}」复制为你自己的题库「{new_bank.bank_name}」"
                    f"（bankId={new_bank.id}，含 {new_bank.total_questions or 0} 道题），"
                    "现在可以随意修改"
                ),
            }
        )


__all__ = ["BankShareManageTool", "MAX_SHARES_PAGE"]
