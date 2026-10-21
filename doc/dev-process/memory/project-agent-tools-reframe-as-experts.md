---
name: 产品概念重构——「可用工具」改为「专家管理」
description: 2026-10-10 用户要求把智能体设置里的「可用工具」改成面向 C 端用户的「专家管理」，且 LLM 须实时感知专家开关并用通俗语言告知用户
type: project
from: Agent
---

2026-10-10 用户对智能体产品提出一次**概念重构**要求（针对「可用工具 / tools」这套机制）：

**问题诊断（用户原话要点）：**
- 当前「可用工具」与「智能体」两者**不能做好协调、且很鸡肋**。
- 用户设想中**工具本是给智能体用的**；让**用户直接在智能体设置里配工具没有意义**——除非是**用户自己创建的智能体**才会用到该功能。
- 用户平时都是**和主代理（指挥家）聊天**，因此用户真正该管的是：**主代理可以开启哪些"专家"**。

**重构方向：**
1. 把「可用工具」区**改名/改造成「对应的专家」管理**——用户管的是"主代理能开启哪些专家"，而不是开关底层工具。
2. **对话措辞要更合理、面向普通 C 端用户**：给 LLM 的提示词要让 LLM 知道并把"专家"之类名词讲清楚；**直接说"它能干嘛"**，而不是那种"只有敲代码的程序员才看得懂"的技术性工具说明。
3. **LLM 要实时知道**：哪个专家被（用户）**关闭/开启**了、当前**是否可被调用**。

**关键关联点（Agent 已确认的现状事实）：** 后端 `/ai/agent/tools` 返回的 `label`/`descriptionZh` 是**给"工具"用的**中文文案，与"专家"语义不符，需要一起改；实测 12 个工具的 `label` 全是"XX管理"这类技术味词汇，用户要的是"专业角色/专家"。

**方案已定案（2026-10-10，用户通过 3 个问答确认后授权实施）：**
1. **开关粒度上移**：把「可用工具」开关从**工具粒度**上移到**专家（官方角色）粒度**——开关对象改为官方专家角色 `bank`/`note`/`kb`/`stats`（题库/笔记/知识库/统计专家）。理由：现有 `role` 体系本身就是"专家"概念，而"工具开关"是更细的粒度，两者层级冲突，用户直接开关 `bank_manage` 无意义。
2. **后端新增预偏好存储**：新表 `ai_agent_role_pref`（存用户**禁用**的专家，稀疏风格照既有 `ai_agent_tool_pref` 模型与 `tool_pref_service`）+ 对应服务；**指挥家通讯录/路由按它实时过滤**——被禁用的专家不进通讯录、不可被委派，LLM 自然知道"不可调用"。
3. **提示词口语化**：`roles.py` 的 `capability` 由英文改为 **C 端口语**（如"题库专家——帮你建题库、导入题目、管错题本"），让 LLM 对用户说"专家/助手"而非"工具/函数"。
4. **前端**：设置面板「可用工具」→「专家」，开关对象改为官方专家角色。

**How to apply（实施顺序）：** 先建表+服务 → 改指挥家通讯录/路由过滤 → 改 `roles.py` capability 文案 → 改前端设置面板。

## 实施进展（2026-10-10，未提交）
按上述顺序开始落地：
1. **建表**：新表 `ai_agent_role_pref` 模型已在 `app/database.py` 注册。
2. **服务层**：新增 `app/services/ai/agent/agent_role_pref_service.py`（照 `tool_pref_service` 风格）：`disabled_role_keys(user_id)`（读，**fail-open**）与 `set_role_disabled(user_id, role_key, disabled)`（写，**失败抛**）。
3. **编排层过滤**：`orchestrator.py` 的 `resolve_role` 加 `disabled_role_keys` 参数；`render_sub_agents_briefing(extra_agents, disabled_keys)` 仅在传入启用集时过滤通讯录（禁用专家不进通讯录→LLM 自知不可调用）。

**关键路由语义（非显然，用户确认）：** 当用户**显式点名**一个已被禁用的专家时，语义 =「用户关掉了它，不该用它」→ **忽略该显式指定，退回关键词路由/兜底**（而非报错/强行调用）；关键词路由也须**跳过被禁专家**。

