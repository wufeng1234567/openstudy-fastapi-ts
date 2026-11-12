# 前端大文件解耦记录

目标：把超过 1000 行的前端文件按职责拆成可复用的 composable、纯工具模块和展示组件，先处理业务核心链路，再逐步覆盖题库、英语、笔记和智能体页面。

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

`workspace/index.vue` 已从 3430 行降到 3085 行；`KnowledgeWikiPanel.vue` 从 3240 行降到 3161 行。剩余部分继续按以下顺序拆。

## 后续批次

### 第二批：PracticeComponent

已完成第一步：

- `practiceQuestionUtils.ts`：题型归一、模拟组卷、题干清洗、选项归一化；
- `usePracticeExamTimer.ts`：考试倒计时、时间到处理、页面可见性生命周期；
- `usePracticeScrollHost.ts`：滚动宿主探测、回到顶部/跳到底部、尺寸监听；
- `PracticeComponent.vue` 从 3469 行降到约 3143 行。

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
- `english/listening/index.vue` → 听写控制、播放器、结果统计；已完成 `listeningUtils.ts` 纯工具（数组洗牌、延时、URL 种子签名），主文件从 2850 行降到约 2806 行；
- `english/ocr/index.vue` → 上传/识别/校对；
- `agent/chat.vue` / `components/AiChatStream` / `AgentToolResult` → 消息流、工具卡、会话列表；已完成 `agentToolResultSummary.ts`、`aiChatStreamUtils.ts` 纯展示工具；
- `notes/*` → 列表、详情、编辑器；已完成 `notesUtils.ts` 纯展示工具，`notes/detail.vue` 从 1204 行降到约 1170 行；
- `workspace/components/GalleryPanel.vue` → 已拆出 `GalleryDetailDrawer.vue` 和 `galleryUtils.ts`，主文件从 1273 行降到 1000 行；
- `myQuestion/myStats/index.vue` → 已拆出 `useStatsCharts.ts`，主文件从 1327 行降到约 1184 行。

## 当前阈值

- 目标：单文件 ≤ 1000 行；
- 过渡期：新增代码不得继续扩大超大文件；
- 每次拆分保持现有 API、路由和用户行为不变。
