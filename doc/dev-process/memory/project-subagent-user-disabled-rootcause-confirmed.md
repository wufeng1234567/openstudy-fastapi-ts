---
name: 子代理工具集为空根因已铁证确认（DB 全量工具禁用残留 + 用户无法关闭「工具屏蔽」）
description: 2026-10-11 查库实锤——user_id=105 的 ai_agent_tool_pref 有 12 条全量禁用记录（元凶），ai_agent_role_pref 为空（专家全开，与用户说法一致）
type: project
from: Agent
---

2026-10-11 排查「子代理 kb 拿到 0 个工具 → 委派全线瘫痪」的根因，**已用查库拿到铁证**，从假设收敛为定案。

**铁证（查用户 `user_id=105` 的库）：**
- `ai_agent_tool_pref` 有 **12 条禁用记录**——**所有工具都被禁用**（含 `knowledge_base_manage` 等全部）。
- `ai_agent_role_pref` **为空**（专家全开）——与用户说法完全一致。

**Why（关键）:** 用户说「没有对工具进行过屏蔽」，但库里就是有一份**全量工具禁用残留**（12 条），很可能是**旧「可用工具」面板的 bug/默认行为**（如"全选关闭"）遗留。这份数据正是元凶——`loop.py` 把 `user_disabled=disabled_tools` 传给子代理 → 全量禁用 → 子代理工具集为空 → 委派全瘫、模型瞎编。这是假设 2（见 `project-subagent-exclude-includes-user-disabled`）的实证。

**How to apply:** 修复分两层——① **治本（代码）**：子代理 exclude **不叠加 `user_disabled`**（`loop.py` 已改但**尚未提交**）；② **清数据**：删掉这份残留的 12 条 `ai_agent_tool_pref` 记录（须先核实字段是不是真 `disable=1`）。

## 2026-10-11 修复已完成并推送 ✅
- **字段核实**：12 条记录 `disabled=1` 全部为真，`create_time` 多在 2026-10-10 17:11 集中写入（旧面板遗留特征），`update_time` 亦有 10-10 17:10。
- **代码治本（提交 `50c0331`，已推 gitcode/main）**：`loop.py` 构建子代理 exclude（官方 + 用户自定义两处）由 `user_disabled=disabled_tools` 改为 `user_disabled=set()`，只扣「角色外工具 + 元工具」。新增回归探针 `tests/_probe_kb_tooldefs.py`（零 LLM，复现全量禁用→kb 工具集空，并断言正常态非空）。
- **数据修复（已执行）**：同步 psycopg2 直连 PG，`delete from ai_agent_tool_pref where user_id=105`（删 12 行），user 105 回到"全部启用"默认态——general/指挥家与子代理均恢复。
- **排查手段（可复用）**：沙箱 asyncio 挂 → 装 `psycopg2-binary`（同步）直连 PG（`.env` 的 `PG_HOST/PORT/NAME/USER/PASSWORD`）读 `ai_agent_tool_pref`/`ai_agent_role_pref`。临时诊断脚本用后即删。
- **兜底前置（提交 `ef61f3c`）**：`tool_defs` 为空时明确报错——正是这条把"工具集为空"暴露出来，才顺藤摸到 DB 残留。

**重要 UI 约束（与用户澄清相关）:** 用户当前 UI **只能操作「是否关闭专家」，没有任何开关能屏蔽/关闭工具**。因此即使子代理 exclude 保留 `user_disabled`，用户也无从恢复——这正是必须从代码层「子代理排除集不读 `user_disabled`」根治的原因，不能仅让用户去关工具。详见 `feedback-user-ui-has-no-tool-disable-control`。
