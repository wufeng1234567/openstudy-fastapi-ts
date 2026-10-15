"""
上下文档位（context_budget）单元测试

覆盖：
  1. 档位清单：默认 200K、1M 可选
  2. 归一化：合法值原样、旧值(32k/128k)/空值/未知值 → 默认档
  3. 预算换算：1M 的预算严格大于 200K
  4. 与 conversation_service 的对接：build_context_prompt 能按档位截断

用法：
    ./.venv/Scripts/python.exe tests/test_context_budget.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ai import context_budget as cb  # noqa: E402


class Checker:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        if ok:
            self.passed += 1
            print(f"  [PASS] {name}" + (f" -> {detail}" if detail else ""))
        else:
            self.failed += 1
            print(f"  [FAIL] {name}" + (f" -> {detail}" if detail else ""))


def main() -> int:
    c = Checker()

    print("\n=== 1. 档位清单 ===")
    opts = cb.preset_options()
    keys = [o["key"] for o in opts]
    c.check("提供 200k / 1m 两档", keys == ["200k", "1m"], str(keys))
    c.check("默认档是 200k", cb.DEFAULT_CONTEXT_LENGTH == "200k", cb.DEFAULT_CONTEXT_LENGTH)
    c.check("清单里含默认档", cb.DEFAULT_CONTEXT_LENGTH in keys)
    c.check("1M 档 token 为 1000000", cb.CONTEXT_PRESETS["1m"].tokens == 1_000_000)
    c.check("200K 档 token 为 200000", cb.CONTEXT_PRESETS["200k"].tokens == 200_000)

    print("\n=== 2. 归一化 ===")
    c.check("合法值 200k", cb.normalize_context_length("200k") == "200k")
    c.check("合法值 1m", cb.normalize_context_length("1m") == "1m")
    c.check("大小写/空白不敏感", cb.normalize_context_length("  1M ") == "1m")
    c.check("旧值 32k → 默认", cb.normalize_context_length("32k") == "200k")
    c.check("旧值 128k → 默认", cb.normalize_context_length("128k") == "200k")
    c.check("空值 → 默认", cb.normalize_context_length(None) == "200k")
    c.check("未知值 → 默认", cb.normalize_context_length("bogus") == "200k")

    print("\n=== 3. 预算换算 ===")
    c.check(
        "1M 的历史预算 > 200K 的",
        cb.history_char_budget("1m") > cb.history_char_budget("200k"),
        f"{cb.history_char_budget('1m')} > {cb.history_char_budget('200k')}",
    )
    c.check(
        "1M 的单条上限 > 200K 的",
        cb.single_message_char_budget("1m") > cb.single_message_char_budget("200k"),
    )
    c.check(
        "历史预算不超过窗口 token（换算保守）",
        cb.history_char_budget("1m") <= cb.CONTEXT_PRESETS["1m"].tokens
        and cb.history_char_budget("200k") <= cb.CONTEXT_PRESETS["200k"].tokens,
    )
    c.check(
        "非法档位取默认预算",
        cb.history_char_budget("32k") == cb.history_char_budget("200k"),
    )

    print("\n=== 4. 与 conversation_service 对接（纯函数，不连库）===")
    from app.services.ai.conversation_service import trim_history_by_budget

    # 造一批历史，总长介于 200K 与 1M 之间：200K 档应截断，1M 档应全留
    unit = "字" * 500
    history = [{"role": "user" if i % 2 else "assistant", "content": unit} for i in range(400)]
    total = len(history) * 500
    kept_200k = trim_history_by_budget(history, max_chars=cb.history_char_budget("200k"))
    kept_1m = trim_history_by_budget(history, max_chars=cb.history_char_budget("1m"))
    c.check(
        "同一批历史：200K 档截断、1M 档保留更多",
        len(kept_200k) < len(kept_1m),
        f"200K={len(kept_200k)} 条 / 1M={len(kept_1m)} 条（总 {total} 字符）",
    )
    c.check(
        "截断保留的是最近的（时间正序、末条仍在）",
        kept_200k and kept_200k[-1] is history[-1],
    )

    print(f"\n{'=' * 56}\n结果：{c.passed} 通过 / {c.failed} 失败")
    return 1 if c.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
