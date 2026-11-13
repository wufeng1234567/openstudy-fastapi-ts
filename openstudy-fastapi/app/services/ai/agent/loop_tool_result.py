"""Agent 工具结果的**回灌消息**（从 `loop.py` 抽出）。

  · `tool_result_message` —— 把工具结果包成回灌给模型的那条 `ToolMessage`

⚠ 依赖方向单向：`loop.py` → 本模块；本模块**不反向依赖**它
   （`loop_helpers` 无项目级回引），因此不会形成循环依赖。

⚠ **工具调用时序、确认 / 回滚 / 事件顺序一个字节都没动** —— 这里只把
   「回灌消息长什么样」挪到了可独立读、可独立测的地方；发事件的时机、
   自纠计数的先后、`lc_messages` 的追加位置全部原样保留。
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import ToolMessage

from app.services.ai.agent.loop_helpers import dumps as _dumps


def tool_result_message(result: Any, call_id: str) -> ToolMessage:
    """把工具结果回灌给模型的一条 `ToolMessage`。

    ⚠️ `tool_call_id` 必须与模型发起这次调用时的 id **逐字一致** ——
       对不上，模型就收不到这条结果（这一轮的上下文就断了）。

    ⚠️ 这段构造原本在**五处**逐字相同（工具不存在 / 角色外工具 / 参数校验不过 /
       死循环提示 / 委派回填）—— 现在收敛到一处，回灌口径不会再各处漂。
    """
    return ToolMessage(content=_dumps(result), tool_call_id=call_id)
