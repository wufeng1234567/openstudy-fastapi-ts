"""
`memory_search` —— 长期记忆检索工具（Agent 自封装，**只读**）

L1 注入（`memory_service.build_memory_context`）只往系统提示词塞最近几条，
解决的是「一眼就能想起来的背景」。但用户问「我上个月删掉的那个题库叫什么」时，
最近 5 条里未必有 —— 那就得让模型**主动去翻**。这个工具就是那个入口。

与 L1 的分工：
    L1 = 常驻的少量背景（省心，不用模型动手）
    L2 = 按需深挖（模型自己决定搜什么词、搜几类）

⚠️ 记忆正文是**过去某个时刻的**用户数据，不是当前状态。写操作类记忆可能已经
过期（用户后来又把题库改名了）。所以工具描述里明确要求：拿记忆当**线索**，
真正要读当前状态时回到 `bank_manage` / `question_manage` 去查。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.ai.agent.base import AgentTool, ToolContext, fail, ok
from app.services.ai.memory_service import (
    DEFAULT_SEARCH_LIMIT,
    MEMORY_TYPE_CONVERSATION,
    MEMORY_TYPE_EPISODIC,
)

#: 一次最多返回几条（超过这个数回灌进上下文就是噪声了）
MAX_LIMIT = 20

_MEMORY_TYPES = (MEMORY_TYPE_EPISODIC, MEMORY_TYPE_CONVERSATION)


class MemorySearchTool(AgentTool):
    name = "memory_search"
    #: ⚠️ 描述与参数说明一律英文（进系统提示词 `{{TOOLS}}` 与 Function Calling）
    description = (
        "Search what you remember about this user from EARLIER sessions: operations they "
        "performed (created/updated/deleted banks, notes, questions) and past conversation "
        "summaries. Use this when the user refers to something from before — "
        "'the bank I made last time', 'what did I delete', 'as we discussed earlier' — "
        "and the few notes already injected into your context are not enough. "
        "action values: search=find memories matching `query`, "
        "list=show the most important memories (optionally filtered by `memory_type`). "
        "NOTE: memories are POINTS IN TIME, not current state — treat them as clues and "
        "re-read the live data with `bank_manage` / `note_manage` / `question_manage` "
        "before acting on anything."
    )
    #: 界面专用（只给前端看；不进 definitions() / describe()）
    label = "记忆检索"
    description_zh = (
        "翻我之前记下的东西（你过去的操作、以前会话的摘要）："
        "search=按关键词搜、list=按类型列出来。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Operation to perform",
                "enum": ["search", "list"],
            },
            "query": {
                "type": "string",
                "description": (
                    "Keyword to look for inside past memories (used by search). "
                    "Match on the concrete noun the user mentioned, e.g. a bank name."
                ),
            },
            "memory_type": {
                "type": "string",
                "description": (
                    "Filter by kind: episodic=things the user did, "
                    "conversation=summaries of past chats. Omit for both."
                ),
                "enum": list(_MEMORY_TYPES),
            },
            "limit": {
                "type": "integer",
                "description": (
                    f"How many memories to return (default {DEFAULT_SEARCH_LIMIT}, max {MAX_LIMIT})."
                ),
            },
        },
        "required": ["action"],
    }
    #: 只读 —— 查记忆本身不该再产生一条新记忆
    write_operation = False

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        action = str(params.get("action") or "search")
        if action not in ("search", "list"):
            return fail(f"未知操作: {action}", "action 只能是 search / list")

        memory_type = self._memory_type(params)
        if isinstance(memory_type, dict):  # fail 信封
            return memory_type

        limit = params.get("limit")
        try:
            limit = int(limit) if limit is not None else DEFAULT_SEARCH_LIMIT
        except (TypeError, ValueError):
            limit = DEFAULT_SEARCH_LIMIT
        limit = max(1, min(MAX_LIMIT, limit))

        query = (params.get("query") or "").strip()
        if action == "search" and not query:
            return fail(
                "检索记忆需要提供 query",
                "请给出要回忆的关键词（例如题库名、操作类型）",
            )

        from app.services.ai import memory_service

        rows = await memory_service.list_memories(
            ctx.db,
            ctx.user_id,
            memory_type=memory_type,
            limit=limit,
            keyword=query or None,
        )

        items: List[Dict[str, Any]] = [
            {
                # memoryId 留着，便于用户说「把这条忘掉」时定点删除
                "memoryId": r.id,
                "memoryType": r.memory_type,
                "content": r.content,
                "importance": r.importance,
                "createTime": r.create_time.isoformat(sep=" ") if r.create_time else None,
            }
            for r in rows
        ]

        if not items:
            hint = (
                f"没有找到包含「{query}」的历史记忆。"
                if query
                else "这个用户还没有任何历史记忆。"
            )
            return ok(
                action=action,
                query=query or None,
                count=0,
                memories=[],
                message=hint + "请如实告知，不要编造过去发生过的事。",
            )

        # 带一句人话回执（工具卡片与 memory_hook 都用它；虽然只读不会被记）
        if query:
            message = f"找到 {len(items)} 条与「{query}」相关的历史记忆"
        else:
            message = f"找到 {len(items)} 条历史记忆"
        return ok(
            action=action,
            query=query or None,
            count=len(items),
            memories=items,
            message=message,
            note=(
                "这些是**过去某个时刻**的记录，可能已经过期。"
                "要确认现状请用相应工具重新查询，不要直接断言当前状态。"
            ),
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _memory_type(params: Dict[str, Any]) -> Optional[str] | Dict[str, Any]:
        value = (params.get("memory_type") or "").strip().lower()
        if not value:
            return None
        if value not in _MEMORY_TYPES:
            return fail(
                f"未知的记忆类型：{value}",
                f"memory_type 只能是 {' / '.join(_MEMORY_TYPES)}",
            )
        return value


__all__ = ["MemorySearchTool"]
