---
name: 全局工具 GLOBAL_TOOLS 叠加语义及其对探针的连带影响
description: GLOBAL_TOOLS（memory_search/memory_manage）在 compute_exclude 里并入 allow 并默认对官方角色与用户自定义智能体可见；改后须同步 _probe_agent_role 与 _probe_agent_config 的多条断言
type: feedback
from: Agent
---

**`GLOBAL_TOOLS`（`memory_search`/`memory_manage`）是集中定义、在 `compute_exclude` 里并入 `allow` 的全局工具，默认对所有官方角色和用户自定义智能体（`build_user_role`）可见。涉及角色/工具分配或其探针的改动，都要按「生效工具 = 白名单 ∪ GLOBAL_TOOLS」这一语义（并再与「全部 − 用户屏蔽」取交）来判定。**

**Why:** 2026-10-09 把记忆能力改为全局默认注入后，许多以「角色 `tools` 白名单」为口径的探针断言前提过期。逐条受影响：
- `tests/_probe_agent_role.py`：AR-01（工具名校验）须同时校验 `GLOBAL_TOOLS` 里的工具名存在；AR-03（每个工具至少被一个非 general 角色覆盖）的覆盖集须并入 `GLOBAL_TOOLS`；AR-06（关键词「记」→ memory）须改为断言「记忆类消息不再路由到独立 memory 角色」（应落 general，因通用场景无其他关键词命中）；AR-12/13/14（生效工具）应为 `bank.tools ∪ GLOBAL_TOOLS`；AR-20（红线）应为 `(role_tools ∪ GLOBAL_TOOLS) ∩ (all − 用户屏蔽)`；并新增 AR-22（全局工具对所有具名角色可见），以及「全局工具对用户自定义智能体 `build_user_role` 也可见」的断言。
- `tests/_probe_agent_config.py`：AC-21「用户 Agent 生效工具 == 其白名单」会因 GLOBAL_TOOLS 叠加而失败，须改为 `白名单 ∪ GLOBAL_TOOLS`。

**How to apply:** 触及 `roles.py` 的 `GLOBAL_TOOLS`/角色工具分配、`orchestrator.py` 的 `compute_exclude`、或 `build_user_role` 后，跑探针前先按上述语义核对 `_probe_agent_role.py`（AR-01/03/06/12/13/14/20 及新增 AR-22）与 `_probe_agent_config.py`（AC-21）的断言。注意 AR-18（`bank_defs < full_defs`）在此语义下仍成立（bank 白名单 3 + 全局 2 = 5 < 11），无需改。原则同 `_toolpref_probe` P10：新设计让探针前提过期时，改探针断言口径以对齐新设计，而非放宽设计本身。

**2026-10-09 补充（指挥家 `delegate_task` 元工具引入后，AC-21/22 语义不变）：** 工具集加入元工具 `delegate_task` 并让它进入 general 白名单后，`_probe_agent_config.py` 的 **AC-21/22 无需改**——两式比较的是「生效工具 == 白名单 ∪ GLOBAL_TOOLS」，而生效工具会**排除** `delegate_task`，白名单 ∪ GLOBAL_TOOLS（也不含它）同样不含它 → 两侧相等仍成立。改探针前先按「元工具是否同时出现在比较式两侧」逐条推演，别连带改无辜断言。此时全量回归口径为：角色探针 21/21、用户智能体探针 **22/22**、`_toolpref_probe` 32/32、`_probe_knowledge_ingest` 28/28（另新增指挥家探针，见 `tests-probe-conductor.md`）。

## 2026-10-09 处理状态（已完成，全绿）
- 已核对/修改 `_probe_agent_role.py` 的 AR-01、AR-03、AR-06、AR-12/13/14、AR-20，并新增 AR-22 及 `build_user_role` 全局可见断言。
- 已改 `_probe_agent_config.py` 的 AC-21（断言改为「用户 Agent 生效工具 = 白名单 ∪ GLOBAL_TOOLS」）。
- **实测结果（全绿）**：角色探针 **21/21**（原 20 + 新增 AR-22）；`_probe_agent_config.py` **21/21**。
- **代价（可接受）**：bank 角色生效工具由 3 → 5（白名单 3 + 全局 `memory_search`/`memory_manage`）；bank 的 `describe` 输出由 2626 → **4164 字符**——这是全局工具的合理代价（用户明确要记忆工具全局可用）。
- 已全面搜索 `memory` 角色 key 的前端/文档引用：仅注释/文档提及，无代码引用；设计文档 `docs/fastapi_v2_多智能体协同方案.md` §4.2 角色表已更新（把 memory 从角色表移入全局工具）。
- **全量回归已完成（2026-10-09，全绿）**：角色探针 21/21、用户智能体探针 22/22、`_toolpref_probe` 32/32、`_probe_knowledge_ingest` 28/28、编译通过。删除 memory 角色后 `_toolpref_probe` 仍 32/32：其 CJK 守卫/P11d 扫 `describe()`，memory 角色的 `prompt_fragment` 是英文，删除不影响白名单判红（P11d 只扫注册表静态输出，不含运行期 system_prompt）。
- **前端无需改**：前端角色选择器从 `/agent/roles` 动态拉取，memory 角色消失后自动不再显示；`chat.vue` 无「记忆助手」硬编码引用。
