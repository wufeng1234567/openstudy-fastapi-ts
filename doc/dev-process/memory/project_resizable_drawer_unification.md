---
name: 抽取 ResizableDrawer 公共组件统一抽屉容器
description: 用户已定案把可拖拽拉伸抽屉抽成公共组件 ResizableDrawer；知识库/历史会话复用，设置保留 el-dialog 不动
type: project
from: Agent
---

2026-10-10 用户提出：把「悬浮助手」（`openstudy-vue3-ts/src/components/AiAssistant/index.vue`）中基于 `el-drawer` + 自研 `startDrawerResize` 的**可拖拽拉伸抽屉容器**提炼为**公共组件** `components/ResizableDrawer/index.vue`，让多处复用（诉求：样式/交互统一）。

**用户已定案的终版方案（2026-10-10）**：
1. 新建 `ResizableDrawer` 公共容器（支持 rtl/ltr、可拉伸、宽度持久化可选、过渡关停、可选滚动锚点）。
2. **知识库** → 迁到 `ResizableDrawer`（**左侧 ltr**、可拉伸、带 storageKey）。原先迁入时为右侧 rtl，2026-10-10 用户提出「入口在哪、面板就从哪滑出」是一致性原则——历史会话与知识库按钮都在底部左侧，两处抽屉都从左侧滑出；已随提交 `33a126d` 落地（`direction` 由 `rtl`→`ltr`，宽度持久化 key `openstudy_kb_drawer_size`、默认宽度、`@open` 行为均不变，`KnowledgeBasePanel` 内部含「收起」按钮与方向无关无需改）。设置按钮在右侧，将来若把「设置」改抽屉应自右侧滑出；目前仍是居中 `el-dialog`，无需改。

2026-10-10 用户提出「入口在哪面板就在哪」的一致性理由（历史会话按钮与知识库按钮都在左侧工具栏），遂改 `direction="rtl"` → `"ltr"`；min/max/defaultWidth 与持久化 key `openstudy_kb_drawer_size` 不变。取舍：知识库面板较宽，放左侧向右扩会盖住对话区，但属按需唤起可接受。
3. **历史会话** → 从 `.session-popover` 浮层迁到 `ResizableDrawer`（**左侧 ltr**，会话列表在左更直觉，可拉伸）。
4. **设置** → ~~保留 `el-dialog` 不动~~（**该取舍已被 2026-10-10 终局方案 A 推翻**：设置也统一进智能体页自有 `ResizableDrawer` 的 settings tab，旧设置 `el-dialog` 已从 chat.vue 整块删除，见 `project-agent-page-drawer-tab-unification.md`）。

**悬浮助手那套拉伸实现的关键特性（复用点）**：rAF 节流 + 直接写 DOM 宽度（不进 Vue 渲染管线）、拖拽期关闭 `transition`、滚动锚点保持（拖消息不跳位）、localStorage 宽度持久化、min/max 边界钳制。

**实现要点/坑**：
- 拖拽方向不同：rtl 向左拖变宽 `delta = startX - clientX`；ltr 向右拖变宽 `delta = clientX - startX`。
- 定位 `el-drawer` 根节点用**唯一随机 `drawerClass`**（模板 `:class` 绑定 `rd-drawer rd-{direction} ${drawerClass}`），`getDrawerEl` 用 `.rd-drawer.${drawerClass}` 精确命中；**不要**用 `document.querySelector` 模糊查找「当前方向最新抽屉」（多抽屉同方向会取错），也无需 `bindDrawerClass`。
- `ResizableDrawer` 用 `v-model` 开合、内建 `append-to-body`、emit `open` 事件（迁 `KnowledgeBaseDrawer` 时 `@open` 保留）。
- `KnowledgeBaseDrawer` 结构 = 「入口按钮 + 抽屉外壳」，迁移即把 `el-drawer` 换成 `ResizableDrawer`，入口按钮不变。

