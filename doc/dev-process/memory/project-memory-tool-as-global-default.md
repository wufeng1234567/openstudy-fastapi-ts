---
name: 记忆助手应改为全局默认工具
description: 用户要求去掉可路由的「记忆助手」独立角色，把记忆能力改为所有角色可用的默认全局工具
type: project
from: Agent
---

用户（2026-10-09）提出：**「记忆助手」不应作为可被路由/选择器里单独选择的独立角色存在，隐藏它，把记忆能力作为默认全局工具供所有角色使用**（每个角色都能用记忆工具，用户无需单独去选「记忆助手」）。

**Why:** 用户认为记忆是横切能力，把它做成一个要用户主动选择的路由目标不合理；全局默认注入更符合使用习惯。

**How to apply:** 涉及智能体「记忆助手」相关改动时的目标形态——记忆工具（`memory_search`/`memory_manage`）不再绑定在独立的 memory 独占角色上，而是默认对所有角色可用；「记忆助手」不再出现在角色选择器（如前端 `el-select` 的官方角色分组）中。改动前须先核实 `app/services/ai/agent/roles.py` 中各角色的工具分配现状。

## 2026-10-09 落地实现（已编码）
- `roles.py`：**删除 memory 角色**；新增模块级常量 `GLOBAL_TOOLS = ("memory_search", "memory_manage")`（定义在 `GENERAL_ROLE` 附近），并加入 `__all__` 导出；其它角色的 `tools` 注释补充说明全局工具会自动叠加。
- `orchestrator.py`：`compute_exclude` 中把 `GLOBAL_TOOLS` **并入 `allow` 再算 exclude**；import 引入 `GLOBAL_TOOLS`。
- **设计要点（用户认可）**：全局工具**不是**并进各角色的 `tools` 元组，而是集中定义 + 在 `compute_exclude` 里叠加——这样角色定义保持干净、全局工具集中管理。
- `resolve_role` 循环 `OFFICIAL_ROLES`，memory 删除后自动适配；仍需确认无硬编码 `"memory"`。
- 后续：`tests/_probe_agent_role.py` 会断言 memory 角色存在、AR-03「每工具被覆盖」等，删角色后需同步更新该探针。
- **语义补充（2026-10-09）**：`GLOBAL_TOOLS` 的生效范围为**所有官方角色 + 用户自定义智能体（`build_user_role`）**——「全局」既覆盖官方角色也叫对用户自建 Agent 可见。生效工具 = `白名单 ∪ GLOBAL_TOOLS`，再与（全部 − 用户屏蔽）取交。改动牵连的探针断言见 [`feedback-global-tools-overlay-probe-impact.md`](feedback-global-tools-overlay-probe-impact.md)。