## 实施进展续（2026-10-10，未提交）
4. **编排层禁用过滤补齐**：`renderable_sub_agents` 与 `render_sub_agents_briefing` 增加禁用过滤（按 `disabled_role_keys` 剔除被禁专家）；`Iterable` 需在 `roles.py` 顶部 import（已确认）。
5. **`roles.py` 文案口语化落地**：
   - `capability` 保持**英文**（守 P11d 白名单限制），但改为**业务化/口语化英文**，去技术黑话（给指挥家看）。
   - `description` 改为**中文口语**（界面用，`RoleSpec.description` docstring 明确"只给前端"、**不进注册表**，故不触发 P11d——依据 `feedback-p11d-scans-registry-not-runtime-prompt`）。
   - `name` 由"题库助手"改为"题库专家"（`name` 是界面/通讯录显示名，用于 `render_sub_agents_briefing` 形如 `- bank (题库专家): ...`）；用户措辞偏好"专家"而非"助手"。
   - 用户原话要求："直接说它可以干嘛""不要敲代码程序员看的词"。
   - 先改 4 个官方角色（bank/note/kb/stats），其余随后。

## 实施进展三（2026-10-10，未提交）
6. **`general` 角色文案定案**：`general` 是**指挥家自身**（不是可委派的子代理），其 `name` 显示在 `meta` 事件"当前由谁回答"中；用户倾向把"通用助手"改成更亲民的**"智能助手"**（在"通用专家"之间取舍后偏向前者）。
7. **指挥家提示词口语化**（`prompts.py` 的 `AGENT_CONDUCTOR_SECTION`）：保持**英文**（守 P11d），把 "sub-agents" 改口语为 **"specialist helpers / team members"**、用 **"experts"** 措辞，并要求 LLM **对用户说"专家/助手"**、用**业务语言**；明确**"通讯录里没有的专家 = 已被关闭/叫不到"**（只在通讯录里的专家可用）。
8. **`loop.py` 读禁用专家 + 传路由/通讯录**：`resolve_role`/`render_sub_agents_briefing` 调用点需传入 `disabled_role_keys`；`ai.py` 加专家 API。**关键约束（沿用首 token 优化）：新增的 `disabled_role_keys` DB 读必须并行进 `asyncio.gather`，不得新增串行 DB 读**（见 `project-chat-first-token-latency`）。

## 实施进展四（2026-10-10，未提交）
9. **`loop.py` 委派环境也传禁用（双保险）**：`renderable_sub_agents()` 的两处调用（一处约 1052 行构建委派环境、另一处约 1067 行）都须传 `disabled_keys`，使被关专家不仅不进**通讯录**、也进不了 `delegate_roles` 映射（`delegate_exclude` 同理）；理由=防模型在通讯录里没看到却在 delegate 工具 roles 映射里查到而被调用。
10. **`ai.py` 专家清单 + 开关 API**：在 `/agent/roles` 端点（约 788-810 行）之后新增 `GET /ai/agent/experts`（列可委派专家 + 启用状态）与 `PUT /ai/agent/experts/{key}`（开关）；模板参考 `AgentToolPrefBody`（约 954）+ `PUT /agent/tools`（约 976+）。**语义定案：只列"可委派专家"（即 `renderable_sub_agents`，排除 general）**，不让 general/指挥家自身出现在开关列表里。鉴权沿用既有风格：`get_current_user` 登录态取 `current_user["user_id"]`。

## 实施进展五（2026-10-10，未提交）
11. **后端专家 API 完成并编译通过**：`ai.py` 新增 `GET /ai/agent/experts` 与 `PUT /ai/agent/experts/{key}` 已落地，`Any` 已 import，后端编译验证通过。
12. **前端改造进行中**：`openstudy-vue3-ts/src/api/ai/agent.ts` 计划新增 `listAgentExperts` / `setAgentExpertPref`（专家 API），并把 `chat.vue` 设置面板的 `toolOptions`（工具开关）换成 `experts`（专家开关）；新 API 加在既有 `listAgentRoles` 附近。

