---
name: 智能体页容器统一为单一抽屉+内部tab并隐藏自检tab
description: 2026-10-10 用户定案智能体页设置/知识库/历史会话统一到自带 ResizableDrawer 的 tab；抽屉方向改「打开时锁定」；隐藏自检tab
type: project
from: Agent
---

2026-10-10 用户定案智能体页（`openstudy-vue3-ts/src/views/front/agent/chat.vue`）容器统一方案（**方案 A**）：

- 把原有的「设置 / 知识库 / 历史会话」**三个形态各异的独立容器**统一到**智能体页自己的 `ResizableDrawer`**，抽屉内部用 **tab 切换**（设置 / 知识库 / 历史）。
- 交互：点工具栏对应按钮 → 开抽屉 + 自动切到对应 tab（按钮与 tab 一一对应）。
- 同时**隐藏工具栏的「自检」tab**（此项无争议、立即做）。

**用户否决的备选方案**：不让全局悬浮助手 `AiAssistant` 充当这些功能的统一承载容器。否决理由：上下文割裂（全局悬浮小助手 vs 独立全屏页）、AiAssistant 的 tab 体系（对话/我的题库/我的知识库）没有「设置」「历史会话」且结构不匹配。

**抽屉方向策略（2026-10-10 用户最终纠正，终版）**：用户原话「无论是在哪里进入不同的 tab 出现的抽屉方向 都必须保持和当前一致，比如你在左侧点开进入的知识库页面、然后又点击了智能体设置 tab，此时抽屉会变到右侧去，这一点并不合理」。据此定案：**抽屉方向在打开时由入口侧锁定，内部切 tab 一律不改方向**。落地：`panelDirection` 从「依赖 `panelTab` 的计算属性」改为**普通 `ref`**，仅在**抽屉原本关闭、由入口按钮打开时**设一次（设置入口在右 → `rtl`；知识库/历史入口在左 → `ltr`）；`openPanel` 内仅当「原本关闭」才设方向。**这一终版推翻了此前「方向随激活 tab 动态变化」的定案**（旧因：三个入口分处两侧、el-drawer direction 支持动态改；现因：同抽屉内切 tab 改方向导致抽屉横跳，破坏「同一个容器」心智，故不可接受）。

**执行进展（2026-10-10）**：方案 A 已落地实施——设置弹层内容复制进统一抽屉的 settings tab，随后从 `chat.vue` **整块删除旧的设置 `el-dialog`**（原 277-340 行；含「我的智能体」管理内联弹窗仍另立）。删除时用唯一注释起止点精确匹配整块替换为空，**不要用 `deleteFile`**（只能删文件不能删片段）。说明"设置保留 `el-dialog`"的旧取舍已被彻底推翻、设置也进抽屉 tab。

**自检 tab 彻底删除（2026-10-10 实执行完成）**：自检 tab 位于**全局悬浮小助手 `AiAssistant`**（非智能体页），用户定案彻底不显示。在 `AiAssistant/index.vue` 中实际删除清单——自检面板定义块（约 240-254 行）+ script 层 `defineAsyncComponent` 导入（约 209）、`Tools` icon 导入（约 213）、`activeTab` 类型的 `'self'` 字面量（约 245）、`switchToSelf` 方法（约 695-697）。**仅保留 `selfCheckRunning`**，因其仍被第 139 行的 `:disabled` 使用。**坑**：`DfSelfCheckPanel` 定义删除后，渲染分支若未先删会编译报未定义——务必先删使用处再删定义。

**script 层状态收敛细节（2026-10-10）**：原三个独立状态（`settingsVisible`≈ch534 / `openSettings`≈ch540 / `historyOpen`≈ch617，及 watch 673、两处 `historyOpen.value = false`≈ch710/757）统一为 **`panelOpen`（开合）+ `panelTab`（'settings'|'kb'|'history'，决定内容）+ `panelDirection`（ref，开抽屉时锁定方向）**；`openSettings()` 改为 `openPanel(tab)`。原 `watch(historyOpen)`（打开时清空搜索词）须随之迁移到 `watch(panelOpen)` 上保留该副作用。实施中已确认：`KnowledgeBasePanel` 有 `activate` 方法（`nextTick` 后调用）、`ResizableDrawer`/`watch` 已在 chat.vue import 区。**删除旧容器时用唯一注释起止点整块替换为空，禁用 `deleteFile`（其只能删文件不能删片段）。**

**本轮收尾（2026-10-10）**：本轮改动两个文件——`chat.vue` 与 `AiAssistant/index.vue`。`KnowledgeBaseDrawer` 组件文件**保留不删**（避免连带风险），chat.vue 不再 import 它。因本次纯前端，判定 `app.main` 不受影响、跳过后端探针，仅做前端校验。远程 tip 为 `6c6a2bc`（上一轮 metrics+删状态条+并行化），本轮在其上追加 `chat.vue` 改动 + AiAssistant 新改，建 worktree 核对差异后再提交。

**抽屉方向横跳已修复并推送（2026-10-10）**：提交 `1f213da`（`fix(agent-ui): 抽屉方向打开后锁定，切 tab 不再横跳`，推送 `c1ed09a..1f213da HEAD -> main`，hook PASSED）。落地方式正是上文终版：`panelDirection` 由 `computed(() => panelTab==='settings' ? 'rtl' : 'ltr')` 改为普通 `ref`，新增 `dirOfTab(tab)`，`openPanel(tab)` 中**仅当抽屉原本关闭时**才设方向（设置入口→rtl、知识库/历史入口→ltr）；已打开时（点内部 tab 头或另一工具栏按钮）只切内容、不动方向。**注意**：此提交是"仅改 chat.vue 单文件推送"之外的额外一轮——本轮修复发生在容器统一 `c1ed09a` 之后，为独立小提交。

**待办（2026-10-10 用户新报，尚未处理）**：用户指出智能体**设置面板 UI 要优化**——输入框/控件与周围边框贴到一起（缺内边距，拥挤）、周边空白偏多；另报**工具读取 bug**——从知识库或历史会话切入智能体设置后，设置里的**工具列表一直处于加载状态**。Agent 已定位到疑似根因：`loadToolOptions()` 中 `toolOptions.value = (payload?.tools || [])...`，若 `fetchAgentToolsForUi()` 请求失败/返回异常则 `payload?.tools` 为 undefined → 被赋成**空数组** → 因模板 `v-if="!toolOptions.length"` 永久显示"正在读取工具清单…"且无重试；而 `openPanel('settings')` 每次都调 `loadToolOptions()`，故首次失败后一直空。下一步须核对 `fetchAgentToolsForUi` 签名（是否抛异常/返回非预期结构）。

**Why:** 现有三个容器形态不一，统一为同一抽屉+tab 可保证容器一致、逻辑自洽；同时避免与全局悬浮助手耦合而牵连其他页面。方向「打开即锁定」满足用户对「同一个抽屉」视觉稳定性的要求。
**How to apply:** 智能体页后续新增辅助功能优先并入这一个抽屉的 tab，而非再新建独立容器；**抽屉方向不随 tab 变更**；不要把这些功能迁到全局悬浮助手 `AiAssistant` 中。
