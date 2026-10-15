"""
`memory_manage` —— 长期记忆管理工具（Agent 自封装）

补的是一条**断头路**
-------------------
`memory_search` 特意把 `memoryId` 返回给模型、并在注释里写明「便于用户说『把这条忘掉』时
定点删除」，但当时**没有任何工具能删** —— 用户说「忘掉那件事」，模型只能口头答应，
记忆原封不动地留在库里、下一轮又会被 L1 注入回来。这个工具就是那个缺口。

复用的是 `services/ai/memory_service` 的既有函数（`delete_memory` / `clear_memories` /
`count_by_type` / `get_memory` / `list_memories`），**一行 SQL 都不重写**：
淘汰限额、类型校验、归属校验都已经在那里了。

⚠️ 写操作为什么自己开会话（这一条很关键，别「优化」掉）
------------------------------------------------------
`memory_service` 的写函数**内部会 `commit()`**，而 `loop._execute_tool` 会把
`write_operation=True` 的工具包在 `async with ctx.db.begin_nested()` 里。两者相遇时
SAVEPOINT 里的 `commit()` 会把外层事务一起提交掉，退出上下文时抛
`Can't operate on closed transaction inside context manager`
—— 实测（`tests/_probe_nested_commit.py`，PG 真库）：**异常抛了，但数据已经写进去了**。
换到工具层就是「用户看到『执行失败』，其实记忆已经删了」，比不删更糟。
所以本工具的所有写操作都开**自己的一次性会话**（与 `memory_hook` / `runtime_context`
同一做法：「增强项/独立写不要寄生在别人的事务里」）。读操作仍走 `ctx.db`（只读，无害）。

⚠️ 删记忆的**回执里绝不带被删记忆的正文**
----------------------------------------
写操作成功后会由 `memory_hook` 落一条 episodic 记忆（内容是工具的 `message`）。
如果 `message` 里带上正文，用户刚说「忘掉这件事」，这件事就会**换一条记忆继续存在**
—— 删除失效，而且那条新记忆 importance=8，会被排到 L1 注入的最前面。
所以 `forget` / `clear` 的 message 只说「删了几条、什么类型、ID 是多少」。
（memory_hook 还会把 `params` 存进新记忆的 `metadata`，里面只有 id，没有正文。）
"""

from __future__ import annotations

from typing import Any, Dict, List

from loguru import logger

from app.services.ai import memory_service
from app.services.ai.agent.base import (
    OP_RESTORE_MEMORY,
    REASON_MISSING_TARGET_ID,
    UNDO_BEFORE_KEY,
    AgentTool,
    ToolContext,
    fail,
    ok,
)
from app.models.agent_memory import MAX_PER_TYPE, MEMORY_TYPES

#: `clear` 执行前要查「将被删的 id 列表」，这是那一次查询的上限。
#:
#: ⚠️ 为什么取「两类上限之和」：`clear` 能删的行**最多**就是两类各自的配额
#: （写入侧 `memory_service._evict` 每次写完都会把超配额的最旧行物理删掉，
#: 所以正常路径下活跃行数永远 ≤ 上限）。按上限之和去查 = 一条都漏不掉；
#: 真要有人绕过 `save_memory` 用裸 SQL 塞超量行，那是账本之外的事，本探针会告警。
_MAX_CLEAR_IDS = int(MAX_PER_TYPE.get("episodic", 0)) + int(
    MAX_PER_TYPE.get("conversation", 0)
)

#: 记忆类型的中文名（只用于给用户看的回执）
_TYPE_TEXT = {
    memory_service.MEMORY_TYPE_EPISODIC: "操作记录",
    memory_service.MEMORY_TYPE_CONVERSATION: "对话摘要",
}

#: `clear` 时允许的取值（`all` = 清空全部类型）
_ALL = "all"
_CLEAR_TYPES = (*MEMORY_TYPES, _ALL)

#: 确认卡片里正文最多显示多少字（正文是用户数据，够辨认就行）
_PREVIEW_CHARS = 120