## 实施进展六（2026-10-10，未提交）
13. **`agent.ts` 专家 API 已落地**：新增 `listAgentExperts` / `setAgentExpertPref` / `AgentExpert` 类型，位置在 `listAgentConfigs` 之前（`_authHeaders` 之后）。

**关键前端设计约束（用户已明确，非显然——易被误删）：**
- **保留 `toolOptions` / `toolLabelMap` 及其加载函数 `loadToolOptions`**——「我的智能体」管理页仍用它做**工具多选**（`chat.vue` 约 337 行 `v-for="t in toolOptions"`、约 294 行 `toolLabelMap`），**不是**本次要删的对象。
- 本次只把**设置面板的「可用工具」段**（`chat.vue` 约 214-234 行）换成**「专家」段**；新增独立状态 `experts` / `expertLoading` / `expertLoadFailed` / `expertTogglingKey` 与函数 `loadExperts` / `toggleExpert`，**与 toolOptions 完全独立**（勿复用/合并）。
- `onMounted` 改为**同时预取** experts 与 toolOptions（`openPanel('settings')` 同步改）。
- 交互文案（面向 C 端口语化）：标签「专家」、说明「开启后，主助手会在需要时请这位专家帮忙；关掉就完全不用它。」；DOM 结构复用既有 `.settings-tools` / `.settings-tool` 样式类。
- 响应取值口径：后端 `success(payload, ...)` 返回 `{code, msg, data}` → 前端取 `data.data.experts`（PUT 保存走同一口径）。

## 实施进展七（2026-10-10，未提交）
14. **`chat.vue` 前端改造已动手（据最新约 8 条消息）**：
    - 在 `toolOptions`（约 530 行）之前 / `_toolLoadInFlight`（约 546 行）之后**新增独立的 `experts` 状态与 `loadExperts`/`toggleExpert` 函数**；随后 `openPanel` 中 settings 分支的 `loadToolOptions()` **改为 `loadExperts()`**。
    - **`onMounted`（约 1031 行）预取由 `loadToolOptions()` 改为 `loadExperts()`**——理由：toolOptions 仅供「我的智能体」管理页使用，默认不再预取。
    - **保留 `openAgentManager` 里的 `loadToolOptions()`**——「我的智能体」管理页工具多选仍用它。
    - **注意**：上一轮为修"设置面板工具清单顺序敏感 bug"而把 `loadToolOptions` 挪进 `onMounted` 预取（提交 `ee78533`）；本轮因设置面板改专家，`onMounted` 预取对象换成 `loadExperts`，需确认 toolOptions 的预取不再需要（管理页进入时按需拉）。

## 实施进展八（2026-10-10，未提交）
15. **清理设置面板弃用的工具状态**：`toolLoading`/`toolLoadFailed` 仍被 `loadToolOptions` **内部使用**故保留（模板已不显示 loading，管理页 `el-select multiple` 也不需要）；`toolTogglingName`/`toggleToolInSettings` 已**完全无模板/脚本引用**（设置面板已改用 experts；管理页不用它）→ 一并删除，同时移除仅此处使用的 `saveAgentToolPref` import。`fetchAgentToolsForUi` 仍被 `loadToolOptions` 使用 → 保留。用户决策=保守最小改动，仅删彻底无引用的。
16. **踩坑（编辑失误）**：一次 edit 的 `oldString` 只匹配到 `openAgentManager`，等于把它前面**重复插入**了一份 `toggleToolInSettings` → 产生两份重复函数定义（一度出现两份位于约 649-667、669-686）。教训：删除函数时若其文本与相邻函数上下文相近，`oldString` 必须带足上下文（含相邻函数名）定位，否则会误插入重复；修法是分两步：先「第二份 + openAgentManager」→「openAgentManager」删第二份，再删第一份。
17. **重复函数清理（2026-10-10）**：两份 `toggleToolInSettings` 中**第一份带注释行、第二份没有**；最终用覆盖两段的完整块（约 649-687，含两份）一次性替换为空实现删除。
18. **删除前的引用确认（2026-10-10）**：经 grep 确认 `toolTogglingName` 声明与 `saveAgentToolPref` 均已**无任何引用**（模板/脚本俱无），故连同 `toggleToolInSettings` 一并删除。**方法教训（本仓库适用的惯例）：删函数/状态前先做全局引用确认（grep），使"完全无引用"成为删除依据，避免误删仍被引用的符号。**

