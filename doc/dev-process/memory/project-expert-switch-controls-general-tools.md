---
name: 专家开关已控制 general 工具集（方案A已落地）
description: 修复"关专家却仍能用其工具"——compute_exclude 加 disabled_role_keys，关专家=收走其工具；提交 ec44bef
type: project
---

2026-10-10 **已修复并推送**：专家开关原先**只控制通讯录/委派、不控制 general（指挥家）的工具集** → 关掉专家后指挥家仍能自己直接调那些工具（"关了没关"）。**结论已过时，现状见下。**

## 方案 A（已落地，提交 `ec44bef`，区间 `777f6c9..ec44bef`）
**关专家 = 该专家名下的业务工具也从 general 工具集收走。**
- `orchestrator.compute_exclude(role, *, all_tool_names, user_disabled=(), disabled_role_keys=())` 新增参数：
  · 对「不限工具」的角色（`general`，`role.tools` 为空）：排除集额外并入**被关专家的工具**
    （新增私有函数 `_tools_of_closed_roles(disabled_role_keys, all_names)` —— 只统计可委派官方专家
    `renderable_sub_agents()`，收敛到注册表真实工具名；用户自定义 key 不在 OFFICIAL_ROLES 自动忽略）；
  · 具名子代理/用户自定义智能体本就用白名单，不受影响（白名单外自然被排除）。
- `loop.run_agent_stream` **主链路**（约 823 行）的 `compute_exclude` 传入 `disabled_role_keys`。
- **顺带修的浪费**：新增 `has_any_sub_agent = bool(renderable_sub_agents(disabled_keys=disabled_role_keys))`；
  **无任何可委派专家时不再给指挥家挂 `delegate_task`**（否则模型白白发起注定失败的委派）。故关全部专家
  → `tool_defs` 为空 → `tools_all_disabled` 生效 → 不 bind_tools，退纯聊天。
- ⚠️ **子代理各自的 exclude（循环里 `delegate_roles`/`sub_excludes` 构建）不传 `disabled_role_keys`** ——
  子代理就是"某个专家本人"，它当然要用自己的工具。

## 效果
- 关「题库专家」→ 指挥家既不能派它、也不能自己调 `bank_manage`/`question_manage`/`question_flag_manage`。
- 关全部专家 → general 工具集为空（**全局记忆工具 GLOBAL_TOOLS 不被牵连**，仍可用）→ 纯聊天。
- 全局工具（记忆）始终对所有角色可见，不被关专家影响。

## 验证（全绿）
- `tests/_probe_agent_expert.py` 新增 **EX-14~17**（关 bank → general exclude 含 bank 工具；未关不含；
  关全部 → exclude 覆盖全部业务工具；记忆不被牵连）：**17/17**。
- 回归：角色 21/21、指挥家 23/23、用户智能体 22/22、工具偏好 32/32、知识库写入 28/28、`app.main` OK、编译通过。
- 探针 DB 段连库，EX-14~17 是纯逻辑段（在 DB 段之后），跑整个文件即可。

**Why:** 用户实测发现"关掉全部专家后 LLM 仍可独立调全部业务工具"，与"关掉=没了"的直觉不符。
**How to apply:** 后续新增官方专家时，其 `RoleSpec.tools` 即"关掉该专家要收走的工具集"，无需另配映射；`compute_exclude` 的 `disabled_role_keys` 只对「不限工具」角色生效。给 `compute_exclude` 增删参数后，`_probe_agent_expert.py` 的 EX-14~17 需同步。
