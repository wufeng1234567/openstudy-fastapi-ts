---
name: sub_agent 启动诊断日志（key/工具数/工具名）待复现定音
description: 2026-10-11 sub_agent.py 新增启动诊断日志打印「工具数=N 工具=[...]」——用户下次复现时一锤定音区分 N=0（链路未发工具）vs N=5 但模型瞎编（模型行为，兜底已能救）
type: project
from: Agent
---

2026-10-11 在 `openstudy-fastapi\app\services\ai\agent\sub_agent.py` 新增**子代理启动诊断日志**：形如 `[sub_agent:key] 启动 ... 工具数=N 工具=[...]`。

**Why:** 「子代理没有 kb 工具、被问就瞎编」的根因本轮**尚未 100% 锁定**——两个候选分叉：(a) 真实链路 `tool_defs` 为空（链路未把工具发出去，N=0）；(b) 工具确实发给了模型、是模型瞎编（N=5）。假 LLM 探针只能证明**逻辑正确**，证明不了运行时真实链路（见 project-subagent-kb-tools-not-sent-runtime）。

**How to apply:** **等用户下次复现时读这条日志定音**——`工具数=0` → 判为链路问题（查 `llm.bind_tools(tool_defs)` / `compute_exclude` 实际传参）；`工具数=N` 但模型仍说没有工具 → 判为模型行为（协议文本兜底/拒答兜底已能救）。这是本轮刻意留下的「一锤定音」埋点，勿当普通调试日志删掉。
