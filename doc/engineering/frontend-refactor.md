# 前端大文件解耦记录

目标：把超过 1000 行的前端文件按职责拆成可复用的 composable、纯工具模块和展示组件，先处理业务核心链路，再逐步覆盖题库、英语、笔记和智能体页面。

## 执行队列（历史顺序，当前状态见技术债务登记）

以下是 2026-11-12 的执行顺序快照；当前行数与完成状态以 `doc/quality/technical-debt-register.md` 为准：

| 顺序 | 文件 | 当前行数 | 状态 |
|---:|---|---:|---|
| 1 | `views/front/workspace/index.vue` | 1000 | 完成 |
| 2 | `components/PracticeComponent/PracticeComponent.vue` | 1000 | 完成 |
| 3 | `views/front/studio/components/QuestionBuilder.vue` | 1358 | 已完成（当时记录 2337） |
| 4 | `views/front/workspace/components/KnowledgeWikiPanel.vue` | 1996 | 已完成（当时记录 2853） |
| 5 | `views/front/english/listening/index.vue` | 1981 | 已完成（当时记录 2034） |
| 6 | `views/front/english/ocr/index.vue` | 1372 | 已完成（当时记录 1395） |
| 7 | `views/front/agent/chat.vue` | 1375 | 已完成（当时记录 1383） |
| 8 | 其余 >1000 行文件 | — | 按行数继续 |

> `workspace/index.vue` 当前已拆出 `WorkspaceChrome.vue`、`WorkspaceCascade.vue`、`useWorkspaceUpload.ts`；继续拆整理、编辑、刨析和导入模块。

### 目录约定

- `views/`：只做页面编排和路由参数接入；
- `components/`：展示子组件，props/emits 对外；
- `composables/`：状态、副作用、接口轮询、生命周期；
- `utils/`：纯函数、格式化、几何/类型映射；
- `styles/`：页面样式模块。

`workspace` 已按此结构整理：`components/`、`composables/`、`utils/`、`styles/`。

### 组件包目录规范（2026-11-13 执行）

多文件组件包统一采用：

```text
components/<Feature>/
  <Feature>.vue 或 index.vue   # 唯一公开入口，留在根层
  components/                  # 子展示组件，只放 .vue
  composables/                 # use* 状态/副作用
  utils/                       # 无 Vue 依赖的纯函数、类型映射
  styles/                      # .css/.scss
```

本次已规整：

- `PracticeComponent/`：主组件留在根层；11 个子组件进 `components/`，23 个 `usePractice*.ts` 进 `composables/`，`practiceQuestionUtils.ts` 进 `utils/`，2 个样式进 `styles/`；
- `Crontab/`：`index.vue` 留在根层，8 个日历子组件进 `components/`；
- `CommentSection/`：`CommentSection.vue` 留在根层，4 个子组件进 `components/`，`mention.ts` 进 `utils/`；
- `MyQuestion/`：`MyQuestion.vue` 留在根层，3 个子组件进 `components/`，样式进 `styles/`。

所有相对 import、`@/components/...` 别名 import 与 `<style src>` 已同步更新；`npm run build:prod`、`npm run test:unit`、composable import guard 和练习页 runtime smoke 均通过。目录规范由 `scripts/check_frontend_structure.py` 校验，并接入 `scripts/verify-quality.bat`。

第二轮（同日）把其余同类问题一并清理：

- 12 个单组件包的根层 `.css/.scss` 全部移入各自的 `styles/`；
- `AgentToolResult` 的 `useAgentToolJumps.ts` 移入 `composables/`，`agentToolResultSummary.ts` 移入 `utils/`；
- `AiChatStream`、`IconSelect`、`SvgIcon` 的根层工具 `.ts` 移入 `utils/`；
- `GlobalSettings` 的 `AgentManagerDialog.vue` 移入 `components/`。

现在 `src/components` 下每个功能包根层只保留一个公开入口（`index.vue` 或 `<Feature>.vue`），不再把子组件、composable、工具函数和样式全部堆在根层。

## 拆分原则

1. **纯函数进 `*.ts`**：颜色/类型映射、状态文案、几何计算等不依赖 Vue 实例的逻辑；
2. **状态与副作用进 composable**：搜索、轮询、筛选、导航等逻辑用显式参数注入，避免隐式全局依赖；
3. **模板按职责拆子组件**：一个子组件只接收自己的 props，通过 emits 回传动作；
4. **样式保持既有作用域**：`index.scss` 是全局样式时继续复用，避免拆分后视觉回归；
5. **每批改完必须通过 `npm run build:prod`，并做关键页面 DOM/交互回归**；
6. **ESLint 增加 `max-lines` warning**，先暴露存量，模块拆完后逐步收紧。

## 第一批（本次）

| 原文件 | 拆分结果 | 说明 |
|---|---|---|
| `views/front/workspace/index.vue` | `components/WorkspaceFilePanel.vue` | 文档列表、上传入口、关联题库/笔记、空态 |
| `views/front/workspace/index.vue` | `useWorkspaceFilters.ts` | 搜索提示、计数、筛选组与可见文件计算 |
| `views/front/workspace/index.vue` | `useWorkspaceCascade.ts` | 全库级联搜索、结果与打开动作 |
| `views/front/workspace/components/KnowledgeWikiPanel.vue` | `knowledgeGraphMeta.ts` | 六类实体元数据、类型归一化与页面类型映射 |