**迁移落地要点（2026-10-10）**：
- 知识库抽屉：移除 `KnowledgeBaseDrawer` 中 `.kb-drawer` 专属 `<style>` 块——body padding/overflow 已由 `ResizableDrawer` 的 `.rd-drawer .el-drawer__body`（`padding:0; overflow:hidden; position:relative`）接管；grep 确认 `KnowledgeBasePanel` 不依赖 `.kb-drawer` 样式，删除安全。
- 历史会话：`chat.vue` 从 `.session-popover` 浮层改左侧 `ResizableDrawer`；原「历史会话」按钮 `toggleHistory` 改 `historyOpen = true`，去掉 `@mousedown.stop`；移除 `onDocMousedown`、清理 `sessionPopoverRef` 及 `toggleHistory` 定义（含其它浮层逻辑，抽屉自带遮罩关闭）；原本挂在 footer 内的会话列表 markup 整体搬到抽屉 slot，抽屉放在根元素内与「设置」dialog 同级。
- 原 `toggleHistory` 承担「打开时清空搜索词」的副作用随其删除而丢失，**须改用 `watch(historyOpen, v => v && (sessionKeyword.value=''))` 保留该行为**。
- `watch` 需从 vue 显式 import（chat.vue 原 import 区未含 `watch`）；`watch(...)` 放在 `setup` 作用域中段（如 `formatTime` 前）是合法位置，不必强行挪到顶部 import 后。
- `ResizableDrawer` 需在 chat.vue import 区显式引入；旧 `.session-popover` 样式块整体删除，改加历史抽屉专属样式。

**scoped 样式穿透结论（2026-10-10）**：`ResizableDrawer` 的 slot 内容虽经 `append-to-body` 渲染进 `el-drawer`（脱离组件 DOM 层级），但 slot 内容的 DOM 仍由**调用方组件**（如 chat.vue）模板渲染，带调用方的 `data-v-xxx`，因此 `chat.vue` 的 `scoped` 样式**可以**命中抽屉内 `.session-item` 等元素——`append-to-body` 不影响 scoped 命中，无需 `:deep()`。

**收尾（2026-10-10）：本次提交含 3 个文件——新增 `ResizableDrawer/index.vue`，修改 `KnowledgeBaseDrawer/index.vue`、`chat.vue`（chat.vue 从 fetch 后的 gitcode/main 基线 `0f3d21e`——即"UI 收敛"那次提交——建 worktree 提交）。**
- 浮层 `.session-popover` 删除后，`chat.vue` 中与之相关的过时**注释**需一并清理（实例：第 24 行注释描述了已删的浮层）。`grep session-popover` 仅命中第 24 行，说明模板删除时已连带清了 toolbar 注释里的引用；若 grep 无残留即无需再动。
- 顶部大段注释（约 35/37 行）提到"历史会话"**入口**，该入口仍存在，注释仍然准确，**不要**误删。
- 残留仅在 `AiAssistant`（悬浮助手**自己的**历史会话面板，本次未要求改，保留）。
**拉伸手柄定位基准**：`.rd-resize-handle` 与 `.rd-body` 同为 `el-drawer` 默认 slot 内容，插在 `.el-drawer__body` 内，其 `position:absolute` 的定位基准即 `.el-drawer__body`（`ResizableDrawer` 已设 `position:relative`），故手柄与 body 可正确对齐。

**终局定案（2026-10-10，覆盖上条「设置保留 el-dialog」）**：用户选定**方案 A**——把智能体页（`views/front/agent/chat.vue`）的「设置 / 知识库 / 历史会话」全部统一到**智能体页自己的 `ResizableDrawer`** 容器，内部用 **tab 切换**（设置 / 知识库 / 历史）；点工具栏对应按钮 → 开抽屉 + 切到对应 tab；并把工具栏的「自检」tab **隐藏**。
- 用户明确否决「让全局悬浮助手 `AiAssistant` 承载智能体页设置/知识库/历史」的设想（原方案 B），理由：AiAssistant 是全局悬浮助手、智能体页是独立全屏页，借它弹抽屉会在独立大屏页里弹出小助手导致**上下文割裂**；抽屉方向矛盾（AiAssistant 抽屉 rtl 右侧，而智能体页入口在左侧）；且 AiAssistant 的 tab 体系是「对话/我的题库/我的知识库」，既无「设置」也无「历史会话」（历史是它的 `sessionListVisible` 浮层），tb 不匹配。另有既有事实：AiAssistant 的「我的知识库」tab 与智能体页抽屉用的是**同一 `KnowledgeBasePanel` 组件**（功能本已重复）。
- 后续如需再统一容器形态，沿用此方向：统一到**页面自有抽屉 + 内部 tab**，而非借用全局悬浮助手。

**Why:** 用户目标是把形态各异的容器统一为同一套可拉伸抽屉，做样式与交互一致性优化；悬浮助手的拉伸实现质量高、复用价值大。选择页面自有抽屉而非全局悬浮助手，是为避免上下文割裂与方向矛盾，真正解决"3 个独立容器形态不一"的问题。
**How to apply:** 公共容器必须与具体面板解耦（slot 驱动，内容由调用方提供）；设置类轻量弹层保持 `el-dialog`，勿强行做成大抽屉。
