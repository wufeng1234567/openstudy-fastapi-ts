"""
子代理执行器 —— 指挥家把任务派给某个子代理时，在这里跑一个**精简 ReAct 循环**

在「指挥家 + 子代理」架构里（见 `docs/fastapi_v2_指挥家模式方案.md`）：

  · **指挥家** = `loop.run_agent_stream`（面向用户、掌握子代理通讯录、可委派）；
  · **子代理** = 本模块 `run_sub_agent(...)`（后台工作者，**不直接面向用户**）。

⚠️ 为什么子代理**不复用** `run_agent_stream`
==========================================
`run_agent_stream` 是"面向用户的一整轮"：发 SSE 事件、写会话历史、落库、触发记忆钩子、
管 L1 注入……子代理是**内部一次调用**，不需要这些，复用反而会：
  · 把子代理的中间过程也流给用户（违背"隔绝子代理与用户通信"）；
  · 往会话历史里塞进内部任务文本（污染用户可见的历史）。

所以本模块是**自包含的精简循环**：一个 LLM + 子代理的窄工具，跑到"不再调工具"为止，
把最终文字返回给指挥家。

⚠️ 子代理**不挂委派工具**（只挂自己的业务工具）
============================================
从根上杜绝"子代理再委派"的递归。委派只有指挥家能做。

⚠️ 写操作的收口仍走 `loop._execute_tool`
======================================
工具的 SAVEPOINT、异常转 fail 信封、写操作记忆钩子，全部复用 `loop._execute_tool` ——
它是"api 主循环与 ds-free 单步执行唯一的收口"（见其 docstring）。子代理直接调它，
行为与主循环一致，不再重造。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from loguru import logger

from app.services.ai.agent.base import ToolContext
from app.services.ai.agent.registry import registry


#: 子代理内层循环的最大「模型→工具」往返数（比指挥家小：子代理任务更聚焦）
SUB_AGENT_MAX_LOOPS = 6


async def run_sub_agent(
    db: Any,
    *,
    user_id: int,
    session_id: Optional[str] = None,
    role_spec: Any,
    task: str,
    llm: Any,
    excluded_tools: Optional[set] = None,
    max_loops: int = SUB_AGENT_MAX_LOOPS,
    extra: Optional[Dict[str, Any]] = None,
    own_session: bool = False,
) -> Dict[str, Any]:
    """跑一个子代理，返回 `{"success", "text", "steps"}`

    Args:
        db: 数据库会话。传 `None` 时**本函数自己开一个独立会话**（见 `own_session`）。
        user_id: 归属用户（子代理的工具只碰这个用户的数据）。
        session_id: 会话 id（透传给工具 ctx）。
        role_spec: 子代理的 `RoleSpec`（用 `persona` 作系统提示词、`tools` 作白名单）。
        task: 指挥家整理好的**自包含子任务描述**（子代理的"用户消息"）。
        llm: 已构造好的 LLM 客户端（指挥家传下来，避免重复构造/重复解析模型）。
        excluded_tools: 已算好的排除集（= 全部 − 子代理白名单 ∪ 用户屏蔽）。
                        传 None 时由本函数按 `role_spec.tools ∪ GLOBAL_TOOLS` 现算。
        max_loops: 内层最大往返数。
        extra: 追加到子代理 ToolContext.extra 的键（如 attachments）。
        own_session: **是否让本子代理用独立数据库会话**。
            · `True`（并发委派时必须）：子代理自己开一个 `async_session_factory` 会话，
              并在每次**写操作**后 `commit()` —— 因为 asyncpg 单连接**不能并发**，
              多个子代理共用指挥家的同一个会话会撞（`begin_nested` SAVEPOINT 冲突 /
              连接被并发复用）。独立会话 = 独立连接，天然支持并行。
            · `False`（默认，串行委派）：沿用传入的 `db`，写操作由指挥家主循环统一 commit
              （保证回退账本与数据同源）。此时 `db` 不能为 None。
            ⚠️ 并发（`own_session=True`）时，子代理的写操作**自行提交**、其回退账本记在
              自己的事务里 —— 与指挥家主事务不再同源。这是"真并行"的必然代价：
              并行子任务无法共享一个 SAVEPOINT。需要"整轮可回退"的场景应走串行委派。

    Returns:
        {"success": bool, "text": str, "steps": [工具名...], "error": str|None}
    """
    from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

    from app.services.ai.agent import orchestrator
    from app.services.ai.agent import loop as loop_mod

    # 0) 独立会话：并发委派时每个子代理各开一个连接（见 own_session 说明）
    db_session = None
    if own_session or db is None:
        from app.database import async_session_factory

        db_session = async_session_factory()
        db = await db_session.__aenter__()

    try:
        return await _run_sub_agent_inner(
            db,
            user_id=user_id,
            session_id=session_id,
            role_spec=role_spec,
            task=task,
            llm=llm,
            excluded_tools=excluded_tools,
            max_loops=max_loops,
            extra=extra,
            commit_writes=own_session or db_session is not None,
        )
    finally:
        if db_session is not None:
            await db_session.__aexit__(None, None, None)


async def _run_sub_agent_inner(
    db: Any,
    *,
    user_id: int,
    session_id: Optional[str],
    role_spec: Any,
    task: str,
    llm: Any,
    excluded_tools: Optional[set],
    max_loops: int,
    extra: Optional[Dict[str, Any]],
    commit_writes: bool,
) -> Dict[str, Any]:
    """子代理内层循环的实体（`run_sub_agent` 负责会话生命周期，这里只管跑）"""
    from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

    from app.services.ai.agent import orchestrator
    from app.services.ai.agent import loop as loop_mod

    # 1) 子代理工具集：白名单 ∪ 全局工具，再扣用户屏蔽
    if excluded_tools is None:
        excluded_tools = orchestrator.compute_exclude(
            role_spec,
            all_tool_names=registry.names(),
            user_disabled=set(),
        )
    tool_defs = registry.definitions(exclude=sorted(excluded_tools))

    # 2) 子代理系统提示词：persona 优先，回退 prompt_fragment，再回退一句通用说明
    persona = (role_spec.persona or role_spec.prompt_fragment or "").strip()
    system_text = (
        (persona + "\n\n") if persona else ""
    ) + _SUB_AGENT_BASE_RULES

    ctx = ToolContext(
        db=db,
        user_id=user_id,
        session_id=session_id or None,
        extra={**(extra or {}), "sub_agent": role_spec.key},
    )

    messages: List[Any] = [
        SystemMessage(content=system_text),
        HumanMessage(content=task or ""),
    ]

    bound = llm if not tool_defs else llm.bind_tools(tool_defs)
    steps: List[str] = []

    for _ in range(max(1, int(max_loops))):
        try:
            ai = await bound.ainvoke(messages)
        except Exception as e:  # noqa: BLE001 - 子代理失败要带回给指挥家，不抛
            logger.warning("[sub_agent:{}] LLM 调用失败: {}", role_spec.key, e)
            return {"success": False, "text": "", "steps": steps, "error": str(e)}

        tool_calls = getattr(ai, "tool_calls", None) or []
        messages.append(ai)

        if not tool_calls:
            # 不再调工具 → 这就是子代理的最终产出
            text = _content_to_text(getattr(ai, "content", ""))
            return {"success": True, "text": text, "steps": steps, "error": None}

        for tc in tool_calls:
            name = str((tc or {}).get("name") or "")
            params = dict((tc or {}).get("args") or {})
            call_id = (tc or {}).get("id") or ""
            tool = registry.get(name)
            if tool is None or name in excluded_tools:
                # 子代理不该调这个工具（不在白名单 / 不存在）→ 回灌失败让它改用别的
                result = {
                    "success": False,
                    "error": f"工具 {name} 不在当前子代理「{role_spec.name}」的可用范围内",
                    "hint": "请改用你可用的工具，或直接给出结论",
                }
            else:
                steps.append(name)
                result = await loop_mod._execute_tool(tool, params, ctx)
                # 独立会话：写操作必须自己提交（本会话没有外层主循环的统一 commit，
                # 关会话时会回滚未提交的写）—— 见 run_sub_agent 的 own_session 说明
                if commit_writes and tool.write_operation and result.get("success"):
                    try:
                        await db.commit()
                    except Exception as e:  # noqa: BLE001 - 提交失败不影响子代理给出结论
                        logger.warning("[sub_agent:{}] 写操作提交失败: {}", role_spec.key, e)
            messages.append(
                ToolMessage(content=_dumps(result), tool_call_id=call_id)
            )

    # 往返用尽：让它做个收尾（不带工具），拿一段总结
    try:
        tail = await llm.ainvoke(
            messages + [HumanMessage(content=_SUB_AGENT_WRAPUP)]
        )
        text = _content_to_text(getattr(tail, "content", ""))
    except Exception as e:  # noqa: BLE001
        logger.warning("[sub_agent:{}] 收尾调用失败: {}", role_spec.key, e)
        text = ""
    return {"success": True, "text": text, "steps": steps, "error": None}


#: 子代理的通用基础规则（英文，追加在 persona 之后）
_SUB_AGENT_BASE_RULES = (
    "## Working Rules\n"
    "- You are a background specialist. Your output goes back to the main assistant, "
    "NOT directly to the user.\n"
    "- Do exactly the task you were given with YOUR tools. If the task is outside your "
    "tools, say so in your result and stop.\n"
    "- Never fabricate results: only report what your tool calls actually returned.\n"
    "- When done, reply with a concise, factual summary of what you did/found "
    "(plain text, no meta-commentary)."
)

#: 往返用尽时的收尾指令
_SUB_AGENT_WRAPUP = (
    "You have reached the step limit. Reply now with a concise summary of what was "
    "actually done/found so far. Do not call any more tools."
)


def _content_to_text(content: Any) -> str:
    """把 LangChain 的 content（str 或多模态块列表）拍平成纯文本"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "".join(parts)
    return str(content or "")


def _dumps(obj: Any) -> str:
    """工具结果 → 字符串（与 loop 同口径：紧凑 JSON，中文不转义）"""
    import json

    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        return str(obj)


__all__ = ["run_sub_agent", "SUB_AGENT_MAX_LOOPS"]
