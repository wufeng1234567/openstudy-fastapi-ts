# -*- coding: utf-8 -*-
"""探针：确认卡「一次一张」+ 调用专家时的等待提示（接线校验）。

背景（2026-10-17 用户报的两个问题）：
  1. 模型说完「我同时派两位专家并行处理…」后界面卡住，过一会儿才冒出「专家协同中」——
     中间那段（模型正在流式生成 tool_call 参数）没有任何等待提示。
     要求：期间显示「正在调用专家…」，并且与「正在调用工具…」区分开。
  2. 并行派两个专家时，两张确认卡**同时**弹出。用户滚到底只看见最后一张，
     点了确认后第一张还挂着 → 后端等满 180 秒超时，用户感知是「点完确认页面傻愣着」。
     要求：确认卡串行，一次只出一张。

这两件事都是「接线」性质（一个事件 + 一把锁），没有纯函数可测，
所以本探针做**源码级断言**：确保关键语句还在，防止后续重构把它们悄悄拆掉。

用法：.venv/Scripts/python.exe tests/_check_expert_wait_and_confirm_lock.py
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_DIR = os.path.join(ROOT, "app", "services", "ai", "agent")


def _read(name: str) -> str:
    with io.open(os.path.join(AGENT_DIR, name), "r", encoding="utf-8") as f:
        return f.read()


def main() -> int:
    loop_src = _read("loop.py")
    sub_src = _read("sub_agent.py")
    failures = []

    # ---- 问题 1：调用专家期间的等待提示 ----
    if "正在调用专家…" not in loop_src:
        failures.append(
            "loop.py: 缺少「正在调用专家…」等待提示 —— 正文与专家卡之间会重新变成空白"
        )
    if "正在调用工具…" not in loop_src:
        failures.append("loop.py: 缺少「正在调用工具…」—— 两种等待态没有区分开")
    if "announced_wait" not in loop_src:
        failures.append("loop.py: 缺少 announced_wait 去重 —— 每个流式分片都会发一条等待提示")

    # ---- 问题 2：确认卡串行 ----
    if "confirm_lock = asyncio.Lock()" not in loop_src:
        failures.append("loop.py: 缺少每轮运行的 confirm_lock（确认卡会再次并发弹出）")
    if '"confirm_lock": confirm_lock' not in loop_src:
        failures.append("loop.py: confirm_lock 没有传给子代理 —— 并行专家仍会同时弹卡")
    if "async with confirm_lock:" not in loop_src:
        failures.append("loop.py: 主循环的确认没有走 confirm_lock")
    if '(ctx.extra or {}).get("confirm_lock")' not in sub_src:
        failures.append("sub_agent.py: 没有读取 confirm_lock —— 子代理确认不受串行约束")
    if "_lock.acquire()" not in sub_src or "_lock.release()" not in sub_src:
        failures.append("sub_agent.py: confirm_lock 的 acquire/release 不完整（可能漏释放）")
    if "等待上一个确认完成后执行" not in sub_src:
        failures.append("sub_agent.py: 排队中的专家没有状态提示，看起来会像卡死")

    if failures:
        print("失败项:")
        for f in failures:
            print(f"  ✗ {f}")
        return 1

    print("全部通过（等待提示 3 项 + 确认串行 6 项）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
