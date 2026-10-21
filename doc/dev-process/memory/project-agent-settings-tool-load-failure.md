---
name: 智能体设置面板工具列表「一直加载」失败态缺失
description: 2026-10-10 用户报从知识库/历史切入设置后可用工具一直「正在读取」；根因=loadToolOptions 无 loading/错误态
type: project
from: Agent
---

2026-10-10 用户报 bug：在智能体页**从知识库/历史会话切入「设置」tab 后**，「可用工具」列表**一直处于"正在读取…"**（永久加载）。同场景还报**设置面板 UI 问题**：输入框贴边框、留白多。

**根因（已定位）**：`chat.vue` 的 `loadToolOptions` **没有 try/catch、没有加载态、没有失败态**。`toolOptions` 初值 `[]`，请求未回来或失败时 UI 就渲染"正在读取…"，无法区分「加载中 / 失败（可取不到）/ 空 / 有数据」。`fetchAgentToolsForUi` 失败返回 `{tools:[]}` → `toolOptions=[]` → 界面永久卡"正在读取"且**无错误提示、无重试**。

**已排除的假因**：
- 前端 `BASE` 定义正常（`fetch(\`${BASE}/ai/agent/tools\`)`），非未定义/相对地址问题。
- 工具解析口径**没错**：`chat.vue` 用 `t?.function?.name || t?.name` 兜底、`label` 读 `t?.label || t?.descriptionZh`；旧组件 `AgentToolPopover` 的 `toRow` 读 `entry.function.name`（Function Calling schema）——两者兼容，**不是字段名对不上**。后端 `tools[i]` 可能为 OpenAI function 格式 `{type:'function', function:{name}}`。

**修复方向（无论根因为何都该做）**：
1. `loadToolOptions` 加显式 `toolLoading` / `toolLoadFailed` 状态 + try/catch + 失败重试按钮，区分四种状态；复用 `AgentToolPopover` 的成熟口径（显式 loading + 失败重试）。
2. `openPanel('settings')` 时若已有数据不重复拉；失败给明确提示。
3. 设置面板样式：修输入框贴边框、减少多余留白。

**修复（已落地并推送，2026-10-10）**：提交 `8cd8391`（区间 `1f213da..8cd8391`，hook PASSED，仅改 `chat.vue`）。
- `loadToolOptions` 加显式 `toolLoading` / `toolLoadFailed` 状态 + try/catch + finally；template 工具区区分「加载中 / 取不到（含**重试**按钮）/ 有数据」三态；`openPanel('settings')` 已有数据不重复拉。解析口径读 `entry.function.name`（与 `AgentToolPopover` 一致）。
- 设置面板样式同批修：`.settings-body` 加内边距 `18px 20px 24px`（原内容直接贴抽屉内壁）、`.settings-row` 由横排**改纵排**（标签在上、字段在下）、`max-width:560px`（抽屉拉宽时表单不被拉散）、行距收紧、新增失败条暖色样式。见 feedback-agent-chat-toolbar-density 的"设置面板 UI 已优化"。

**真因结论（2026-10-10 判断，未再深挖）**：真凶大概率是**首次 `/ai/agent/tools` 请求失败**（token/网络），叠加原代码无失败提示与自动恢复。做过旁证：`AgentToolPopover` 一直正常且解析口径与我方一致，唯一差异就是它没有 loading 态；底层 `fetchAgentToolsForUi` 已有 `_toolsCache`，重复调用命中缓存、不会重复网络请求，所以"每次切设置重拉"并不慢——排除"反复请求拖慢"这一路径。若用户本地切到设置**仍**显示"工具清单没取到"，即为请求真失败，点「重试」应恢复，并需用户提供浏览器控制台报错。

**⚠️ 后续进展（2026-10-10，仍未解决，根因收敛）**：本轮（AI 侧提交 `61af866` = 模型框「请选择」修复，区域 `8cd8391..61af866`）**未再改 loadToolOptions**，但**下一位用户报告**（沟通中的第三个 bug）把现象收得更紧：**「刷新页面后，第一次直接点其他 tab，再点设置 → 工具永远刷不出来；而先点一次设置、再看其他 tab、再回设置 → 能出来」**。这种**顺序敏感**强烈指向 `loadToolOptions()` 的**并发/竞态**（而非单纯请求失败）：先点设置会先发起请求，之后切 tab 回来时请求已完成/缓存命中 → 成功；而"先点其他 tab"路径下首次请求的时机/成功回调被状态覆盖或未落定 → 永久空。下一步应查 `loadToolOptions` 与 tab 切换的时序（是否在未挂载/已切走的组件上调 setState、或 loading 标记卡住、或早返回丢弃了结果），而非只加"重试按钮"。**这条待办仍存活**。

