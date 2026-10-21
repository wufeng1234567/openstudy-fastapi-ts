---
name: 指挥家模式（Orchestrator+Sub-Agents）已实施
description: 多智能体从"角色=工具预设"升级为"指挥家+子代理"的落地位置、语义与验证
type: project
---

2026-10-09 实施完成：多智能体从**"角色=工具预设"**（用户否定为"工具机制"）升级为**「指挥家（Orchestrator）+ 子代理（Sub-Agents）」**。设计稿 `docs/fastapi_v2_指挥家模式方案.md`。

## 用户拍板的核心语义
- **用户只与主智能体（指挥家）单入口对话**，不感知内部子代理；
- 指挥家掌握**子代理通讯录**（谁能干什么），决定"自己答 or 委派"；
- **子代理与用户通信被隔绝**（后台工作者），结果交回指挥家，**由指挥家整合后统一口吻回复**（Orchestrator-Worker）；
- **双通道**：显式选择（用户点名 → 子代理直接面向用户）/ 自动路由（指挥家模式）；
- 跨域请求**转交**而非报错。

## 落地位置
- **`roles.py`**：`RoleSpec` 新增 `persona`（子代理自我认知，英文）+ `capability`（给指挥家看的能力摘要）；5 个官方角色（bank/note/kb/stats + general）补全这两个字段；新增 `DELEGATE_TOOL_NAME="delegate_task"`、`renderable_sub_agents()`（有 capability 的角色，排除 general）、`render_sub_agents_briefing(extra_agents)`（渲染通讯录）。**注：原始实现 `capability` 为英文；2026-10-10 起用户要求改为 C 端口语（见 `project-agent-tools-reframe-as-experts`），"英文"约束已过时，实施时以该条记忆为准。**
- **`orchestrator.py`**：`compute_exclude` **永远排除 `delegate_task`**（元工具，防子代理递归委派）。新红线：`可用 = (角色白名单 ∪ GLOBAL_TOOLS) ∩ (全部 − 用户屏蔽 − 元工具)`。
- **`sub_agent.py`（新）**：`run_sub_agent(db, user_id, session_id, role_spec, task, llm, excluded_tools, max_loops=6, extra)` —— 自包含**精简 ReAct 循环**（不复用 `run_agent_stream`，避免把子代理过程流给用户/污染会话历史）；工具执行复用 `loop._execute_tool`（SAVEPOINT/异常转fail/记忆钩子同口径）；子代理**不挂 delegate_task**（防递归）。
- **`tools/delegate.py`（新）**：`DelegateTaskTool`（`delegate_task`，`write_operation=False`）。从 `ctx.extra` 取 `delegate_llm`/`delegate_roles`/`delegate_exclude`/`delegate_extra`；缺环境 → 明确 fail（不假装成功）。
- **`prompts.py`**：新增 `AGENT_CONDUCTOR_SECTION`（含 `{{SUB_AGENTS}}` 占位）；`build_agent_system_prompt(..., sub_agents_text="")` 非空时在确认规则后、输出规范前插入指挥家段。
- **`loop.py`**：`run_agent_stream` 改指挥家模式——显式点名（`req.agent_id` 非空 或 `req.role` 是具名子代理）→ 子代理直接面向用户（不挂 delegate）；否则 → **指挥家模式**（`role_spec=general` 全工具 + 加回 `delegate_task` + 注入通讯录 + `ctx.extra` 注入 `delegate_*` 环境）。新增 SSE 事件 `delegate_start`/`delegate_done`（含 agent/task/success/summary）。显式子代理时角色提示词用 `persona`。
- **`tools/__init__.py`**：注册 `DelegateTaskTool`。
- **前端 `agent.ts`**：`AgentEventType` 加 `delegate_start`/`delegate_done`（UI 时间线预留；子代理不直接发言）。

## 验证（全绿）
- 新增 `tests/_probe_conductor.py`：**23/23**（子代理定义/通讯录/delegate_task 永排除/指挥家提示词/工具元数据/`run_sub_agent` 假 LLM 跑通窄工具裁剪）。用**假 LLM**（脚本式 `ainvoke`+`bind_tools`）+ mock `_execute_tool`，零成本。
- 回归：`_probe_agent_role` **21/21**（AR-03/15/16/17/20 已同步改为"元工具不计入覆盖/排除"）、`_probe_agent_config` **22/22**、`_toolpref_probe` **32/32**、`_probe_knowledge_ingest` **28/28**、`app.main` 导入 OK。

**Why:** 用户要真"智能体机制"而非"角色=工具表裁剪"；这是对已落地阶段 1/2 的方向性升级。

## 交付状态（2026-10-09）
指挥家模式改动已从 `gitcode/main` worktree 提交推送：本次共 **11 个文件**（8 个源码/探针 + 1 方案文档 + 2 探针），其中修改文件 `loop.py`/`tools/__init__.py`/`prompts.py`/`agent.ts` 相对 main 差异纯净（上一轮多智能体已推 main），可整文件拷入。worktree 内编译通过 + 指挥家探针 23/23。
**How to apply:** 后续改角色/工具时，注意 `delegate_task` 是元工具（不进任何白名单、永远被 exclude、只有指挥家模式加回）；子代理循环是 `sub_agent.py` 而非 `run_agent_stream`。
