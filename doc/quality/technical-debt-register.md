# OpenStudy 技术债务登记册

> 基线：2026-11-12；本表只登记未完成债务，不把已有拆分当作已清零。
> 相关证据：`quality-report.md`、`quality-scorecard.md`、`doc/engineering/frontend-refactor.md`。

## 1. 类型与 lint 债务

| 项目 | 当前值 | 说明 | 下一步 |
|---|---:|---|---|
| 前端 type-check | **1,786 条 error TS，exit 2** | 历史 RuoYi 页面、`ref({})` 推断、`catch(error)` unknown 等 | 按文件分组，先收敛 `src/views/front` 活跃路径 |
| 前端 ESLint | **0 errors / 3,754 warnings** | warn-only 基线，主要为 any/no-console/默认 prop | 建 warning 预算，按目录递减 |
| 后端 ruff 全量 | **约 115 errors**（107 F401 + 8 F841） | 语法门禁 `E9,F63,F7,F82` 已过；全量未清零 | 先加 `__init__.py` re-export 规则，再逐文件清 F401/F841 |
| 后端覆盖率 | **历史 19%** | 复跑 coverage 当前有 INTERNALERROR，数字需重跑后确认 | 修 coverage 写入路径，再设 30% 路线 |

## 2. 前端超大文件（当前实测）

| 行数 | 文件 | 风险/备注 |
|---:|---|---|
| 1,996 | `src/views/front/workspace/components/KnowledgeWikiPanel.vue` | 图谱/百科双视图，P2 拆分 |
| 1,358 | `src/views/front/studio/components/QuestionBuilder.vue` | 模板约 1,100 行，优先拆 AI 弹窗和编辑器 |
| 1,354 | `src/composables/useAgentChat.ts` | Agent 会话状态机，业务复杂 |
| 1,426 | `src/composables/useQuestionPractice.ts` | 练习状态核心 |
| 1,981 | `src/views/front/english/listening/index.vue` | 英语听力页 |
| 1,734 | `src/api/ai/agentDsFree.ts` | Agent 工具元数据/客户端 |
| 1,501 | `src/api/ai/ai.ts` | AI API 聚合 |
| 1,372 | `src/views/front/english/ocr/index.vue` | OCR 页面 |
| 1,375 | `src/views/front/agent/chat.vue` | 对话页 |
| 1,157 | `src/components/AiAssistant/index.vue` | 助手抽屉 |
| 1,103 | `src/utils/latex.ts` | 工具函数偏大 |

## 3. 后端超大文件（当前实测）

| 行数 | 文件 | 风险/备注 |
|---:|---|---|
| 2,571 | `app/api/v1/questions.py` | 路由/业务混杂，P2 下沉 service |
| 2,299 | `app/api/v1/rag.py` | 资料/RAG 巨型路由 |
| 1,628 | `app/services/rag/wiki_service.py` | 百科服务 |
| 1,882 | `app/services/ai/agent/loop.py` | Agent 循环，已拆部分 helper |
| 1,972 | `app/services/rag/workspace_service.py` | 资料空间服务 |
| 1,821 | `app/services/bank_export_service.py` | 题库导出 |
| 1,723 | `app/api/v1/ai.py` | AI 路由 |

## 4. P2 执行顺序

1. `QuestionBuilder.vue`：先拆 AI 弹窗模板/生成执行链，再拆编辑器；
2. `KnowledgeWikiPanel.vue`：图谱/百科双视图与数据投影分离；
3. `loop.py` / `questions.py` / `rag.py`：路由只留参数/权限/响应，业务下沉 service；
4. `useAgentChat.ts` / `useQuestionPractice.ts`：按会话/题目/草稿边界拆 composable；
5. 每拆一个文件必须 build + 真实页面验证 + 更新本台账；不把“计划拆分”写成“已完成”。
