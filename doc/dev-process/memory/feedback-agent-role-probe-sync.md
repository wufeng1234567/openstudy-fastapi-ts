---
name: 改官方角色/全局工具后须同步更新 _probe_agent_role 探针
description: roles.py 增删角色或改动全局工具注入后，tests/_probe_agent_role.py 的断言（memory 角色存在、AR-03 每工具被覆盖等）会失效，须一并更新
type: feedback
from: Agent
---

**改动 `app/services/ai/agent/roles.py`（增删官方角色、调整工具/全局工具 `GLOBAL_TOOLS`）后，必须同步检查并更新 `tests/_probe_agent_role.py` 的断言，不能只改实现。**

**Why:** 2026-10-09 把 memory 角色删除、记忆工具改为 `GLOBAL_TOOLS` 全局默认注入时，`_probe_agent_role.py` 中会断言「memory 角色存在」「AR-03 每个工具都被某角色覆盖」等——删角色/改全局工具后这些断言的前提过期，探针会误判为失败。

**How to apply:** 凡触及官方角色表或工具分配，跑探针前先看 `_probe_agent_role.py`，判断是**真 bug** 还是**探针前提过期**（同 `_toolpref_probe` P10 的教训：优先改探针输入/断言口径对齐新设计，而非放宽设计）。AR-03 这类「每工具被覆盖」的断言在引入全局工具后应把 `GLOBAL_TOOLS` 计入覆盖集合。

**2026-10-09 元工具 `delegate_task` 案例（指挥家模式）**：`roles.py` 新增 `DELEGATE_TOOL_NAME = "delegate_task"`（指挥家专属元工具、永不进任何角色白名单）后，`_probe_agent_role.py` 的 **AR-03、AR-15、AR-16、AR-17、AR-20 共 5 项**需改口径——**这是新设计的正确结果**（`delegate_task` 不该被任何子代理/角色覆盖；general 的 exclude 现恒含它（若在 `all_names` 里）；红线断言含 `meta_exclude`）。修法：探针在 `all_names` 后构造「业务工具集」（剔除元工具）做覆盖断言；AR-03 明确不把 `delegate_task` 计入「需被覆盖」集；AR-20 红线右侧 `rhs = role_tools ∩ (全部 − 用户屏蔽)` 也必须扣 `meta_exclude`（否则 rhs 含 `delegate_task` 而 lhs 不含 → 不等）。凡新增「指挥家专属元工具」都要按此同步探针口径。

**反向教训（2026-10-09，避免过度修改）**：并非所有断言都受元工具影响。AR-12/13/14 用的是 `bank_effective_allow = bank.tools ∪ GLOBAL_TOOLS`（不含 `delegate_task`），而 `all_names − ex` 也因 `bank_effective_allow` 不含它而**同样不含 `delegate_task`** → 两边相等，**AR-12/13/14 不受影响，无需改**。改探针前先按「元工具是否同时出现在比较式两侧」逐条推演，只改真正转红的项，不要连带改无辜断言。

**2026-10-10 方案 A（`compute_exclude` 加 `disabled_role_keys`）对本探针无影响**：`_probe_agent_role.py` 的 **AR-15/16/17** 断言 `general` 的 `exclude` 只含元工具——因它们调用 `compute_exclude` 时**未传 `disabled_role_keys`**（默认空集），方案 A 生效后这些断言仍正确、无需改。结论：为 `compute_exclude` 增参数并让新逻辑对 `general` 生效后，**只有传了新参数的调用点行为改变**；不传参的探针断言（AR-15/16/17）不受连带影响。改签名/语义后先逐个调用点判断是否传新参数。
