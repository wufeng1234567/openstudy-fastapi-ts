---
name: 多智能体角色路由会破坏 _toolpref_probe P10 组的前提，须显式锁 role="general"
description: 阶段1 角色切分后「列一下我的笔记」被路由到 note 角色，导致 _toolpref_probe P10a 失败；正确修法是给该探针的 AgentRequest 显式指定 role=general，而非放宽断言
type: feedback
from: Agent
---

**多智能体阶段 1 引入角色路由后，`tests/_toolpref_probe.py` 的 P10 整组必须在其 `AgentRequest` 上显式指定 `role="general"`，否则会因角色路由误判而判红。**

**Why:** 2026-10-09 阶段 1 落地角色切分后跑 `_toolpref_probe.py`，P10a 判红。根因不是 bug：P10a 的测试消息是 `"列一下我的笔记"`，被新路由按关键词「笔记」判定为 **note 角色**，于是把角色外工具（如 `bank_manage`）也从绑定的 tools 里排除，令 P10a 的断言 `"bank_manage" in bound_names`（探针约 727 行）为 False。**这是探针与设计的真实冲突**：P10 系列的前提是「只屏蔽了 `note_manage`，其余工具都应绑定」，那是**角色化之前**的旧口径；角色化后该消息绑定的是 note 专属窄工具集，是新设计的正确行为。

**How to apply:** 遇到探针因新设计行为变化而"失败"时，先判定是**真 bug** 还是**探针前提过期**。此例属后者——**正确且合规的修法**是给该探针的 `AgentRequest` 加 `role="general"`（模拟"不启用角色切分"的旧口径），让它继续聚焦其真正要测的"用户屏蔽闸门"，不受角色路由干扰；**不要**为图省事放宽/删除探针断言。注意 **P10 是一整组**（P10a/b/c 共用同一 stream）：若只解 P10a，P10b/P10c 的"模型硬调 `note_manage` 被拒"前提在 note 角色下不成立（note 角色下 `note_manage` 是允许的），故需给整个 `AgentRequest` 加 `role="general"` 让整组回到旧口径。改完重跑 P10 组验证；同时确认 `AgentRequest` 已在该探针文件中导入。

## 2026-10-09 修复已落地并验证
- 修复结果：`_toolpref_probe.py` 加 `role="general"` 后 **32/32 全绿**（P10 组恢复）；另跑 `_probe_knowledge_ingest` **28/28 全绿**（loop 改动未破坏新工具链路）。
- **经验：当新设计让探针前提过期时，优先改探针输入（显式锁 role）而非改断言/放宽设计。** 同扩展探针（如 `_probe_knowledge_ingest`）直调工具、不经 `run_agent_stream` 角色逻辑，故不受角色切分影响，但阶段 1 改动后仍应回归跑一遍防回归。
- 阶段 1 改动清单（未提交，位于 delivery 工作区）：新增 `agent/roles.py`、`agent/orchestrator.py`、`tests/_probe_agent_role.py`；修改 `app/api/v1/ai.py`、`app/services/ai/agent/loop.py`。
