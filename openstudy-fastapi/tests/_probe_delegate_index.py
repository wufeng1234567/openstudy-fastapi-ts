# -*- coding: utf-8 -*-
"""同步校验：delegate 事件 index 用整轮全局 delegate_seq（无需 asyncio）"""
import inspect
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.services.ai.agent import loop as loop_mod

src = inspect.getsource(loop_mod.run_agent_stream)
seq_def = src.find("delegate_seq = 0")
loop_pos = src.find("for loop_index in range")

rows = [
    ("PD-19", "delegate_seq 在 LLM 轮次循环之前声明", seq_def != -1 and loop_pos != -1 and seq_def < loop_pos),
    ("PD-20a", "delegate_start 不再用 len(delegate_jobs) 作 index", '"index": len(delegate_jobs)' not in src),
    ("PD-20b", "delegate_start 用 this_delegate_idx", "this_delegate_idx" in src),
    ("PD-20c", "delegate_done 用 item[seq]", 'item["seq"]' in src),
    ("PD-20d", "job 元组含 seq（7 元素解包）", "_cid, _tool, _params, _idx, _key, _name, _seq = job" in src),
]
red = 0
for cid, title, ok in rows:
    if not ok:
        red += 1
    print(f"  [{'通过' if ok else '失败'}] {cid} {title}")
print(f"\n共 {len(rows)} 项；红的={red}")
sys.exit(1 if red else 0)
