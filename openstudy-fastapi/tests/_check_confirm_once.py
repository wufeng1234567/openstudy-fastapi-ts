# -*- coding: utf-8 -*-
"""探针：规模闸门类确认「本轮只问一次」。

背景（2026-10-17 用户报的 bug）：
    让智能体"导入 40 道题 + 写知识点入库"，它把 40 题拆成 15+14+11 三批，
    知识点又分几块写同一个知识库 —— 结果用户连点了 6 次「确认执行」。

根因：
    `question_manage.batch_import` 在 **≥5 题** 时强制确认、
    `knowledge_ingest.from_text` 在 **≥3000 字 / ≥8 块** 时强制确认。
    这些是「规模闸门」，每一批新参数都会重新命中 → 每批都弹一张卡。

期望行为（本探针固化）：
    · 同一轮内，用户对 `tool:action` 点过一次「确认」后，后续批次**不再追问**；
    · **破坏性操作（删除）不受影响**：仍然每次都问；
    · 用户关掉「自动执行」时，普通写操作仍然每次都问（那条路径与闸门无关）。

用法：.venv/Scripts/python.exe tests/_check_confirm_once.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.services.ai.agent.guard import GuardState  # noqa: E402
from app.services.ai.agent.loop import needs_user_confirmation  # noqa: E402


class _FakeTool:
    """最小假工具：needs_confirmation=True（写操作），confirm_policy 可配。"""

    name = "question_manage"

    def __init__(self, *, destructive: bool = False, size_gate: bool = True):
        self._destructive = destructive
        self._size_gate = size_gate

    def needs_confirmation(self, params):
        return True

    def is_destructive(self, params):
        return self._destructive

    def confirm_policy(self, params):
        return self._size_gate


def _batch(n: int) -> dict:
    """造一批 batch_import 参数（题数不同 → 参数不同 → 指纹不同）"""
    return {
        "action": "batch_import",
        "bank_id": 1230,
        "questions": [{"q": f"题目{i}"} for i in range(n)],
    }


def main() -> int:
    failures = []

    # ---- 场景 1：规模闸门，第一批要问 ----
    tool = _FakeTool()
    state = GuardState()
    first = needs_user_confirmation(tool, _batch(15), True, state)
    if not first:
        failures.append("第一批（15 题）应该要确认，实际没有")
    else:
        state.mark_confirmed(tool.name, "batch_import")

    # ---- 场景 2：后续批次（参数不同）不应再问 ----
    for n in (14, 11, 7):
        again = needs_user_confirmation(tool, _batch(n), True, state)
        if again:
            failures.append(f"已批准后，{n} 题那批仍要求确认（应该不再问）")

    # ---- 场景 3：破坏性操作必须每次问，哪怕已批准过 ----
    destr = _FakeTool(destructive=True)
    for i in range(3):
        need = needs_user_confirmation(destr, _batch(10), True, state)
        if not need:
            failures.append(f"破坏性操作第 {i + 1} 次没有要求确认（必须每次都问）")

    # ---- 场景 4：不同工具互不影响 ----
    other = _FakeTool()
    other.name = "knowledge_ingest"
    need_other = needs_user_confirmation(
        other, {"action": "from_text", "text": "x" * 4000}, True, state
    )
    if not need_other:
        failures.append("另一个工具（knowledge_ingest）不该被 question_manage 的批准放行")

    # ---- 场景 5：没有 state 时保持旧行为（保守，每次都问）----
    legacy = needs_user_confirmation(tool, _batch(15), True, None)
    if not legacy:
        failures.append("不传 state 时应保持旧行为（每次都问），实际被放行了")

    # ---- 场景 6：auto_confirm=False 时普通写操作仍要问 ----
    no_gate = _FakeTool(size_gate=False)
    need_when_off = needs_user_confirmation(no_gate, {"action": "create"}, False, state)
    if not need_when_off:
        failures.append("关掉自动执行时，普通写操作仍应确认")

    state2 = GuardState()
    state2.mark_confirmed("question_manage", "create")
    after_off = needs_user_confirmation(no_gate, {"action": "create"}, False, state2)
    if not after_off:
        failures.append("auto_confirm=False 的路径不应被 confirmed_writes 放行（它只作用于规模闸门）")

    if failures:
        print("失败项:")
        for f in failures:
            print(f"  ✗ {f}")
        return 1

    print("全部通过（6 个场景）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