## 实施进展九（2026-10-10，未提交）
19. **前端专家段样式**：专家项实际是「**名称 + 描述两行 + 右侧开关**」，既有 `.settings-tool`（flex 居中）**不够用**→ 在 `.settings-tool-name` 样式区之后追加 `.settings-expert`（`align-items: flex-start`）与 `.settings-expert-main`（纵排），仅改 `chat.vue`。
20. **前端校验通过**：`AgentExpert` 类型已 import；`experts`/`loadExperts`/`toggleExpert` 已定义；模板已用；用项目根 `openstudy-vue3-ts\_v.cjs` 脚本校验通过。
21. **第九步：建表 + 探针 + 回归**：先 `init_db` 建表 `ai_agent_role_pref`（成功 `DB_OK` + `Database tables created successfully`）；再写探针 `openstudy-fastapi\tests\_probe_agent_expert.py`（连 DB、用 probe uid，验证专家开关服务 + 路由/通讯录过滤），**待跑既有探针确认未破坏**。详见 `reference-probe-agent-expert`。

## 实施进展十（2026-10-10，未提交）
22. **专家探针首跑与修断言全绿**：`_probe_agent_expert.py` 首跑 12/13，EX-10 因裸子串匹配误命中（`stats` capability 含 "a bank"）而红→改为行首前缀匹配后 **13/13 全绿**。详见 `reference-probe-agent-expert`。
23. **全量回归与文案改动副作用**：跑角色/指挥家探针确认口语化 capability/name/提示词标题改动未破坏既有断言——**角色探针 21/21 通过**（不依赖文案）、**指挥家探针 22/23**（唯一红项 **CD-11** 因提示词标题由 `## ... (CONDUCTOR MODE)` 改为 "You Are the Main Assistant..."，断言写死 `CONDUCTOR` 而失效）、`app.main` **APP_OK**。下一步=改 CD-11 断言匹配新标题。详见 `tests-probe-conductor`。
24. **方法教训（本仓库通用）**：① 改 prompt/角色文案措辞前，先确认哪些探针断言写死了具体字面（CD-11 之痛）；② 断言通讯录过滤勿用裸子串匹配 key（可能命中其他文案）。

## 实施进展十一（2026-10-10，未提交）
25. **指挥家提示词标题改写与两条探针断言修复（全绿）**：新标题定稿 `## You Are the Main Assistant (with a Team of Experts)`；因标题改掉，**CD-11（找 `CONDUCTOR`）与 CD-14（找 `CONDUCTOR MODE`）两条断言同时失效**，已改为匹配新关键词 `"Main Assistant"`（CD-14 用 `"team of specialist"`）→ **指挥家探针 23/23 全绿**。CD-12 的 `role_spec.persona` 断言不受影响：本轮**只改 capability/description/name，未改 persona**，故 persona 里残留的 "Question Bank Specialist" 仍在且断言正确。**用户智能体探针 22/22 绿**；随后回归 config/toolpref/knowledge_ingest。详见 `tests-probe-conductor`。

## 实施进展十二（2026-10-10，全量回归全绿，进入 worktree 提交推送）
26. **全量回归通过（专家管理交付验收口径）**：专家探针 **13/13**、角色探针 **21/21**、指挥家探针 **23/23**、用户智能体探针 **22/22**、`_toolpref_probe` **32/32**、`_probe_knowledge_ingest` **28/28**，`app.main` **APP_OK**。
27. **本轮改动文件清单（后端）**：新增 `models/agent_role_pref.py`、`services/ai/agent/agent_role_pref_service.py`、`tests/_probe_agent_expert.py`；修改 `roles.py`、`orchestrator.py`、`loop.py`、`prompts.py`、`api/v1/ai.py`、`database.py`、`tests/_probe_conductor.py`；前端改 `api/ai/agent.ts`、`views/front/agent/chat.vue`。
28. **worktree 搬运注意（本轮实证）**：`database.py` 须手工只加 1 行（`agent_role_pref,`）——它相对 main 显示 `+28/-0` 含历史遗留（`client_token`）；`roles.py`/`orchestrator.py` 相对 main 显示"整文件被删"(`0 309`/`0 182`) 是未跟踪文件假象（详见 `feedback-git-worktree-isolation`）。fetch 得远程 tip=`3fe1fe3`（详见 `project-gitcode-push-requires-fresh-pat`）。

