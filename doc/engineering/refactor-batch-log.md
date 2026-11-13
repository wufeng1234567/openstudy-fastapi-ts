# Refactor Batch Log

本文件记录 P2 大文件整改的批次快照、授权范围与验证结果，方便 LLM 评委和后续维护者回溯。

## Batch 1（2026-11-13，已完成）

- 基线 commit：`8deeee10bf47b3c7c6f659dc7efb438a192146d6`
- 快照目录：`_scratch_refactor_batch1/`（已被 `.gitignore` 的 `_scratch*` 规则忽略；含原文件副本与 `baseline-sha256.txt`）
- 回滚命令：`git checkout 8deeee1 -- <file>`；或从快照目录复制原文件

| 文件 | 基线 SHA256 | 授权 |
|---|---|---|
| `openstudy-vue3-ts/src/views/front/studio/components/QuestionBuilder.vue` | `12172CC1084089F0F074127F4372E099C34F8E96D229567331B95862DA37DF34` | hy4 |
| `openstudy-vue3-ts/src/views/front/workspace/components/KnowledgeWikiPanel.vue` | `F9620CAC866149CDE32D895B8F65EB9A5DD996CEC888C671569D1E7A38009CF1` | hy4 |
| `openstudy-vue3-ts/src/composables/useAgentChat.ts` | `B5427A0BBF00A6CA858BA4FADB2CB4FFD5B95B52B4FB71D3EE646C8FDB9F8CB1` | minimax3.1f |

### 子代理约束

- 子代理只允许改授权文件及同目录配套新模块；
- 禁止改既有配置、依赖、其他组件/服务；
- 禁止子代理 commit/push/checkout/reset；
- 禁止子代理单独跑 build/pytest/lint/type-check；
- 3 个文件全部完成后，主代理统一 review diff，再做一次批次级 build + 单测 + 真实页面 smoke。

### 批次验收

- [x] 基线快照（文件副本 + SHA256）
- [x] 两个子代理任务已派发（hy4 / minimax3.1f）
- [x] 三个文件全部修改完成
- [x] 主代理 review diff（`git diff --check` 通过）
- [x] 批次级自动测试（build 3,998 modules / unit 29 项 / 3 路由 smoke 无 console/pageerror）
- [x] 提交并同步三仓库（Gitee/GitCode 已推送；GitHub 重试中）

### 结果（非空行口径）

| 文件 | 批次前 | 批次后 | 变化 |
|---|---:|---:|---:|
| `QuestionBuilder.vue` | 1,627 | 1,475 | -152 |
| `KnowledgeWikiPanel.vue` | 2,657 | 2,586 | -71 |
| `useAgentChat.ts` | 2,102 | 1,537 | -565 |

新增模块：
- `useQuestionBuilderTypes.ts` / `useQuestionBuilderTypePopover.ts` / `useQuestionBuilderAiStream.ts`
- `useWikiMapDisplay.ts`
- `agentChatTypes.ts` / `agentChatTimeline.ts` / `agentChatReferences.ts` / `agentChatMetrics.ts`

## Batch 2（2026-11-13，已完成）

- 基线 commit：`35dd8b8`
- 快照目录：`_scratch_refactor_batch2_35dd8b8/`（含原文件副本 + `baseline-sha256.txt`）
- 授权：hy4 = QuestionBuilder + KnowledgeWikiPanel；minimax3.1f = useQuestionPractice

### 批次验收

- [x] 基线快照（文件副本 + SHA256）
- [x] 两个子代理任务已派发（hy4 / minimax3.1f）
- [x] 三个文件全部修改完成
- [x] 主代理 review diff（`git diff --check` 通过）
- [x] 批次级自动测试（build 4,005 modules / unit 29 项 / studio+practice smoke 通过；workspace 无 console/pageerror）
- [x] 提交并同步三仓库（Gitee/GitCode 已推送；GitHub 重试中）

### 结果（非空行口径）

| 文件 | 批次前 | 批次后 | 变化 |
|---|---:|---:|---:|
| `QuestionBuilder.vue` | 1,475 | 1,382 | -93 |
| `KnowledgeWikiPanel.vue` | 2,586 | 2,553 | -33 |
| `useQuestionPractice.ts` | 2,161 | 1,515 | -646 |

新增模块：
- `useQuestionBuilderDialogActions.ts` / `useQuestionBuilderPreviewEdit.ts`
- `useWikiPlanState.ts` / `useWikiMapViewControls.ts`
- `questionPracticeTransform.ts` / `questionPracticeAnswer.ts` / `questionPracticeRandomPlan.ts`
