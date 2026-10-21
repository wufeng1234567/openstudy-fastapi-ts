---
name: 智能体聊天页底部工具栏已收敛
description: 用户反馈输入区底部过密（9控件），已把配置三件套聚合进「设置」弹层，提交 0f3d21e
type: feedback
---

**智能体聊天页（`openstudy-vue3-ts/src/views/front/agent/chat.vue`）输入区底部工具栏不许堆砌过多控件。**

**Why:** 2026-10-09 用户反馈"不太美观、信息太密、超过设计原则"——当日该工具栏一度有 **9 个**分散控件（附件 / 知识库 / 历史会话 / 自动执行开关 / 智能体选择器 / 可用工具弹层 / 模型选择器 / 我的智能体 / 新对话）。智能体选择器 + 我的智能体按钮是当时新加的，把密度推过了临界点。用户对 UI 密度敏感。2026-10-10 用户在截图/交互层继续报出**视觉遮挡与冲突**问题（角标被悬浮助手盖、hover 伪类与输入框滚动条打架）——用户对**元素重叠/视觉碰撞**这类问题非常敏感，改 UI 位置时须预先核查与同页其他浮层（浮动按钮、滚动条、抽屉）的占位是否重叠。

**设置面板 UI 已优化（2026-10-10 用户新反馈，已落地并推送 `8cd8391`）**：用户嫌智能体**设置面板不好看**——输入框/控件与周围边框贴到一起（缺内边距）、留白偏多、整体缺内边距。根因=.settings 内容直接铺在 `.agent-panel-body`（无内边距）导致输入框贴抽屉/tab 边框。已改：给 `.settings-body` 加内边距 `18px 20px 24px`（原内容直接贴抽屉内壁）+ 收紧输入控件高度防撞边；把 `.settings-row` 由「左标签+右字段」**横排改为纵排**（标签在上、字段在下，删除 `.settings-label` 的 `flex:0 0 68px`）——纵排解决"窄标签列挤压输入框"致贴边，也更适合窄抽屉；再加 `max-width:560px`（抽屉被拉宽时表单不被拉散）。处理 UI 密度类需求时须兼顾"控件与边框的间距"和"整体留白"两端，勿只加间距而留白失衡。

**How to apply:** 已按"中度收敛"落地（提交 `0f3d21e`，已推 gitcode/main）：
- 新增一个**「设置」按钮 + `el-dialog` 设置弹层**，把「配置类三件套」——**智能体选择 + 模型（AiModelSelector）+ 可用工具开关**——聚合进去；「我的智能体」管理入口也收进弹层底部（低频操作）。
- 底部工具栏只留高频动作：**附件、知识库、历史会话、自动执行开关、设置、新对话**（9 → 6 个）。
- 移除常驻的「支持 Word/PDF…」提示文字；移除独立智能体选择器/我的智能体按钮/`AgentToolPopover` 入口（`AgentToolPopover` 组件保留未删，仅 chat.vue 不再用）。
- 设置弹层内工具开关为**受控式**，复用 `agentDsFree` 的 `fetchAgentToolsForUi` / `saveAgentToolPref`；chat.vue 内维护 `toolOptions`（含 `disabled`）+ `toggleToolInSettings`。
- 后续再往该输入区加控件/配置项时，**优先并入「设置」弹层**，不要新增常驻控件；底部常驻控件建议保持 ≤ 6 个。
- 前端验证方式：本环境 esbuild 不可用，用 `@vue/compiler-sfc`（parse + compileTemplate）+ `typescript`（createSourceFile 查 parseDiagnostics）三项佐证。
- 2026-10-10 用户继续要求**去掉智能体聊天页里「放大输入框/评论框」的按钮**（"去掉，不需要了，或者有没有更合理的摆放位置"）——延续"底部输入区不再堆控件、低频功能挪出底部"的方向；处理此类诉求时优先移除/迁出而非留在原地。
  - 「放大输入」按钮位于 `openstudy-vue3-ts/src/components/ChatInputArea/index.vue`（底部工具栏的 `.expand-btn`，点开是 `el-dialog` 大文本框）。评估结论：**该能力本身有价值（长文本输入是真需求），不该直接删**。
  - 用户 2026-10-10 已选定**方案 A**：从底部工具栏撤下「放大输入」按钮，改为**输入框（`input-text-layer`）右上角的绝对定位小角标图标**——既不丢能力、又不占底部工具栏排位。
  - 用户对「放大输入」的实现预期：**删除底部按钮 + 其 `el-dialog` 弹窗**，并注意清理可能残留的 `.toolbar-btn` 相关样式规则。
  - 通用原则：面对"要不要删/换位置"的 UI 问题时，用户接受先给判断+分方案（A/B/C）再动手；用户默认倾向**保留能力但挪出高频区**，而非粗暴删除。
