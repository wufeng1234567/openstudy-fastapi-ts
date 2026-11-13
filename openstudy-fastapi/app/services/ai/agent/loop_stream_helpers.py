"""Agent 流式循环的**纯辅助**（从 `loop.py` 抽出）。

这里放的是循环用到的、**不碰状态**的小工具：

  · **`_resolve_turn_id`** —— 本轮对话 id（缺省兜一个 `auto_<hex>`）
  · **`_read_decision`** —— 把确认决定读成 `(approved, edited)`（容忍旧格式）
  · **`_disabled_fail`** —— 工具被用户屏蔽时的**统一失败信封**
  · **`_async_empty_list`** —— `asyncio.gather` 的占位 awaitable
  · **`build_human_text`** —— 用户消息正文（标签包裹，明确「这是数据不是指令」）
  · **`build_vision_blocks`** —— 多模态组块（正文 + 图片 data URL）

⚠️ 依赖方向单向：`loop.py` → 本模块；本模块**不反向依赖** `loop.py`
   （`loop_support` / `base` 均无对 `loop` 的回引），因此不会形成循环依赖。

⚠️ **流式循环与事件顺序一个字节都没动**：这些函数只被调用、不改变任何时序；
   工具调用时序、确认 / 回滚的先后、事件的先后与载荷形状全部保持原样。

⚠️ `loop.py` 侧照旧把这些名字 import 回来 → **`loop._resolve_turn_id` 等
   既有引用照旧可用**（`tests/_probe_rollback_turn.py` 就是按 `loop._resolve_turn_id`
   取值的）。
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.services.ai.agent.base import fail
from app.services.ai.agent.loop_support import (
    TAG_ATTACHMENTS,
    TAG_USER_REQUEST,
    _wrap_tag,
)


def _resolve_turn_id(value: Optional[str]) -> str:
    """本轮对话 id：优先用前端带上来的，缺省时兜一个 `auto_<hex>`。

    ⚠️ 为什么不「干脆不记」：账本行的 `turn_id` 是回退的唯一取数键，空值既取不出来，
    又**绝对不许**当通配符（空串会把整个会话的行扫进来一起撤）。
    api 付费链路「一次请求 = 一轮」（轮边界 = 前端一次 `runStream`），所以兜底的
    「一次请求一个 id」**恰好等于正确粒度**；ds-free 是一轮里多次请求共用 turnId，
    没带上时兜底会退化成「一次工具调用一个 turn_id」—— 属于**安全退化**
    （回退按钮那一轮只能退回最后一次调用，而不是扫进整轮）。前端接上 `turnId` 后即恢复。
    """
    text = str(value or "").strip()
    if text:
        return text[:64]
    return f"auto_{uuid.uuid4().hex[:12]}"


def _async_empty_list() -> Any:
    """一个「立即完成、返回空列表」的 awaitable —— 供 `asyncio.gather` 占位用。

    指挥家模式才需要读用户智能体通讯录；非指挥家模式下用它在 gather 里占位，
    保持两个分支的代码结构一致（避免 if/else 各写一遍 gather）。
    """

    async def _inner() -> List[Any]:
        return []

    return _inner()


def _disabled_fail(tool_name: str) -> Dict[str, Any]:
    """工具被用户屏蔽时的**统一失败信封**（执行侧两处出口共用一份文案）。

    为什么要一个函数而不是各写一遍：`_prepare_tool_call`（ds-free 的 execute / preview）
    与 `run_agent_stream` 的内联分支是两条独立代码路径，文案一旦各写一份就会漂 ——
    而这段文字会**直接显示给用户**，也会原样回灌给模型。

    `hint` 是必需的（见 backend-ai-chain 红线）：没有它，模型会以为是自己参数写错了，
    拿同一组参数反复重试，白烧轮数。这里的 hint 明确说「是用户关掉的、别再调了」。
    """
    return fail(
        f"「{tool_name}」已被用户在工具设置里屏蔽",
        "用户明确屏蔽了这个工具，请不要再次调用它，直接用现有工具或直接回答",
    )


def _read_decision(decision: Any) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """把 `_pending_decisions` 里存的决定读成 `(approved, edited)`（容忍旧格式）"""
    if isinstance(decision, dict):
        return bool(decision.get("approved")), decision.get("edited")
    return bool(decision), None


def build_human_text(context: str, typed: str, file_text: str) -> str:
    """用户消息正文：标签包裹，明确「这是数据不是指令」

    顺序固定：**历史上下文 → 用户请求 → 附件正文**，用空行分隔。
    """
    human_parts: List[str] = []
    if context:
        human_parts.append(context)
    human_parts.append(_wrap_tag(TAG_USER_REQUEST, typed))
    if file_text:
        human_parts.append(_wrap_tag(TAG_ATTACHMENTS, file_text))
    return "\n\n".join(human_parts)


def build_vision_blocks(human_text: str, vision_images: List[str]) -> List[Any]:
    """多模态组块：正文 + 图片

    ⚠️ 图片必须是 **data URL**（`data:image/...;base64,`）或绝对 URL ——
    OpenAI 兼容多模态端点只接受这两种，相对路径（`/profile/upload/...`）
    会直接 400（`Unsupported image_url format`）。
    """
    blocks: List[Any] = [{"type": "text", "text": human_text}]
    for url in vision_images:
        blocks.append({"type": "image_url", "image_url": {"url": url}})
    return blocks
