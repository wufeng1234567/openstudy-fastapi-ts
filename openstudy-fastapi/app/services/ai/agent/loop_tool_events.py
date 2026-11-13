"""Agent「模型自纠」事件的构造（从 `loop.py` 抽出）。

  · `tool_self_correction_event` —— 回灌工具失败结果后要下发的那条 `self_correct` 事件

⚠ 依赖方向单向：`loop.py` → 本模块 → `loop_events` / `loop_support`；
   那两个模块**都不反向依赖** `loop.py`，因此不会形成循环依赖。

⚠ **SSE 事件顺序、工具调用时序、确认 / 回滚顺序一个字节都没动** ——
   这里只是把「这条事件长什么样」挪到了可独立读、可独立测的地方；
   `state.corrections` 的自增**仍然留在调用点**，时序与原来逐字一致。
"""

from __future__ import annotations

from app.services.ai.agent.loop_events import self_correct_event
from app.services.ai.agent.loop_support import _event


def tool_self_correction_event(corrections: int, tool_name: str, reason: str) -> str:
    """「模型自纠」事件（`self_correct`）。

    ⚠️ `corrections` 必须是**已经 +1 之后**的计数 —— 事件里回显的「第几次自纠」
    要跟状态条上的计数一致。

    ⚠️ 这段（自增 + 事件）原本在**四处**逐字相同 —— 现在事件构造收敛到一处，
    四条链路的文案与字段形状不会再各自漂。
    """
    return _event(self_correct_event(corrections, tool_name, reason))
