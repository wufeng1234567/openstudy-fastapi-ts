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

import re
from typing import Any, Dict, List, Optional

from loguru import logger

from app.services.ai.agent.base import ToolContext
from app.services.ai.agent.registry import registry


#: 子代理内层循环的最大「模型→工具」往返数（比指挥家小：子代理任务更聚焦）
SUB_AGENT_MAX_LOOPS = 6

#: 「模型没走 Function Calling、而是把工具调用**写成了文本**」时最多纠正几次
SUB_AGENT_FORMAT_FIX_LIMIT = 2

#: 检测「文本形式的工具调用尝试」用的正则（与前端 `agentDsFree.ts` 的 `looksLikeToolCallAttempt` 对齐）。
#:
#: 为什么要检测：子代理用的是指挥家同一个模型（可能是不支持/弱支持 Function Calling 的
#: ds-free 反代或某模型），当它**把调用写成文本**（`<|DSML|>` / `<invoke name="...">` /
#: 围栏 JSON / 裸 JSON）时，LangChain 的 `ai.tool_calls` 为空 —— 若直接把 `ai.content`
#: 当「子代理最终产出」返回，指挥家就会把这段**原始协议文本**当结果回报给用户
#: （用户 2026-10-10 报的「知识库/题库创建失败」真因：子代理从没真正执行工具，只吐了协议文本）。
#: ⚠️ 只认**标记形状**（带尖括号）——正文里光出现 `tool_call`/`DSML` 这些词不算。
_SUB_AGENT_PROTOCOL_PATTERNS = (
    re.compile(r"<[=/\s]*tool_calls?\b", re.IGNORECASE),
    # DSML：这是 DeepSeek 网页端的工具语法标记，正常学习对话里几乎不会出现 `DSML` 这个词，
    # 故只要出现（大小写不敏感）即判为协议文本尝试 —— 容忍半角/全角尖括号与竖线的各种变体
    # （用户 2026-10-10 记录里是 `＜｜｜DSML｜｜ invoke ...＞` 这类全角形态）。
    re.compile(r"DSML", re.IGNORECASE),
    re.compile(r"<\s*invoke\b", re.IGNORECASE),
    re.compile(r"<\s*parameter\b", re.IGNORECASE),
)


def _looks_like_tool_protocol(text: str) -> bool:
    """子代理的文本产出是否**像一次工具调用尝试**（DSML / invoke / 围栏 JSON / 裸 JSON）

    与前端 ds-free 的 `looksLikeToolCallAttempt` 同口径（子代理产出的文本不该被当成结论）。
    命中即认为"模型没走 Function Calling、把调用写成了文本"——须纠正重试，绝不能当最终产出。
    """
    if not text:
        return False
    for pat in _SUB_AGENT_PROTOCOL_PATTERNS:
        if pat.search(text):
            return True
    # 围栏代码块里的 tool+action JSON（成对或未闭合）
    fence = re.search(r"(?:```|~~~)([\s\S]*?)(?:```|~~~)", text)
    if fence and _has_tool_action_keys(fence.group(1)):
        return True
    at = max(text.rfind("```"), text.rfind("~~~"))
    if at >= 0 and _has_tool_action_keys(text[at + 3:]):
        return True
    # 裸 tool+action JSON（正文里引用示例不算：要求整段文本里同时出现两个键即可，从严不够的
    # 情况宁可多纠正一次 —— 子代理产出协议文本本就是异常）
    return _has_tool_action_keys(text)


def _has_tool_action_keys(s: str) -> bool:
    """文本里是否同时出现 `"tool"` 与 `"action"`/`"name"` 之类的调用键"""
    return bool(
        re.search(r"[\"'](?:tool|name)[\"']\s*:", s)
        and re.search(r"[\"'](?:action|args|parameters|arguments)[\"']\s*:", s)
    )


#: 模型吐了协议文本时的纠正提示（回灌给子代理，要求它改用**真正的工具调用**）
_SUB_AGENT_FORMAT_FIX = (
    "Your previous message contained tool-call syntax as PLAIN TEXT (e.g. DSML / <invoke> / "
    "a raw JSON block). That did NOT execute anything. If you need a tool, call it through the "
    "normal function-calling mechanism; do NOT print the call as text. If you already have the "
    "answer, just reply with the plain-text result."
)


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
    #: 「模型吐了协议文本、已纠正」的次数（超过 `SUB_AGENT_FORMAT_FIX_LIMIT` 就放弃）
    format_fix_streak = 0

    for _ in range(max(1, int(max_loops))):
        try:
            ai = await bound.ainvoke(messages)
        except Exception as e:  # noqa: BLE001 - 子代理失败要带回给指挥家，不抛
            logger.warning("[sub_agent:{}] LLM 调用失败: {}", role_spec.key, e)
            return {"success": False, "text": "", "steps": steps, "error": str(e)}

        tool_calls = getattr(ai, "tool_calls", None) or []
        messages.append(ai)

        if not tool_calls:
            text = _content_to_text(getattr(ai, "content", ""))
            # ⚠️ 关键兜底：模型**没走 Function Calling**、把工具调用**写成了文本**
            #    （DSML / <invoke> / 围栏 JSON）时，`tool_calls` 会是空 —— 若把这段文本
            #    当「子代理的产出」返回，指挥家就会原样回报给用户（用户 2026-10-10 报的
            #    「知识库/题库创建失败」就是这个：子代理从没真正执行工具）。故检测并纠正。
            if _looks_like_tool_protocol(text):
                format_fix_streak += 1
                if format_fix_streak <= SUB_AGENT_FORMAT_FIX_LIMIT:
                    logger.warning(
                        "[sub_agent:{}] 模型吐了工具协议文本，回灌纠正（第 {} 次）",
                        role_spec.key, format_fix_streak,
                    )
                    messages.append(HumanMessage(content=_SUB_AGENT_FORMAT_FIX))
                    continue
                # 纠正多次仍不改 → 明确失败（绝不把协议文本当结论交回指挥家）
                logger.warning("[sub_agent:{}] 连续 {} 次吐协议文本，放弃", role_spec.key, format_fix_streak)
                return {
                    "success": False,
                    "text": "",
                    "steps": steps,
                    "error": "子代理模型未能按工具协议输出（多次把工具调用写成了纯文本），任务未执行",
                }
            # 正常文本 = 子代理的最终产出
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
