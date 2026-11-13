"""Agent SSE 事件载荷的**纯构造**（从 `loop.py` 抽出）。

这里的函数只回答「这条事件长什么样」——**不碰状态、不发事件、不排事件顺序**：

  · `error_event` / `warning_event` / `waiting_event` —— 纯消息类事件
  · `text_event` / `thinking_event` —— 模型正文 / 推理增量
  · `self_correct_event` —— 模型正在自我纠正
  · `tool_start_event` / `tool_result_event` / `tool_result_cancelled_event`
    —— 工具调用的生命周期事件

⚠️ 依赖方向单向：`loop.py` → 本模块；本模块**不反向依赖** `loop.py`，
   因此不会形成循环依赖。

⚠️ **事件契约一个字段都没改**：`type` 与各载荷字段的名字、取值、字典键顺序
   都与原来内联的 dict **逐字一致** —— 前端 `api/ai/agent.ts` 按这些字段渲染，
   改名字就等于改契约。事件之间的**先后顺序**也没动（`yield` 的位置原样保留）。
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def error_event(message: str) -> Dict[str, Any]:
    """致命错误 —— 本轮结束。"""
    return {"type": "error", "message": message}


def text_event(content: str) -> Dict[str, Any]:
    """模型正文增量（可能是工具调用前的引子）。"""
    return {"type": "text", "content": content}


def thinking_event(content: str) -> Dict[str, Any]:
    """模型深度思考的推理正文增量。"""
    return {"type": "thinking", "content": content}


def warning_event(message: str) -> Dict[str, Any]:
    """非致命问题（死循环警告 / 图片丢失 / 轮数用尽 / 删除合并提示）。"""
    return {"type": "warning", "message": message}


def waiting_event(message: str) -> Dict[str, Any]:
    """等待提示（每轮模型调用开始前 / 收尾整理执行结果时）。"""
    return {"type": "waiting", "message": message}


def self_correct_event(attempt: int, tool: str, reason: str) -> Dict[str, Any]:
    """模型正在自我纠正（参数非法或工具报错后重试）。"""
    return {"type": "self_correct", "attempt": attempt, "tool": tool, "reason": reason}


def tool_start_event(
    tool: str,
    action: Optional[str],
    message: str,
    params: Any,
    preview: Optional[Dict[str, Any]],
    needs_confirmation: bool,
) -> Dict[str, Any]:
    """工具开始执行。

    ⚠️ `params` 必须传**已脱敏**的那份（`_safe_params`）—— 前端会把整段参数显示出来。
    """
    return {
        "type": "tool_start",
        "tool": tool,
        "action": action,
        "message": message,
        "params": params,
        "preview": preview,
        "needsConfirmation": needs_confirmation,
    }


def tool_result_event(
    tool: str,
    action: Optional[str],
    success: bool,
    message: str,
    data: Any,
) -> Dict[str, Any]:
    """工具执行完毕（成功 / 失败）。"""
    return {
        "type": "tool_result",
        "tool": tool,
        "action": action,
        "success": success,
        "message": message,
        "data": data,
    }


def tool_result_cancelled_event(
    tool: str,
    action: Optional[str],
    message: str,
) -> Dict[str, Any]:
    """用户取消的工具结果事件。

    ⚠️ 取消**不是失败**：文案中性、`data=None`（没有 fail 信封 → 前端不会去渲染
       那份空的「执行结果」）。前端据此渲染成中性卡片而不是红色失败卡片。
    """
    return {
        "type": "tool_result",
        "tool": tool,
        "action": action,
        "success": False,
        "cancelled": True,
        "message": message,
        "data": None,
    }
