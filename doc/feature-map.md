# OpenStudy 功能地图

> 目的：让评委/新同学在 30 秒内知道「功能在哪里、由谁实现、有什么证据」。
> 事实来源：`OpenStudy-系统完整介绍与功能架构梳理.md`（2026-11-10）与当前代码结构。

## 15 个功能域

| # | 功能域 | 用户入口 | 核心后端 | 关键数据 | Agent 覆盖 | 状态 |
|---:|---|---|---|---|---|---|
| 1 | 智能对话 / Agent | `/front/agent/chat`；侧边栏品牌行助手入口（右侧抽屉） | `app/api/v1/ai.py`、`app/services/ai/agent/loop.py`、`agent/tools/*` | `ai_chat_*`、`ai_agent_*` | 自身 + 29 工具 | 核心 |
| 2 | 我的资料空间 | `/front/workspace` | `app/api/v1/rag.py`、`workspace_service.py` | `rag_knowledge_base`、`rag_document` | `knowledge_*`、`workspace_search`、`gallery_manage` | 核心 |
| 3 | 资料解析 / RAG | 上传、检索、问答 | `file_parser.py`、`document_pipeline.py`、`hybrid_search.py` | `rag_document_chunk` | `knowledge_search`、`knowledge_ingest` | 核心 |
| 4 | 资料诊疗室 | 资料详情：体检 / 原文 / 报告 / 整理 / 版本 | `document_health_service.py`、`material_organizer.py`、`document_smart_report_service.py` | `material_organize_*`、`rag_document_section` | 无专属工具（已知断点） | 页面核心、Agent 缺口 |
| 5 | 知识百科 / 智能图谱 | `/front/workspace` 的百科/图谱视图 | `wiki_service.py`、`wiki_link_service.py`、`knowledge_graph_service.py`、`study_map_service.py` | `rag_wiki_page*`、`rag_graph_*` | `wiki_manage`、`study_graph`、`study_plan` | 核心 / 部分可用 |
| 6 | 题库 / 题目 | `/front/studio`、`/front/myQuestion` | `questions.py`、`question_write_service.py` | `question_bank`、`question_main`、`question_source` | `bank_manage`、`question_manage` | 核心 |
| 7 | 练习 / 考试 / 判分 | `/front/questionPractice` | `practice.py`、`question_grading_service.py` | `user_practice_session`、`user_practice_log` | 间接（`bank_manage` jumpUrl） | 核心 |
| 8 | 错题 / 收藏 / 斩题 | `/front/myQuestion/questions` | `questions.py`、`question_record_service.py` | `user_question_error/favorite/marked` | `question_flag_manage` | 核心 |
| 9 | 笔记 / 学习分享 | `/front/notes`、`/front/myQuestion/noteManage` | `notes.py`、`note_write_service.py` | `note*`、`note_question*` | `note_manage`、`note_kb_link` | 核心 |
| 10 | 学习统计 / 学情诊断 / 规划建议 | `/front/myQuestion/myStats`、知识图谱 | `user_stats.py`、`study_diagnosis_service.py`、`study_advice_service.py` | `user_practice_log`、`study_plan_snapshot` | `learning_stats`、`study_plan`、`study_graph` | 核心 |
| 11 | 文档编排 / 导出 / 微课 | `/front/tools/docCompose`、`/front/microCourse` | `doc_compose_*`、`bank_export_service.py`、`micro_course_*` | `rag_micro_course` | `document_compose`、`bank_export`、`micro_course_generate`、`review_sheet`、`mind_map` | 核心/边缘 |
| 12 | 英语学习 | `/front/english/*` | `words.py`、`english_practice.py`、`ocr.py` | `word_books`、`words`、`english_practice_log` | `english_wordbook`、`english_practice` | 核心 |
| 13 | 分享 / 消息 / 通知 | `/front/share/*`、`/front/messages` | `bankShare.py`、`kbShare.py`、`notification.py` | `bank_share*`、`kb_share*`、`user_notification` | `bank_share_manage`；知识库分享无工具 | 核心/缺口 |
| 14 | 后台管理 / 系统支撑 | `/index`、`/system/*`、`/monitor/*` | `system.py`、`monitor*.py`、`ai_config.py` | `sys_*`、`sys_ai_config` | 无（设计上可做运营智能体） | 仅后台 |
| 15 | 实用工具 | `/front/tools/*` | `document.py`、`doc_compose.py` | — | 部分（文档编排） | 边缘（侧栏入口已注释） |

## 关键链路证据

| 链路 | 入口 | 关键代码 | 可验证证据 |
|---|---|---|---|
| Agent 对话 | 前端 SSE `/ai/agent/stream` | `agent/loop.py`、`registry.py`、`orchestrator.py` | 29 工具 + 确认/回滚/记忆；`doc/功能迭代与代码质量` |
| 资料上传 | `/front/workspace` | `rag.py`、`document_pipeline.py`、`file_parser.py` | 解析 → chunk → embedding → pgvector |
| 资料体检 | 资料详情 | `document_health_service.py` | 四维评分与问题清单 |
| 知识百科 | 资料空间 Wiki 视图 | `wiki_service.py`、`wiki_link_service.py` | 主题页、内链、历史版本 |
| 六类图谱 | Wiki 图谱视图 | `study_map_service.py`、`KnowledgeWikiPanel.vue` | 真实节点/边，当前评级 6/10 |
| 练习判分 | `/front/questionPractice` | `practice.py`、`question_grading_service.py` | 服务端会话、判分、错题记录 |

## 已知缺口（不要写成已完成）

- 资料诊疗室、智能报告、题库关联、知识库分享、后台管理尚无 Agent 工具；
- 图谱四套服务并存，统一图契约已部分落地但未完全收口；
- 题源锚点与笔记节点覆盖仍不足；
- 规划建议不是任务系统，旧学习处方接口仍保留，口径需注意。
