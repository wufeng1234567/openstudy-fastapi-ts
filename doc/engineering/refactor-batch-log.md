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

## Batch 3（2026-11-13，已完成）

- 基线 commit：`0082c2e`
- 快照目录：`_scratch_refactor_batch3_0082c2e/`（含原文件副本 + `baseline-sha256.txt`）
- 授权：hy4 = rag.py + wiki_service.py；minimax3.1f = loop.py

### 批次验收

- [x] 基线快照（文件副本 + SHA256）
- [x] 两个子代理任务已派发（hy4 / minimax3.1f）
- [x] 三个文件全部修改完成
- [x] 主代理 review diff（`git diff --check` 通过）
- [x] 批次级自动测试（compileall / ruff 语法门禁 / rag/wiki/loop 导入 / 22 项定向 pytest）
- [x] 提交并同步三仓库（Gitee/GitCode 已推送；GitHub 重试中）

### 结果（非空行口径）

| 文件 | 批次前 | 批次后 | 变化 |
|---|---:|---:|---:|
| `app/api/v1/rag.py` | 2,665 | 2,476 | -189 |
| `app/services/rag/wiki_service.py` | 2,133 | 2,039 | -94 |
| `app/services/ai/agent/loop.py` | 2,300 | 1,950 | -350 |

新增模块：
- `rag_schemas.py` / `wiki_payload_helpers.py`
- `loop_support.py` / `loop_attachments.py` / `loop_confirm_policy.py`

## Batch 4（2026-11-13，已完成）

- 基线 commit：`81f2b44`
- 快照目录：`_scratch_refactor_batch4_81f2b44/`（含原文件副本 + `baseline-sha256.txt`）
- 授权：hy4 = questions.py + rag.py；minimax3.1f = wiki_service.py

### 批次验收

- [x] 基线快照（文件副本 + SHA256）
- [x] 两个子代理任务已派发（hy4 / minimax3.1f）
- [x] 三个文件全部修改完成
- [x] 主代理 review diff（`git diff --check` 通过，修正一处 EOF 空行）
- [x] 批次级自动测试（compileall / ruff / questions+rag+wiki 导入 / 13 项定向 pytest）
- [x] 提交并同步三仓库（Gitee/GitCode 已推送；GitHub 重试中）

### 结果（非空行口径）

| 文件 | 批次前 | 批次后 | 变化 |
|---|---:|---:|---:|
| `app/api/v1/questions.py` | 3,084 | 3,018 | -66 |
| `app/api/v1/rag.py` | 2,476 | 2,440 | -36 |
| `app/services/rag/wiki_service.py` | 2,039 | 1,928 | -111 |

新增模块：
- `question_schemas.py` / `question_field_helpers.py`
- `rag_formatters.py`
- `wiki_content_helpers.py`

## Batch 5（2026-11-13，已完成）

- 基线 commit：`1830ec4`
- 快照目录：`_scratch_refactor_batch5_1830ec4/`（含原文件副本 + `baseline-sha256.txt`）
- 授权：hy4 = KnowledgeWikiPanel；minimax3.1f = useAgentChat + useQuestionPractice

### 批次验收

- [x] 基线快照（文件副本 + SHA256）
- [x] 两个子代理任务已派发（hy4 / minimax3.1f）
- [x] 三个文件全部修改完成
- [x] 主代理 review diff（`git diff --check` 通过）
- [x] 批次级自动测试（build 4,010 modules / unit 29 项 / studio+workspace+practice smoke 通过；agent-chat 无 console/pageerror）
- [x] 提交并同步三仓库（Gitee/GitCode 已推送；GitHub 重试中）

### 结果（非空行口径）

| 文件 | 批次前 | 批次后 | 变化 |
|---|---:|---:|---:|
| `KnowledgeWikiPanel.vue` | 2,553 | 2,413 | -140 |
| `useAgentChat.ts` | 1,537 | 1,451 | -86 |
| `useQuestionPractice.ts` | 1,515 | 1,485 | -30 |

新增模块：
- `useWikiGraphDerived.ts` / `useWikiGraphHulls.ts`
- `agentChatEventShapes.ts` / `agentChatTurns.ts`
- `questionPracticeRules.ts`

## Batch 6（2026-11-13，已完成）

- 基线 commit：`f35a7ee`
- 快照目录：`_scratch_refactor_batch6_f35a7ee/`
- 授权：hy4 = questions.py + rag.py；minimax3.1f = loop.py
- 测试：compileall / ruff / questions+rag+loop 导入 / 13 项定向 pytest
- 提交：`4b8ea98`（Gitee/GitCode 已推送；GitHub 重试中）

### 结果（非空行口径）

| 文件 | 批次前 | 批次后 | 变化 |
|---|---:|---:|---:|
| `app/api/v1/questions.py` | 3,018 | 2,944 | -74 |
| `app/api/v1/rag.py` | 2,440 | 2,411 | -29 |
| `app/services/ai/agent/loop.py` | 1,950 | 1,911 | -39 |

新增模块：
- `question_export_headers.py` / `rag_payload_formatters.py`
- `loop_stream_helpers.py`

## Batch 7（2026-11-13，已完成）

- 基线 commit：`c8bd1d4`
- 快照目录：`_scratch_refactor_batch7_c8bd1d4/`
- 授权：hy4 = QuestionBuilder + KnowledgeWikiPanel；minimax3.1f = useQuestionPractice
- 测试：build 4,012 modules / unit 29 项 / studio+wiki+practice+agent-chat smoke 通过
- 提交：`595d5b7`（Gitee/GitCode 已推送；GitHub 重试中）