## 实施进展十三（2026-10-10，worktree 搬运实操中）
29. **逐文件 diff 块核对结果（本轮实证）**：`ai.py` 单块（812 处，正是新增专家端点段）=纯净；`loop.py` 5 块全落在本次改动区（75 import / 766/800/815/986 指挥家）；`prompts.py` 1 块（382 指挥家段）——三者**纯净可整拷**。

## 实测发现（2026-10-10，语义缺口）
30. **专家开关不控制 general 自身工具集**：实测「关掉全部专家后发给 LLM 的信息」——通讯录（`sub_agents_text`）为空，但 `general` 的 `tool_defs` 仍是**全部工具**（`role_spec=general` 的 `tools=()`→不限→`compute_exclude={delegate_task}`→指挥家加回 delegate_task→`excluded_tools={}`）。即专家关闭只断**委派路径**、不断 **general 直接调用业务工具**的路径，与"关专家=其工具不可用"的用户预期不符。详见 `project-expert-switch-does-not-restrict-general-tools`。
30. **`database.py` 手工改流程**：先拷纯净文件，再在 worktree 内手工 edit。worktree 的 `database.py` 检出自 main = 旧版（**无 `agent_role_pref,`、也无 `client_token`**，main 版本干净）；主工作区的 `database.py` 有 `client_token` 历史遗留且本轮已加过 `agent_role_pref,` 行 → worktree 内**只加本次那 1 行**即可，不带历史遗留；两处最终一致（除主工作区的 client_token 遗留）。
31. **正确次序（本轮确认）**：先拷纯净文件 → 再在 worktree 手工改 `database.py`（只加 1 行）→ 最后检查 worktree 改动清单。

## 实施进展十四（2026-10-10，已提交并推送 ✅）
32. **完成提交推送**：提交 `777f6c9`（`fix/feat(agent): 「可用工具」改造为「专家」管理；指挥家实时感知专家开关`），区间 `3fe1fe3..777f6c9`，hook PASSED，已推 gitcode/main。worktree 内共 12 项变更（`database.py` 仅 +1 行，无历史遗留），worktree 编译通过；前端 `@vue/compiler-sfc`+`typescript` 校验通过。
33. **探针踩坑**：`_probe_agent_expert.py` 的通讯录过滤断言**须用「行首 `- bank (`」而非子串 "bank"**——其他专家 `capability` 里出现 "a bank"（stats 的 "who shared a bank with me"）会让子串匹配误命中（EX-10 曾因此红）。`_probe_conductor.py` 的 CD-11/CD-14 因指挥家段标题由 `CONDUCTOR` 改为 `Main Assistant` 需同步改断言。

**Why:** 本产品是面向普通学习者的教育/学习类应用（C 端），不是开发者工具——底部状态条、token 耗时等都已被用户以"对用户是噪音"删掉（见 `feedback-chat-status-bar-removed`）；同理"工具/工具开关"这种开发者术语对 C 端用户不可理解，必须抽象成"专家"并用人话描述能力。
**How to apply:** 后续处理智能体设置面板时，把「可用工具」相关 UI 与文案（含后端 `label`/`descriptionZh`）**按"专家"语义重构**；LLM 提示词中涉及专家/能力处用**非技术、C 端可懂的表述**（说"能帮你做什么"）；并确保 LLM **实时获知**当前专家开关状态与可调用性，不要再把裸"工具"概念暴露给普通用户。

