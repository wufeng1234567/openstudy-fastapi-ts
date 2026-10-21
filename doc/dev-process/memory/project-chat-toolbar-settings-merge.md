---
name: chat.vue 工具栏中度合并为单一「设置」弹层
description: 2026-10-10 chat.vue 把散落工具按钮合并进设置弹层；AgentToolPopover 保留但不再被引用
type: project
from: Agent
---

2026-10-10 决定在 `openstudy-vue3-ts/src/views/front/agent/chat.vue` 做**中度合并**：把原先散落的工具栏控件收进一个**新增的「设置」`el-popover`/弹层**，内含三段——① 智能体选择（`el-select` 分组）② 模型（`AiModelSelector`）③ 可用工具（**内联精简开关列表**）。

- **移除**：独立智能体选择器、右侧独立 `AiModelSelector`、"我的智能体"独立按钮、独立 `AgentToolPopover` 按钮、常驻 `footer-hint`。
- **保留**：附件、知识库、历史、自动执行、新对话。
- **AgentToolPopover 组件不删**（别处可能引用），但 chat.vue 不再使用它；设置弹层里的"可用工具"改为**内联自包含列表**（~40-50 行），复用 `fetchAgentToolsForUi` / `saveAgentToolPref`，但**去掉搜索/全选**以保持简洁。
- `toolOptions` 原只有 `{name,label}`，需扩展带 `disabled` 状态；需改 `loadToolOptions` 保留完整 payload。新增 `settingsVisible` 状态与 `openSettings`（打开弹层 + 拉起工具清单，复用 `loadToolOptions`）。
- `AiModelSelector` import 需保留（设置弹层内用）；`AgentToolPopover` import 可移除。

**约束**：用户明确要求"**中度合并**"——不重写/不动其他组件；`AgentToolPopover` 是否只被 chat.vue 引用已确认（`agent.ts` 中仅注释性提及），故保留组件但不引用是可接受的。

**Why:** 现工具栏按钮过多、拥挤；集中在设置弹层里更整洁，但用户警惕大改（对破坏性模板替换有心理阴影——历史曾误删 `.tb-new` 区块）。
**How to apply:** 后续若继续收敛 chat.vue 工具栏，遵循"按钮收进设置弹层 + 组件保留不删"的思路；改大段 template 时格外小心。