`workspace/index.vue` 已从 3430 行降到 **1000 行**：顶部导航/搜索筛选栏拆为 `WorkspaceChrome.vue`，级联搜索结果拆为 `WorkspaceCascade.vue`，上传/批量删除/上传轮询拆为 `useWorkspaceUpload.ts`，文档刨析状态/分段逻辑拆为 `useWorkspaceAnatomy.ts`，导入/题库关联/笔记关联拆为 `useWorkspaceImports.ts`，编辑器状态/打开/导出拆为 `useWorkspaceEditor.ts`，文本/网页导入弹窗拆为 `WorkspaceTextWebDialogs.vue`，题库导入/题库知识点/题目详情弹窗拆为 `WorkspaceBankDialogs.vue`，后台任务进度栏拆为 `WorkspaceTaskBars.vue`，智能整理流程拆为 `useWorkspaceOrganize.ts`，AI 检索/高亮/命中片段拆为 `useWorkspaceTrySearch.ts`，资料夹动作拆为 `useWorkspaceKbActions.ts`，重新解析任务拆为 `useWorkspaceReprocess.ts`，图片插入题目/笔记弹窗拆为 `WorkspaceImagePickerDialogs.vue`，整理记录/正文编辑器弹窗拆为 `WorkspaceReportEditorDialogs.vue`，编辑器保存/版本恢复的结果处理并入 `useWorkspaceEditor.ts`，代码已按 `views/components/composables/utils/styles` 分目录；`KnowledgeWikiPanel.vue` 从 3240 行降到 2853 行。剩余部分继续按以下顺序拆。

### 样式模块化

对全部大文件做了原样抽取：把内联 `<style>` 拆成同目录 `*.styleN.scss` / `*.styleN.css`，保留原有 `scoped`/全局作用域，逻辑和模板不变。收益最大的文件：

- `notes/detail.vue`：1204 → 566 行；
- `notes/list.vue`：1190 → 685 行；
- `myStats/index.vue`：1327 → 656 行；
- `GalleryPanel.vue`：1273 → 541 行；
- `AiChatStream/index.vue`：2067 → 980 行；
- `AgentToolResult/index.vue`：2007 → 957 行。

二次扫描后，当前 Vue 文件中只剩 12 个仍超过 1000 行：`workspace/index.vue`、`PracticeComponent.vue`、`QuestionBuilder.vue`、`KnowledgeWikiPanel.vue`、`english/listening`、`english/ocr`、`agent/chat`、`AiAssistant`、`MyQuestion`、`KnowledgeBasePanel`、`questionMarked`、`questionError`。

## 后续批次

### 第二批：PracticeComponent

已完成第一步：

- `practiceQuestionUtils.ts`：题型归一、模拟组卷、题干清洗、选项归一化；
- `usePracticeExamTimer.ts`：考试倒计时、时间到处理、页面可见性生命周期；
- `usePracticeScrollHost.ts`：滚动宿主探测、回到顶部/跳到底部、尺寸监听；
- `PracticeComponent.vue` 从 3469 行降到约 2928 行。

下一批继续：

- `PracticeQuestionPanel.vue`：题干、选项、作答区；
- `PracticeAnswerCard.vue`：答题卡（已有 `AnswerCard.vue`，继续收敛）；
- `PracticeSummary.vue`：结果页（已有 `ExamSummary.vue`，继续收敛）；
- `useQuestionPractice.ts` 再拆出 `usePracticeSession.ts`、`usePracticeSubmit.ts`。

### 第三批：KnowledgeWikiPanel

- `useKnowledgeGraphLayout.ts`：`mapNodes`、`mapEdges`、`mapHulls`、布局碰撞和标签避让；
- `KnowledgeWikiDetailDrawer.vue`：主题页详情、出链/反链、来源；
- `KnowledgeWikiGraphPanel.vue`：图谱右侧筛选和操作面板。

### 第四批：题库、英语、笔记、智能体

按页面域拆：

- `studio/QuestionBuilder.vue` → 题目编辑器、题目预览、资料选题；已完成 `questionBuilderUtils.ts` 纯展示工具，主文件从 2892 行降到约 2854 行；
- `english/listening/index.vue` → 听写控制、播放器、结果统计；已完成 `listeningUtils.ts` 纯工具（数组洗牌、延时、URL 种子签名），主文件从 2850 行降到约 2034 行；
- `english/ocr/index.vue` → 上传/识别/校对；样式已外置，主文件从 2120 行降到约 1395 行；
- `agent/chat.vue` / `components/AiChatStream` / `AgentToolResult` → 消息流、工具卡、会话列表；已完成 `agentToolResultSummary.ts`、`aiChatStreamUtils.ts` 纯展示工具和 `useAgentToolJumps.ts` 跳转卡片逻辑；`AiChatStream` 降到约 980 行，`AgentToolResult` 降到约 957 行；
- `notes/*` → 列表、详情、编辑器；已完成 `notesUtils.ts` 纯展示工具，`notes/detail.vue` 降到约 566 行，`notes/list.vue` 降到约 685 行；
- `workspace/components/GalleryPanel.vue` → 已拆出 `GalleryDetailDrawer.vue` 和 `galleryUtils.ts`，主文件从 1273 行降到约 541 行；
- `myQuestion/myStats/index.vue` → 已拆出 `useStatsCharts.ts`，主文件从 1327 行降到约 656 行。

## 当前阈值

- 目标：单文件 ≤ 1000 行；
- 过渡期：新增代码不得继续扩大超大文件；
- 每次拆分保持现有 API、路由和用户行为不变。
