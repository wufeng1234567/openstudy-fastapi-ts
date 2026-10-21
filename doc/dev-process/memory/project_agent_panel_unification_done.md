---
name: 智能体页容器统一为单抽屉+内部tab（已实施）
description: 设置/知识库/历史会话统一到一个 ResizableDrawer+tab；抽屉方向改为打开时锁定（不随 tab 变）；隐藏悬浮助手自检tab；提交 c1ed09a
type: project
---
2026-10-10 **已实施完成**智能体页容器统一（方案 A），提交 `c1ed09a`（`6c6a2bc..c1ed09a`，已推 gitcode/main）。

## 落地内容
- `views/front/agent/chat.vue`：三个功能（设置/知识库/历史会话）统一到**一个 `ResizableDrawer`** + 内部 **tab**（设置/知识库/历史），宽度持久化 key `openstudy_agent_panel_size`（defaultWidth 380、min300/max720）。
  - **抽屉方向：打开时锁定，不随 tab 变（2026-10-10 用户纠正后定案）**。用户指出：「无论是在哪里进入不同的 tab，抽屉方向都必须保持和当前一致」——在左侧入口打开抽屉后又切到「智能体设置」tab，抽屉不该跳到右侧。实现：`panelDirection` 由**计算属性（依赖 panelTab）改为普通 `ref`**，仅在**抽屉原本关闭、由入口按钮打开时**按入口侧设定一次：设置按钮（右入口）→ `rtl`、知识库/历史按钮（左入口）→ `ltr`；抽屉**已打开时切 tab（含点内部 tab 头、或点工具栏按钮走 `openPanel`）一律保持当前方向不动**。`openPanel` 内仅当「原本关闭」时才设方向。同时更新 template 中「方向由 panelDirection 按当前 tab 动态给出」的过时注释。
  - 删除：独立历史会话抽屉、设置 `el-dialog`、工具栏里的 `KnowledgeBaseDrawer` 组件引用。
  - 工具栏三入口 → `openPanel('settings'|'kb'|'history')`（开抽屉+切 tab+按需载入：settings 调 `loadToolOptions()`、kb 调 `kbPanelRef.activate()`）。
  - 知识库内容改用 `KnowledgeBasePanel`（与悬浮助手同一面板，`defineExpose({activate, refreshList, getKbCount})`）。
  - script 改名：`settingsVisible`/`historyOpen`/`openSettings` → `panelOpen`/`panelTab`/`openPanel`/`panelDirection`；`watch(historyOpen)` → `watch(panelTab)`（切到 history 清搜索词）；`switchSession`/`newSession` 关闭改 `panelOpen=false`；补 import `nextTick`；import `KnowledgeBasePanel` 替换 `KnowledgeBaseDrawer`。
  - 样式：新增 `.agent-panel`/`.agent-panel-tabs`/`.aptab`/`.agent-panel-body`/`.session-count-line`；删 `.session-drawer-header`。
- `components/AiAssistant/index.vue`：**隐藏「自检」tab** —— 删 tab 按钮、`DfSelfCheckPanel` 渲染分支、`switchToSelf`、`isDev`/`DfSelfCheckPanel` 定义、`Tools` 图标与 `defineAsyncComponent` import；`activeTab` 类型去掉 `'self'`；`selfCheckRunning` 保留（仍用于发送禁用 `:disabled`）。
- `KnowledgeBaseDrawer/index.vue` 组件文件**保留**（不再被 chat.vue 引用），避免连带删除风险。

**Why:** 三个容器形态各异（el-dialog vs 两套独立抽屉），统一为一个可拉伸抽屉 + tab 才能保证容器一致、逻辑自洽。**方向策略经用户两轮迭代**：初版「方向随入口侧动态变化」被用户否决——同一抽屉内切 tab 时抽屉横跳不合理；终版「方向由首次打开它的入口决定并锁定」。
**How to apply:** 智能体页后续新增辅助功能优先并入这一个抽屉的 tab；**抽屉方向一旦打开即固定，切 tab 不改方向**；不要再新建独立容器，也不要迁到全局悬浮助手 `AiAssistant`。