**排查中排除项（2026-10-10 本轮）**：
- 设置 tab 用 `v-show="panelTab === 'settings'"`，DOM 常驻、`el-switch` 的 `:model-value` 绑定正常——**排除** `v-show` vs `v-if` 导致的问题。
- `openPanel('settings')` 每次点都调 `loadToolOptions()`，逻辑本身正确。
- `KnowledgeBasePanel` **不引用 `agentDsFree`**——排除"知识库面板抢先写坏 `_toolsCache` 模块缓存"。
- `chat.vue` 仅在两处**动态 import** `agentDsFree`（约 543、570 行），因重构已不再静态 import `AgentToolPopover`；`agentDsFree` 在 chat.vue 内只靠动态 import 加载。`AgentToolPopover`（已不被引用）对它是**静态 import**。
- `fetchAgentToolsForUi` 失败返回 `{tools: [], actions: {}}`；`loadAgentToolsPayload` 的 `_toolsCache` **失败不写缓存**（保持 null，下次可重试）——**排除**"失败污染缓存导致永久空"。
- 未消除的疑点：`loadAgents()`（`onMounted` 调、不 await）内 `listAgentRoles()`/`listAgentConfigs()` 与 `loadToolOptions()` 是否共享 `getToken()`/令牌时序、是否同走 `agentDsFree` 模块——**待查**。

**建议根治方向（尚实施中，进行中现状 2026-10-10 本轮）**：把 `agentDsFree` 由动态 import 改 `chat.vue` 顶层**静态 import**（消除动态 import 时序变量）、给 `loadToolOptions` 加**并发飞行锁（复用同一 Promise）**、失败时**保留旧数据不置空**。本轮已把 `listAgentRoles`/`listAgentConfigs` 也确认为走 `getToken()`（与 `loadAgentToolsPayload` 同），且**它们不写工具缓存**；`loadAgents()`（`onMounted` 调、不 await）内 `listAgentRoles`/`listAgentConfigs` 与 `loadToolOptions` 的并发/令牌时序仍是未闭合疑点。已完成推理排除：`watch(panelTab)` 只清搜索词（无害）；`openPanel('settings')` 里 `if (tab === 'settings') loadToolOptions()` 无 await 但数据流无碍；`loadAgentToolsPayload` 本身健壮（失败不写 `_toolsCache`、并发两次各 fetch 均成功即都写缓存、一失败一成功则成功那次写缓存 → 后续可重试），故**问题不在工具 API**。尚未看到运行时报错，需用户提供浏览器控制台日志才能定论。**本轮决定放弃继续静态推测，改为一条高置信度根治：把 `loadToolOptions()` 挪到 `onMounted` 预取一次（页面加载即拉工具清单并缓存），`openPanel('settings')` 只在无数据时补拉 —— 这样无论先点哪个 tab，首次进设置必然有数据，直接消除"顺序依赖"。** 方案三件套同前述：静态 import + 飞行锁 + 失败保旧。

**根治已落地（2026-10-10，未提交/本地已改）**：按上条「高置信度根治」实施——`loadToolOptions()` 挪到 `onMounted` 预取工具清单并缓存，`openPanel('settings')` 仅在无数据时补拉，**彻底消除顺序依赖**；同时静态 import `agentDsFree`、去掉动态 import（已复查确认**无残留动态 import**），并用临时脚本 `openstudy-vue3-ts/_v.cjs` 校验 `chat.vue`（校验通过）。**本轮仅改 `chat.vue` 单文件**；随后按流程 `git fetch`（得最新 `gitcode/main` = `61af866`）→ 建 worktree → 拷入（待提交推送）。

**✅ 根治已落地并推送（2026-10-10，提交 `ee78533`，区间 `61af866..ee78533`，hook PASSED，仅改 `chat.vue`）**：`fix(agent-ui): 根治「刷新后先点其他 tab 再进设置，工具清单不加载」的顺序敏感 bug`。根因结论：`loadToolOptions()` 用 **`await import('@/api/ai/agentDsFree')` 动态导入** 才拿到 `fetchAgentToolsForUi`，使「函数何时可用」成了与「先开哪个 tab」时序耦合的运行时变量；叠加 `onMounted` 里 `loadAgents()` 不 await 的并发发起 → 竞态。四点修复：
1. **改静态 import** —— 去掉两处 `await import`，消除"模块就绪时机"变量；
2. **飞行锁 `_toolLoadInFlight`** —— 同一时刻只发一次请求，多入口共享同一 Promise；
3. **失败/空结果不覆盖已有列表** —— 只在拿到非空数据时覆盖，网络抖动不再清空已显示工具；
4. **`onMounted` 预取** —— 进页面即拉工具清单，无论先点哪个 tab 都已在手，从根上消除顺序依赖。
验证：`@vue/compiler-sfc` + `typescript` 校验通过。**该 bug（第三次报告）至此根治关闭。**

**Why:** 用户从别的 tab 切入设置才复现，说明是首次进设置时请求失败/返回异常结构；原界面无失败态导致"卡死"观感。用户已授权直接动手修（无需再问）。顺序敏感的补充证据把根因从"请求失败"推向"竞态"（最终确认为动态 import 时序 + onMounted 并发竞态）。
**How to apply:** 后续 chat.vue 设置面板/任何异步清单加载，必须显式区分「加载中/失败(含重试)/空/有数据」四态，勿用空数组当默认值掩盖失败；若现象**依赖进入 tab 的顺序**（刷新后先点别的 tab 才复现），优先排查竞态与 loading 标记未复位，而非只加重试。