- 2026-10-10 **方案 A 已落地实施**（`ChatInputArea/index.vue`）：底部工具栏的 `.expand-btn` 及其 `el-dialog` 大文本框弹窗已删除；改为在 `.input-text-layer`（作为定位基准，`position:relative`）内加 `.expand-corner` **绝对定位小角标**。
  - **角标位置几经反复，最终定为右上角（`top:2px; right:8px`）**：
    - 起初定为右下角（理由：右上角会盖住 textarea 首行文字末尾）；但 2026-10-10 用户反馈右下角**被默认悬浮助手（`AiAssistant` 浮动按钮，初始位置在窗口右下角 `window.innerWidth-76, window.innerHeight-130`）遮挡**，遂改回右上角。
    - 右上角仍与滚动条冲突：textarea `overflow-y:auto` 长文本时右侧滚动条贴文本区右缘，与贴 `right:0` 的角标竖直重叠，hover 背景块与滚动条视觉打架。
    - 正解：角标**不贴右边缘**，`top:2px; right:8px`（留出约 8px 滚动条宽度，滚动条在角标右侧、两者并排不叠）；同时给 textarea `padding-right:30px`（角标约 22px + 间隙）使文字与滚动条都不侵入角标区（注意 `padding-right` 只内推文字，**不会移动滚动条位置**）。
  - 角标视觉：**透明背景、hover 才显色**，浮于内容之上以降低视觉干扰。
  - 收尾动作：删除 `expand-btn` 残留样式（grep 确认样式区无残留，仅弹窗相关 `expand-*` 保留）；同步更新 `ChatInputArea/index.vue` 顶部注释（原第 13 行"放大输入对话框"入口位置描述）。
  - 改动仅 `ChatInputArea/index.vue` 一个文件；SFC 校验方式见本环境 esbuild 禁用后的一致做法（`@vue/compiler-sfc` + `typescript`）。
    - 已按 worktree 隔离流程提交并推送 main：提交 `c7836c1`（`33a126d..c7836c1`，hook PASSED），底部工具栏控件由 6 个进一步减到 **5 个**（独立「放大输入」图标按钮撤下）。**右上角修正另见提交 `0c0079e`（`c7836c1..0c0079e`，hook PASSED）**——即上文"角标位置几经反复，最终定为右上角（top:2px; right:8px）+ textarea padding-right:30px"的落地提交。
    - 收尾时同步修正 `ChatInputArea/index.vue` 的**模板注释**：第 14 行原写"右下角"、与最终右上角实现不符，已改为"右上角"；复查第 48-50 行注释本就写"右上角"，与实现一致、无需改。（改 UI 位置后务必核对相邻注释描述是否仍准确。）
- 2026-10-10 **底部执行统计条已整块移除**（用户裁决：本产品是学习系统、非开发工具，"N 轮 M 步 / LLM x ms / 首 token 平均"等 API 统计对用户是噪音）。落地：`chat.vue` 删 `<footer class="agent-foot">` 全块 + `.agent-foot`/`.foot-*` 样式 + 仅它用的 `formatMs`/`formatFirstToken`/`imageCount/corrections/errors/metrics/hasRun` 解构。**同批提交还含**：① 会话执行统计持久化（timeline 快照 `{messages, metrics}`，`useAgentChat` 的 `metricsSnapshot`/`restoreMetrics`——界面虽删但能力保留）；② **首 token 延迟优化**：`loop.py` 把启动期两次独立 DB 读（`build_runtime_context` 读记忆/知识库 + `list_agents` 读用户智能体通讯录）由**串行改 `asyncio.gather` 并行**，并抽 `_load_user_agent_briefing()`/`_async_empty_list()` 辅助函数（二者各自独立开会话，并行安全）。提交 `6c6a2bc`（`0c0079e..6c6a2bc`，hook PASSED）。**首 token 停顿的真相**：深度思考模型本身有网络+推理延迟，后端并行化只消除「可确定的串行 DB 等待」；若仍慢，属模型/网关层。