### 结果（非空行口径）

| 文件 | 批次前 | 批次后 | 变化 |
|---|---:|---:|---:|
| `QuestionBuilder.vue` | 1,382 | 1,360 | -22 |
| `KnowledgeWikiPanel.vue` | 2,413 | 2,339 | -74 |
| `useQuestionPractice.ts` | 1,485 | 1,449 | -36 |

新增模块：
- `useQuestionBuilderState.ts` / `useWikiLearningDisplay.ts`
- `questionPracticeBatch.ts`

## Batch 8（2026-11-13，已完成）

- 基线 commit：`49a3632`
- 快照目录：`_scratch_refactor_batch8_49a3632/`
- 授权：hy4 = questions.py + rag.py；minimax3.1f = wiki_service.py
- 测试：compileall / ruff / questions+rag+wiki 导入 / 13 项定向 pytest
- 提交：`5e3ad84`（Gitee/GitCode 已推送；GitHub 重试中）

### 结果（非空行口径）

| 文件 | 批次前 | 批次后 | 变化 |
|---|---:|---:|---:|
| `app/api/v1/questions.py` | 2,944 | 2,859 | -85 |
| `app/api/v1/rag.py` | 2,411 | 2,387 | -24 |
| `app/services/rag/wiki_service.py` | 1,928 | 1,808 | -120 |

新增模块：
- `question_export_rows.py` / `rag_config_formatters.py`
- `wiki_view_helpers.py`

## Batch 9（2026-11-13，已完成）

- 基线 commit：`0a50c84`
- 快照目录：`_scratch_refactor_batch9_0a50c84/`
- 授权：hy4 = questions.py + rag.py；minimax3.1f = KnowledgeWikiPanel.vue
- 测试：build 4,014 modules / unit 29 项 / wiki runtime 无报错 / compileall / ruff / 13 项定向 pytest
- 备注：batch9 发现并修复 `export_bank_rows` 别名导入错误（`bank_rows as export_bank_rows`）
- 提交：`cb70c77`（Gitee/GitCode 已推送；GitHub 重试中）

### 结果（非空行口径）

| 文件 | 批次前 | 批次后 | 变化 |
|---|---:|---:|---:|
| `app/api/v1/questions.py` | 2,859 | 2,819 | -40 |
| `app/api/v1/rag.py` | 2,387 | 2,377 | -10 |
| `KnowledgeWikiPanel.vue` | 2,339 | 2,270 | -69 |

新增模块：
- `question_patch_helpers.py` / `rag_sse_formatters.py`
- `wikiMapGeometry.ts`

## Batch 10（2026-11-13，已完成）

- 基线 commit：`256a8bd`
- 快照目录：`_scratch_refactor_batch10_256a8bd/`
- 授权：hy4 = QuestionBuilder + KnowledgeWikiPanel；minimax3.1f = useAgentChat
- 测试：build 4,017 modules / unit 29 项 / studio+wiki+agent smoke 通过
- 提交：`e4695d6`（Gitee/GitCode 已推送；GitHub 重试中）

### 结果（非空行口径）

| 文件 | 批次前 | 批次后 | 变化 |
|---|---:|---:|---:|
| `QuestionBuilder.vue` | 1,360 | 1,358 | -2 |
| `KnowledgeWikiPanel.vue` | 2,270 | 2,241 | -29 |
| `useAgentChat.ts` | 1,451 | 1,413 | -38 |

新增模块：
- `useQuestionBuilderContext.ts` / `useWikiMapEdges.ts`
- `agentChatMessages.ts`

## Batch 11（2026-11-13，已完成）

- 基线 commit：`ff12482`
- 快照目录：`_scratch_refactor_batch11_ff12482/`
- 授权：hy4 = questions.py + rag.py；minimax3.1f = loop.py
- 测试：compileall / ruff / questions+rag+loop 导入 / 13 项定向 pytest
- 提交：`c475d09`（Gitee/GitCode 已推送；GitHub 重试中）

### 结果（非空行口径）

| 文件 | 批次前 | 批次后 | 变化 |
|---|---:|---:|---:|
| `app/api/v1/questions.py` | 2,819 | 2,799 | -20 |
| `app/api/v1/rag.py` | 2,377 | 2,339 | -38 |
| `app/services/ai/agent/loop.py` | 1,911 | 1,893 | -18 |

新增模块：
- `question_check_formatters.py` / `rag_kb_formatters.py`
- `loop_events.py`

## Batch 12（2026-11-13，已完成）

- 基线 commit：`237cf45`
- 快照目录：`_scratch_refactor_batch12_237cf45/`
- 授权：hy4 = KnowledgeWikiPanel；minimax3.1f = useAgentChat + useQuestionPractice
- 测试：build 4,020 modules / unit 29 项 / studio+wiki+practice+agent smoke 通过
- 提交：`[pending]`

### 结果（非空行口径）

| 文件 | 批次前 | 批次后 | 变化 |
|---|---:|---:|---:|
| `KnowledgeWikiPanel.vue` | 2,241 | 2,036 | -205 |
| `useAgentChat.ts` | 1,413 | 1,405 | -8 |
| `useQuestionPractice.ts` | 1,449 | 1,444 | -5 |

新增模块：
- `useWikiMapNodes.ts`
- `agentChatLifecycle.ts` / `questionPracticeStatus.ts`
