---
name: 专家开关探针 _probe_agent_expert.py
description: 验证「专家管理」（ai_agent_role_pref 开关服务 + 专家路由/通讯录过滤）的探针入口
type: reference
from: Agent
---

2026-10-10 为「可用工具 → 专家管理」重构新增的验证工具：`openstudy-fastapi\tests\_probe_agent_expert.py`。

用途：连真实 DB（用 probe uid），验证① 专家开关服务（`agent_role_pref_service` 的 `disabled_role_keys` / `set_role_disabled`，即新表 `ai_agent_role_pref` 读写）；② 指挥家**路由 / 通讯录**在被禁专家下的过滤行为（被关专家不进通讯录、不被路由到）。

**前置：建表**——新表 `ai_agent_role_pref` 由 `init_db`（create_all）创建，跑探针前须先建表（幂等，成功输出 `DB_OK` + `Database tables created successfully`）。注意 `create_all` 不会 ALTER 既有表（见 `feedback-sqlalchemy-create-all-no-alter`）。

**2026-10-10 首跑结果与断言修正（重要）：** 首跑 12/13，EX-10「关闭 bank 后通讯录仍含 bank」红。**真因=断言过弱**：EX-10 用子串 `"bank" not in brief` 判断，但 `stats` 专家 capability 文案含 "who shared a bank with me" 的 "a bank"，造成误命中（非真的过滤失效——note 行显示 bank 已被正确过滤）。**修法=断言改为按行首前缀精确匹配，如 `- bank (`**。改后 **13/13 全绿**。教训：验证通讯录过滤时勿用裸子串匹配 key（key 可能是其他文案的子串），须匹配行首条目格式。

**2026-10-10 全量回归全绿（专家管理交付验收口径）：** 本轮把「专家管理」前端（`chat.vue`/`agent.ts`）+ 建表（`ai_agent_role_pref`）+ 新探针全部落地后，全量回归通过：专家探针 **13/13**、角色探针 **21/21**、指挥家探针 **23/23**、用户智能体探针 **22/22**、`_toolpref_probe` **32/32**、`_probe_knowledge_ingest` **28/28**，且 `app.main` 导入 **APP_OK**。

**2026-10-10 方案 A 落地后：探针扩到 17/17 全绿。** 用户批准"方案 A"（关专家连 general 的工具集也收走，见 `project-expert-switch-does-not-restrict-general-tools`）后，为该探针新增 **EX-14~17**：①`compute_exclude(general, disabled_role_keys={'note'})` 须含 `note_manage`；②关全部专家 → `exclude ⊇ 全部业务工具`。**当前专家探针 17/17 全绿**（13 + 4）。

**本轮的探针改动范围：** 新增 `tests/_probe_agent_expert.py`；同时修改了 `tests/_probe_conductor.py`（因指挥家提示词标题/文案改为 "Main Assistant" 而同步断言，详见 `tests-probe-conductor`）。改角色/专家/提示词相关能力后，`_probe_agent_expert.py` + `_probe_conductor.py` + `_probe_agent_role.py` 都须一并回归。

**How to apply:** 改动专家开关服务、`ai_agent_role_pref` 模型、或指挥家 `resolve_role`/`render_sub_agents_briefing` 的 `disabled_role_keys` 过滤逻辑时，跑此探针回归。相关背景见 `project-agent-tools-reframe-as-experts`。

**2026-10-10 再次全量回归全绿（收尾口径）：** 本轮基准提交前跑全量回归全部通过——专家 **17/17**、角色 **21/21**、指挥家 **23/23**、用户智能体 **22/22**、`_toolpref_probe` **32/32**、`_probe_knowledge_ingest` + `app.main` 输出 `APP...`（EXIT=0）。本轮改动文件为 `orchestrator.py`、`loop.py`、`tests/_probe_agent_expert.py`。**注意：本环境判探针通过以退出码 `EXIT=0` 为准（PowerShell 管道/中文匹配易踩编码坑，勿依赖 grep 匹配中文）。**