## 实施进展十五（2026-10-10，方案 A 已获用户批准并开始实施）
34. **语义缺口修复方案定案=方案 A（用户以"ok"批准）**：Agent 就"关专家不修剪 general 工具集"这一缺口给出三选一（A 关专家同时收走该专家业务工具 / B 只改文案说清"只管委派" / C 折中只隐通讯录），**用户批准方案 A**——即"关掉专家 = 其业务工具对 general 也不可用"，让"关了就是没了"成立。
35. **方案 A 的实现要点（本轮进行中）**：改 `orchestrator.py` 的 `compute_exclude`，加 `disabled_role_keys` 参数——对 `general` 角色（`role.tools` 为空=不限）时，把**被关闭专家的工具**从"全部工具"里剔除。`general` 有效工具 = 全部 − 被关专家工具 − 用户屏蔽 − 元工具。需"专家→工具"映射：取 `OFFICIAL_ROLES[key].tools`，且只取**可委派专家**（`renderable_sub_agents`，排除 general 自身）；新增辅助 `_tools_of_closed_roles`（依赖 `renderable_sub_agents`，须确认其来自 roles 已 import）。**效果预期**：关掉"题库专家"→ 指挥家既不能派题库专家、也不能自己调 `bank_manage`；关全部 → 工具集真为空 → 退纯聊天。

**Why:** 专家开关名义上是"专家粒度开关"，但先前只实现为过滤通讯录/路由，未下沉到 general 自己的工具白名单，导致"关专家形同虚设"；方案 A 让开关有真实可感知效果且逻辑自洽（工具集 = 未关闭专家的工具 ∪ 全局工具）。

## 实施进展十六（2026-10-10，方案 A 编码推进中）
36. **`orchestrator.py` import 补 `renderable_sub_agents`**（连同其它符号）。
37. **`loop.py` 四处 `compute_exclude` 调用点区分对待**：**主链路**（约 823 行，指挥家/general）**必须传 `disabled_role_keys`**（方案 A 核心）；**子代理各自的 exclude**（约 1069/1079 行）**不传**——子代理就是"某个专家本人"，它要用自己的工具，不应扣"被关专家"的工具（它本身就是那个专家）。
38. **关键设计判断（非显然，勿回退）**：`delegate_task` 在指挥家模式会被加回 → `excluded_tools` 不含它 → `tool_defs` 含 `delegate_task` → `tools_all_disabled(=not tool_defs)` 恒为 False。**后果：关掉全部专家后 `tool_defs=[delegate_task]`**（通讯录空、只有委派工具）→ 模型看到 `delegate_task` 却**无专家可派**，白浪费一轮。**修法**：把"是否加回 `delegate_task`"改为**依赖是否有可用专家**——在约 828 处判断 `renderable_sub_agents(disabled_role_keys)` 是否为空；空（通讯录为空）时指挥家也**不挂 `delegate_task`**。
39. **`delegate_env` 构建**（约 1063 `conductor_mode` 分支）：保持简单，仅在 `conductor_mode` 时建（`delegate_roles` 为空无害但多余）；已知 1078 附近的 `renderable_sub_agents()` 调用须传 `disabled_keys`（上轮已改）。改完须编译验证，并核对 `has_any_sub_agent` 与 `delegate_env` 的 `renderable_sub_agents()` 调用是否口径一致。

## 实施进展十七（2026-10-10，方案 A 落地并回归全绿）
40. **方案 A 编码完成、编译通过**：`compute_exclude` 加 `disabled_role_keys`，对 `general` 剔除被关专家的业务工具；"是否加回 `delegate_task`"改为依赖 `renderable_sub_agents(disabled_role_keys)` 是否为空（空则不挂 `delegate_task`）。改完编译通过。
41. **`_probe_agent_expert.py` 加方案 A 断言（EX-14~17）**：①`compute_exclude(general, disabled_role_keys={'note'})` 须含 `note_manage`；②关全部专家 → `exclude ⊇ 全部业务工具`；共加 4 条（EX-14~17）。
42. **专家探针 17/17 全绿**（原 13/13 + 新增 EX-14~17）。全量回归结论：**角色探针通过 / 指挥家 23/23 / 用户智能体 22/22**，`_toolpref_probe` 待看统计行。
43. **关键（`_probe_agent_role` 的 AR-15/16/17 不受方案 A 影响）**：这三条断言 `general` 的 `exclude` 只含元工具——因它们**未传 `disabled_role_keys`**（默认空集），故方案 A 生效后仍正确、无需改。改 `compute_exclude` 签名/语义后，先判断各调用点是否传新参数，再决定探针是否需动。