class MemoryManageTool(AgentTool):
    name = "memory_manage"
    #: ⚠️ 描述与参数说明一律英文 —— 它们会同时进两处「提示词注入」通道：
    #:   ① `registry.describe()` → 系统提示词的 `{{TOOLS}}` 占位
    #:   ② `registry.definitions()` → Function Calling 的 `tools` 参数
    description = (
        "Manage your long-term memory about this user (what you remember from earlier "
        "sessions). Use it when the user asks you to FORGET something: 'forget this', "
        "'stop remembering that', 'delete what you know about X', 'clear my memories'. "
        "action values: list_types=show how many memories exist per type and each type's "
        "cap, forget=delete ONE memory by `memory_id`, clear=delete ALL memories of a "
        "given `memory_type` (or \"all\"). "
        "IMPORTANT: to delete one specific memory you must first call `memory_search` to "
        "find it and use the `memoryId` it returns — never guess an id. "
        "Deleting is NOT permanent: deleted memories can be brought back later from the "
        "user's 'recently deleted' list, so do not claim to the user that the memory is gone "
        "forever."
    )
    #: 界面专用（只给前端看；不进 definitions() / describe()）
    label = "长期记忆管理"
    description_zh = (
        "管理我对你的长期记忆：list_types=各类型各有几条、"
        "forget=忘掉指定的几条、clear=全部清空。删除后可以在「最近删除」里恢复。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Operation to perform",
                "enum": ["list_types", "forget", "clear"],
            },
            "memory_id": {
                "type": "integer",
                "description": (
                    "Memory ID to delete (used by forget). Take it from the `memoryId` "
                    "field returned by `memory_search`."
                ),
            },
            "memory_type": {
                "type": "string",
                "description": (
                    "Which kind of memory to clear (used by clear): "
                    "episodic=records of what the user did, "
                    "conversation=summaries of past chats, "
                    "all=EVERYTHING (use only when the user clearly says all memories)."
                ),
                "enum": list(_CLEAR_TYPES),
            },
        },
        "required": ["action"],
    }
    write_operation = True

    #: 需要确认的动作：两个都会真删数据
    _WRITE_ACTIONS = {"forget", "clear"}

    def needs_confirmation(self, params: Dict[str, Any]) -> bool:
        return str(params.get("action") or "") in self._WRITE_ACTIONS

    def is_destructive(self, params: Dict[str, Any]) -> bool:
        # 删记忆虽然能在「最近删除」里恢复，但用户当场看不到那些内容了（数据可见性变了），
        # 仍然算破坏性动作 → 即使 autoConfirm 开着也必须二次确认。
        # ⚠️ 声明本身不要改（`loop.py` 的 `_DESTRUCTIVE_ACTIONS` / needs_user_confirmation
        #    都靠它），变的只是「可撤销」这件事的说明。
        return str(params.get("action") or "") in self._WRITE_ACTIONS

    def undo_plan(self, params: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any] | None:
        """声明「这一笔记忆操作用什么撤」（契约见 `base.AgentTool.undo_plan`）

        两个动作都是逻辑删（`del_flag='2'`），所以逆操作是**恢复** —— 直接复用既有服务函数
        `memory_service.restore_memory`（`/ai/memory/restore` 端点用的也是它，不另写一套）：

          · `forget` → 恢复那一条（id 在回执的 `memoryId` 里）
          · `clear`  → 恢复**将被删的那一批**；id 列表**执行前**才查得出来，
            所以它走 `UNDO_BEFORE_KEY`（`before.memoryIds`），不进回执 ——
            回执里只有「已清空 N 条」，一串 id 给模型看没有意义。
            `targetIds` 因此留空，`rollback_service` 会从 `before` 里取（见 `_before_ids`）。
        """
        action = str(params.get("action") or "")
        if action == "forget":
            mid = _to_int(result.get("memoryId"))
            if mid is None:
                return {"undoable": False, "reason": REASON_MISSING_TARGET_ID}
            return {
                "op": OP_RESTORE_MEMORY,
                "targetTable": "ai_agent_memory",
                "targetIds": [mid],
                "undoable": True,
            }
        if action == "clear":
            return {
                "op": OP_RESTORE_MEMORY,
                "targetTable": "ai_agent_memory",
                "undoable": True,
            }
        return None

    async def preview(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        """确认卡片要说清「删的是哪一条 / 会删掉多少条」

        · `forget`：按 `memory_id` **只读反查**出这条记忆的正文摘要与类型 ——
          绝不回显模型传进来的字符串（它可能记错了 id，或者干脆是编的）
        · `clear`：分别统计该类型（或全部）当前有多少条

        失败**不允许**抛出 —— 循环层会兜住，但别依赖它。
        """
        action = str(params.get("action") or "")
        try:
            if action == "forget":
                return await self._preview_forget(params, ctx)
            if action == "clear":
                return await self._preview_clear(params, ctx)
        except Exception:  # noqa: BLE001 - 预览失败不影响主流程
            return {}
        return {}

    async def _preview_forget(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        memory_id = _to_int(params.get("memory_id"))
        if memory_id is None:
            return {}
        # 只读反查（走 ctx.db 没问题：get_memory 不写库、也不 commit）
        row = await memory_service.get_memory(ctx.db, ctx.user_id, memory_id)
        if row is None:
            return {
                "memoryId": memory_id,
                "content": "（没有找到这条记忆：可能已被删除，或者不属于你）",
            }
        text = row.content or ""
        return {
            "memoryId": row.id,
            "memoryType": row.memory_type,
            "memoryTypeText": _TYPE_TEXT.get(row.memory_type, row.memory_type),
            "content": text[:_PREVIEW_CHARS] + ("…" if len(text) > _PREVIEW_CHARS else ""),
        }

    async def _preview_clear(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        memory_type = self._normalize_type(params.get("memory_type"))
        if isinstance(memory_type, dict):  # fail 信封
            return {"memoryType": "（memory_type 取值不合法）"}
        counts = await memory_service.count_by_type(ctx.db, ctx.user_id)
        if memory_type == _ALL:
            return {
                "memoryType": "all",
                "memoryTypeText": "全部记忆",
                "count": sum(int(c or 0) for c in counts.values()),
            }
        return {
            "memoryType": memory_type,
            "memoryTypeText": _TYPE_TEXT.get(memory_type, memory_type),
            "count": int(counts.get(memory_type) or 0),
        }

    # ------------------------------------------------------------------

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        action = str(params.get("action") or "")
        if action == "list_types":
            return await self._list_types(ctx)
        if action == "forget":
            return await self._forget(params, ctx)
        if action == "clear":
            return await self._clear(params, ctx)
        return fail(
            f"未知操作: {action}",
            "action 只能是 list_types / forget / clear",
        )

    # ------------------------------------------------------------------

    async def _list_types(self, ctx: ToolContext) -> Dict[str, Any]:
        """各类记忆的条数 + 上限（只读）

        为什么值得一个 action：用户问「你都记得我什么」时，模型得先知道**有没有**记忆、
        哪一类多 —— 否则它只能瞎搜。也顺带把上限给出来，模型可以解释「满了会自动淘汰最旧的」。
        """
        counts = await memory_service.count_by_type(ctx.db, ctx.user_id)
        items: List[Dict[str, Any]] = []
        for memory_type in MEMORY_TYPES:
            items.append(
                {
                    "memoryType": memory_type,
                    "memoryTypeText": _TYPE_TEXT.get(memory_type, memory_type),
                    "count": int(counts.get(memory_type) or 0),
                    "limit": MAX_PER_TYPE.get(memory_type),
                }
            )
        total = sum(int(c or 0) for c in counts.values())
        if total:
            message = f"你共有 {total} 条记忆（" + "、".join(
                f"{i['memoryTypeText']} {i['count']} 条" for i in items
            ) + "）"
        else:
            message = "你还没有任何记忆记录"
        return ok(
            action="list_types",
            count=len(items),
            total=total,
            memoryTypes=items,
            message=message,
        )

    async def _forget(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        memory_id = _to_int(params.get("memory_id"))
        if memory_id is None:
            return fail(
                "删除记忆需要 memory_id",
                "请先用 memory_search 找到要忘记的那条记忆，再拿返回的 memoryId 重试",
            )

        from app.database import async_session_factory

        # ⚠️ 自己的一次性会话（理由见模块 docstring：memory_service 内部 commit，
        #    套在 _execute_tool 的 SAVEPOINT 里会「数据已删、却回失败」）
        async with async_session_factory() as db:
            deleted = await memory_service.delete_memory(db, ctx.user_id, memory_id)

        if not deleted:
            return fail(
                f"没有找到这条记忆：memory_id={memory_id}",
                "可能已被删除，或者不属于你。请先用 memory_search 确认 memoryId",
            )
        # ⚠️ 回执**不带正文**（见模块 docstring：带上就等于「删了又记回来」）
        return ok(
            action="forget",
            deleted=1,
            memoryId=memory_id,
            message=f"已忘记 1 条记忆（ID={memory_id}）",
        )

    async def _clear(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        memory_type = self._normalize_type(params.get("memory_type"))
        if isinstance(memory_type, dict):  # fail 信封
            return memory_type

        target = None if memory_type == _ALL else memory_type
        label = "全部" if target is None else _TYPE_TEXT.get(target, target)
        # ⚠️ `memoryTypeText` 必须给：`list_types`(L200) / `_preview_clear`(L167) 都有，
        #    只有 `_clear` 漏了 —— 用户点「清空记忆」时详情面板就会显示英文 `episodic`
        #    （前端 `AgentToolDetail` 的 REDUNDANT_KEYS 是「**有人话**才隐机器码」，
        #    没有人话时它**故意**保留原值，因为藏掉等于什么都不显示）。
        #    与 `_preview_clear` 取同一个词（「全部记忆」），确认卡片与结果卡片才一致；
        #    `label`（「全部」）只用于回执那句人话，两个词不必相同。
        type_text = "全部记忆" if target is None else _TYPE_TEXT.get(target, target)

        from app.database import async_session_factory

        async with async_session_factory() as db:
            # ⚠️ **执行前**把「将被删的 id」查出来：`clear` 是批量逻辑删，回执里只有条数，
            #    而回退必须知道具体撤哪几行。查询复用 `list_memories`（它本来就只回
            #    `del_flag='0'` 的行，与 `clear_memories` 的过滤逐条对齐：user_id +
            #    未删 + 可选 memory_type），不另写一份 SQL。
            pending = await memory_service.list_memories(
                db, ctx.user_id, memory_type=target, limit=_MAX_CLEAR_IDS
            )
            pending_ids = [int(r.id) for r in pending]
            deleted = await memory_service.clear_memories(db, ctx.user_id, target)

        if not deleted:
            return ok(
                action="clear",
                memoryType=memory_type,
                memoryTypeText=type_text,
                deleted=0,
                message=f"没有可清空的「{label}」记忆",
            )
        if int(deleted) > len(pending_ids):
            # 正常路径到不了这里（写入侧有配额淘汰，活跃行数 ≤ 两类上限之和）。
            # 真到了 = 有人绕过 `save_memory` 塞了超量行 → 那部分行回退不了，
            # 记一条 warning 留痕，不要静默地少恢复几条。
            logger.warning(
                "[agent] clear 实际删了 {} 条，但执行前只枚举到 {} 条（超配额写入？）",
                deleted,
                len(pending_ids),
            )
        payload: Dict[str, Any] = {
            "action": "clear",
            "memoryType": memory_type,
            "memoryTypeText": type_text,
            "deleted": deleted,
            "message": f"已清空 {deleted} 条「{label}」记忆",
        }
        if pending_ids:
            # 只给账本用（`_execute_tool` 摘走），不进回执
            payload[UNDO_BEFORE_KEY] = {"memoryIds": pending_ids}
        return ok(**payload)

    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_type(value: Any):
        """`clear` 的 memory_type 归一；非法时返回 `fail()` 信封"""
        raw = str(value or "").strip().lower()
        if not raw:
            return fail(
                "清空记忆需要 memory_type",
                "memory_type 只能是 episodic / conversation / all"
                "（只想清某一类时请明确写出，避免误清全部）",
            )
        if raw not in _CLEAR_TYPES:
            return fail(
                f"未知的记忆类型：{raw}",
                f"memory_type 只能是 {' / '.join(_CLEAR_TYPES)}",
            )
        return raw


def _to_int(value: Any):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = ["MemoryManageTool"]
