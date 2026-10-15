"""
工具执行 → 长期记忆 的挂钩

在 `_execute_tool` 这个**唯一收口**里调用，所以 api 付费链路的主循环与
ds-free 的单步执行（`/ai/agent/execute`）都会自动记上，不用两边各写一遍。

哪些操作会被记住
----------------
由**工具自己**声明，不在这里另抄一份规则：
  · `tool.write_operation` 为真（这工具可能写库）
  · `tool.needs_confirmation(params)` 为真（**这个 action** 是写操作 ——
    工具用自己那份 `_WRITE_ACTIONS` 判定，比如 list/detail 不算）
  · 结果信封 `success` 不为 False（失败的写操作没有记住的价值）
读操作**刻意不记** —— 记下来只会把真正有用的「做过什么」淹没在噪声里。

记忆内容从哪来
--------------
优先用工具既有的 `message` 字段（按红线「工具只做参数校验 + 人话回执」，
它本来就是给人看的，如「题库「X」创建成功（ID=1）」）—— 零重复、
且与用户当时看到的回执完全一致。没有 message 时退回一句兜底描述。

⚠️ **失败绝不抛** —— 记忆是增强项，记不上不该让用户的这一次操作失败。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from loguru import logger

from app.models.agent_memory import (
    MEMORY_TYPE_EPISODIC,
)
from app.services.ai import memory_service
from app.services.ai.agent.base import AgentTool

#: 工具名 → 中文名（只用于兜底描述，正常路径用工具的 message）
_TOOL_LABELS = {
    "bank_manage": "题库",
    "note_manage": "笔记",
    "question_manage": "题目",
    "memory_manage": "记忆",
    # 错题本 / 收藏 / 斩题是同一个工具（`flag_type` 区分）——兜底描述只能给一个中性名，
    # 正常路径用的是工具自己的 `message`（里面写清了是哪个列表）
    "question_flag_manage": "题目标记",
    "knowledge_base_manage": "知识库",
    "bank_share_manage": "题库分享",
}

#: 删除类操作的 importance 更高（用户更可能回头问「我删的那个是什么」）
_DESTRUCTIVE_IMPORTANCE = memory_service.IMPORTANCE_DELETE
_WRITE_IMPORTANCE = memory_service.IMPORTANCE_WRITE


def should_remember(tool: AgentTool, params: Dict[str, Any], result: Any) -> bool:
    """这次调用该不该记进长期记忆。"""
    if not getattr(tool, "write_operation", False):
        return False
    if not isinstance(result, dict) or result.get("success") is False:
        return False
    try:
        if not tool.needs_confirmation(params):
            return False
    except Exception:  # pragma: no cover - 工具实现异常时保守不记
        return False
    return True


def build_memory_text(
    tool: AgentTool, params: Dict[str, Any], result: Dict[str, Any]
) -> Optional[str]:
    """拼出记忆正文。优先复用工具给的人话回执。"""
    message = (result.get("message") or "").strip()
    if message:
        return message

    label = _TOOL_LABELS.get(tool.name, tool.name)
    action = str(params.get("action") or "").strip()
    if action:
        return f"对{label}执行了 {action} 操作"
    return f"使用了{label}"


async def record_tool_memory(
    user_id: int,
    tool: AgentTool,
    params: Dict[str, Any],
    result: Any,
) -> None:
    """写操作成功后落一条 episodic 记忆。

    **永不抛异常** —— 记忆失败不能影响用户的这次操作。

    ⚠️⚠️ **用自己的一次性会话，绝不借用调用方的事务**。
    早先的写法是 `async with db.begin_nested(): await save_memory(db, ...)`，
    看起来「包了 SAVEPOINT 就不会污染外层」，但那层保护是**假的**：
    `memory_service.save_memory` 内部自己会 `commit()` + `refresh()`，
    而 `commit()` 在 SAVEPOINT 里会把**整个事务**一并提交掉，
    紧接着的 `refresh()` 又新开一个事务 —— 于是退出 `begin_nested()` 时，
    它要关闭的那个嵌套事务早就失效了，抛：

        Can't operate on closed transaction inside context manager.
        Please complete the context manager before emitting further commands.

    实测（`tests/_probe_nested_tx.py` 复现）：记忆**确实写进去了**，
    但**每一次写操作都刷一条这样的 warning**，而且 SAVEPOINT 完全没起到隔离作用。
    改用独立会话后两个问题一起消失，也和 `runtime_context` 的做法一致 ——
    「增强项不要寄生在别人的事务里」。
    """
    if user_id <= 0:
        return
    try:
        if not should_remember(tool, params, result):
            return
        text = build_memory_text(tool, params, result)
        if not text:
            return

        destructive = False
        try:
            destructive = tool.is_destructive(params)
        except Exception:  # pragma: no cover
            destructive = False

        # 延迟 import：本模块在 Agent 循环的 import 链上，顶层 import 容易踩循环依赖
        from app.database import async_session_factory

        async with async_session_factory() as db:
            await memory_service.save_episodic(
                db,
                user_id,
                text,
                tool=tool.name,
                params={k: v for k, v in (params or {}).items() if k != "action"},
                importance=_DESTRUCTIVE_IMPORTANCE if destructive else _WRITE_IMPORTANCE,
            )
        logger.debug("[memory] 已记录：{}", text)
    except Exception as e:  # noqa: BLE001 - 记忆是增强项，失败只记日志
        logger.warning("[memory] 记录失败（已忽略，不影响本次操作）: {}", e)


__all__ = [
    "MEMORY_TYPE_EPISODIC",
    "build_memory_text",
    "record_tool_memory",
    "should_remember",
]
