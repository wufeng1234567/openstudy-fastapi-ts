---
name: 时间线 metrics 持久化探针 _probe_timeline_metrics.py
description: 验证 save_agent_timeline/get_agent_timeline 新对象格式与旧数组格式兼容、metrics 读回正确的探针入口
type: reference
from: Agent
---

2026-10-10 为「聊天底部状态条 metrics 会话持久化」修复新增的验证工具：`openstudy-fastapi\tests\_probe_timeline_metrics.py`。

用途：用真实 DB（本环境可用）端到端验证 timeline 读写格式——① 存带 metrics 的 payload → `get_agent_timeline` 读回 metrics 正确；② 存旧纯数组 payload → 读回 `metrics=None` 且 `messages` 正常（证明向后兼容旧数组格式不倒退）。

结果：10/10 全绿。

**⚠️（2026-10-10）该探针面向的「状态条 metrics 持久化」修复方向已被用户定案废弃**（改为直接删掉底部状态条，见 `feedback-chat-status-bar-removed`）；后端 `save_agent_timeline`/`get_agent_timeline` 兼容逻辑与探针仍在，但前端已不再展示 metrics，此探针的价值仅剩"防 timeline 读写格式回退"。

**How to apply:** 改动 timeline payload 结构（`{messages, metrics}` 对象 vs 旧数组）、或调整 `save_agent_timeline`/`get_agent_timeline` 兼容逻辑时，跑此探针做端到端回归。相关背景见 project-chat-metrics-session-memory.md。
