---
name: ResizableDrawer 通用可拖拽抽屉容器
description: 提炼自悬浮助手的可拉伸右侧抽屉容器，知识库/历史会话已复用，提交 56f63b1
type: project
---

2026-10-09 提炼出**可拖拽调宽的通用抽屉容器** `openstudy-vue3-ts/src/components/ResizableDrawer/index.vue`（提交 `56f63b1`，已推 gitcode/main），统一智能体页抽屉交互。2026-10-10 知识库抽屉方向由 `rtl`→`ltr` 的修正已作为提交 `33a126d` 推到 main（tip `56f63b1..33a126d`）。

## 来源与能力（提炼自 `AiAssistant/index.vue` 的抽屉实现）
- 拖拽调宽：**rAF 节流 + 拖拽期间直接写 DOM 宽度**（`el.style.width`），**不更新响应式 ref**——改 ref 会每帧 diff 整个组件，消息多时拖动卡顿。
- 拖拽期关闭 el-drawer 的 `transition`（否则跟手性差）；加官方 `is-dragging` 类。
- **可选**滚动锚点（传 `anchorSelector` 才启用）：拖拽时记住"视口顶部那条消息"，松手后复原。
- **可选**宽度持久化（传 `storageKey` 才读写 localStorage）。
- 纯容器：内容全走默认插槽；`defineExpose({open,close,getWidth})`。
- **多抽屉同方向不串**：用唯一随机 class 精确定位自身 DOM（`append-to-body` 后不在组件树内）。

## Props
`modelValue`(v-model) / `direction`('rtl'|'ltr'，默认 rtl) / `resizable`(默认 true) / `min`(320) / `max`(900) / `defaultWidth`(520) / `storageKey`('') / `anchorSelector`('')。派发 `update:modelValue` 与 `open` 事件。

## 已复用
- **知识库**（`KnowledgeBaseDrawer`）：`el-drawer` 固定 560px → `ResizableDrawer`（**ltr 左侧**、可拉伸、key `openstudy_kb_drawer_size`）。2026-10-10 由 rtl 改为 ltr，与同处左侧工具栏的历史会话按钮保持一致。**2026-10-10 终局：设置/知识库/历史统一进智能体页统一抽屉的 tab 后，`KnowledgeBaseDrawer` 组件文件已无人引用（知识库改用 `KnowledgeBasePanel`），用户定案保留组件文件不删（避免连带风险），chat.vue 不再 import 它。**
- **历史会话**（`chat.vue`）：从输入框上方浮层 `.session-popover` → **左侧** `ResizableDrawer`（ltr、key `openstudy_agent_history_size`、min240/max600/default300）；随之删除 `sessionPopoverRef`/`onDocMousedown`/`toggleHistory` 及 document 级 mousedown 监听，清搜索词改 `watch(historyOpen)`。
- **设置**（2026-10-10 终局方案 A 落地中）：设置已不再用 `el-dialog`，改为并入智能体页统一 `ResizableDrawer` 的 settings tab；旧设置 `el-dialog` 正从 chat.vue 整块删除（原 277-340）。⚠️ 2026-10-10 用户补充定案「入口按钮在哪一侧、抽屉就从哪一侧滑出」：智能体页三入口统一到一个 `ResizableDrawer` 后，其 `direction` 须随激活 tab 动态切换（设置→`rtl` 右滑出、知识库/历史→`ltr` 左滑出，因设置入口在右侧 `#input-toolbar-right`、知识库/历史入口在左侧 `#input-footer`）。`direction` 若由调用方随 tab 动态绑定，需确认其响应式生效、el-drawer 换向平滑过渡。详见 `project-agent-page-drawer-tab-unification.md`。

**Why:** 用户要求把悬浮助手的可拉伸抽屉提炼为公共容器，统一智能体页的抽屉交互与观感（解决"样式不统一"）。
**How to apply:** 后续智能体页/其他页需要"右侧或左侧、可调宽、不占布局"的面板时，一律用 `ResizableDrawer`（内容走 slot），不要再各写一套 el-drawer / 浮层 / dialog；固定宽度的小面板可传 `:resizable="false"`。
