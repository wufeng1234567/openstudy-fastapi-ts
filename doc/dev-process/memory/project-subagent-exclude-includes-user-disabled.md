---
name: 子代理 exclude 误并入 user_disabled 致工具集为空（委派全线瘫痪）
description: 2026-10-11 定案新根因——loop.py 子代理的 compute_exclude 把通用函数默认的 user_disabled 一并传入，用户屏蔽（含旧工具面板残留）会把子代理工具扣光
type: project
from: Agent
---

2026-10-11 排查「子代理 kb 拿到 0 个工具 → 报『没有可用工具（工具集为空）』→ 委派全线瘫痪、模型瞎编」时，**把根因从「运行时链路未把 kb 工具发给子代理」进一步收敛到：`user_disabled`（用户屏蔽工具集）为全量时，子代理 `tool_defs` 为空。**

**Why / 真凶位置：**
- `loop.py` 约 **1080、1090 行**构建子代理 exclude 时，**传了 `user_disabled=disabled_tools`**（`disabled_tools` = 用户屏蔽的具名工具集，来自 `ai_agent_tool_pref`）。
- `orchestrator.compute_exclude` 的 `disabled`（用户屏蔽）是**无条件并入**排除集的——故用户屏蔽会**同样施加到子代理身上**。
- **极端情况**：用户在旧「可用工具」面板里把所有工具关掉（或旧版本残留 `ai_agent_tool_pref` 全量 disabled）→ **所有子代理工具集为空 → 委派全瘫**。这与用户/产品本意（"关工具"是给 general/指挥家裁剪能力）严重不符。
- 依据 `roles.py` 文档与既有设计口径「**子代理就是那个专家本人，它要用自己的工具**」——子代理的能力应由**专家开关**（`ai_agent_role_pref`）控制，**不该被通用函数默认的 `user_disabled` 波及**。
- 注意与 `project-expert-switch-controls-general-tools`（方案 A）里记的「子代理 exclude 不传 `disabled_role_keys`」**不冲突**：那里漏掉的正是 `user_disabled` 这一路。

**修复方向（Agent 定策，分两层）：**
1. **治本**：**子代理 exclude 不叠加 `user_disabled`**（用空集），只扣「角色外工具 + 元工具」；子代理能力改由**专家开关**控制（新设计口径：用户关专家 = 该专家不可用；不再提供"子代理内部单个工具"的开关）。
2. **兜底（已加，用户已看到）**：`tool_defs` 为空时**明确报错**，不再静默瘫痪/瞎编。

**关键排查约束（与沙箱相关）：** 想确认用户 DB `ai_agent_tool_pref` 是否全量 disabled 时，沙箱内 **asyncio 建不起来（asyncpg 挂）** → 改**同步**方式查：读 `.env` 拿 PG 连接串（`localhost:5432`），用 **psycopg2（同步）直连**写只读探针（本轮落点为 `openstudy-fastapi\tests\_probe_db_pref.py`）。见 `feedback-sandbox-blocks-asyncio-event-loop`。
