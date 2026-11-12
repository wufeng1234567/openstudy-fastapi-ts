# OpenStudy API 与数据模型概览

> 目的：给评委/开发一个可核验的接口与数据边界，不替代 OpenAPI/代码。
> 事实基线：系统介绍（2026-11-10）；当前后端 `app/api/v1` 约 42 个挂载路由模块，ORM 约 80 张表。

## 1. API 分层

```text
app/api/v1/*.py       路由：参数校验、鉴权、响应映射
        │
        ▼
app/services/*.py     业务：Agent / RAG / 题库 / 练习 / 笔记 / 统计
        │
        ▼
app/models/*.py       ORM 模型（部分历史模型仍在迁移）
```

约定：

- 路由不直接写复杂业务，复杂逻辑进 service；
- 请求/响应尽量使用 schema；
- 写操作要有权限、确认/回滚边界；
- 长任务通过 job/stream/轮询返回真实状态，不伪造进度。

## 2. 主要路由域

| 路由域 | 代表模块 | 职责 |
|---|---|---|
| 认证/用户 | `auth.py`、`users.py`、`system.py` | 登录、用户、角色、菜单、权限 |
| 资料/RAG | `rag.py`、`document*.py` | 知识库、上传、解析、检索、资料体检、版本 |
| 知识百科/图谱 | `rag.py` 的 wiki/graph 端点，`study_map_service` | 主题页、页面链接、六类图、来源更新 |
| Agent | `ai.py`、`agent/*` | 会话、SSE、工具、确认、回滚、记忆 |
| 题库 | `questions.py`、`question_write_service.py` | 题库/题目 CRUD、导入、导出 |
| 练习 | `practice.py` | 会话、答案、交卷、判分、错题 |
| 笔记 | `notes.py`、`note_write_service.py` | 笔记、草稿、关联、导入资料夹 |
| 英语 | `words.py`、`english_practice.py`、`ocr.py` | 词库、听写、阅读、OCR |
| 分享/通知 | `bankShare.py`、`kbShare.py`、`notification.py` | 分享、领取、消息 |
| 系统/监控 | `monitor*.py`、`ai_config.py` | 后台管理、监控、AI 配置 |

## 3. 数据模型（按域）

| 域 | 代表表 |
|---|---|
| 用户/权限/系统 | `sys_user`、`sys_role`、`sys_menu`、`sys_dept`、`sys_config`、`sys_dict_*`、`sys_notice*`、`sys_job*`、`sys_oper_log`、`sys_logininfor` |
| 资料/RAG | `rag_knowledge_base`、`rag_document`、`rag_document_chunk`、`rag_document_section`、`rag_qa_record`、`rag_micro_course` |
| 知识百科/图谱 | `rag_wiki_page`、`rag_wiki_chunk`、`rag_wiki_page_link`、`rag_wiki_page_revision`、`rag_wiki_page_learning`、`rag_graph_entity`、`rag_graph_relation`、`source_graph_state` |
| 资料资产 | `rag_image_asset`、`rag_image_describe_job`、`rag_wiki_build_job`、`material_asset_usage`、`content_reference`、`material_organize_plan`、`material_organize_log` |
| 题库/练习 | `question_bank`、`question_main`、`question_sub`、`question_source`、`user_practice_session`、`user_practice_log`、`user_question_error`、`user_question_favorite`、`user_question_marked`、`user_bank_favorite`、`question_bank_kb_link` |
| 笔记 | `note`、`note_category`、`note_comment`、`note_question`、`note_question_bank`、`note_public_section`、`user_note_draft`、`user_note_favorite`、`user_note_like`、`note_kb_link` |
| 学习规划/统计 | `study_plan_snapshot`、`user_practice_log` |
| 对话/Agent | `ai_chat_session`、`ai_chat_message`、`ai_agent_timeline`、`ai_agent_memory`、`ai_agent_config`、`ai_agent_op_log`、`ai_agent_role_pref`、`ai_agent_tool_pref`、`chat_upload_file`、`chat_upload_image` |
| 分享 | `bank_share`、`bank_share_receive`、`kb_share`、`kb_share_receive` |
| 英语 | `word_books`、`words`、`word_learning_state`、`english_practice_log` |
| 其他 | `courses`、`user_notification`、`sys_ai_config`、`sys_ai_rate_limit_log` |

## 4. Agent 工具契约

- 29 个工具，统一注册在 `app/services/ai/agent/tools/`；
- 工具描述：英文 name/description + 中文 label/description_zh；
- 写操作声明 `write_operation=True`，需确认/回滚；
- 工具结果通过 `tool_result` 事件返回，前端 `AgentToolResult` 按契约渲染；
- 角色白名单由 `roles.py` 控制，未知工具默认不暴露。

## 5. 数据与迁移边界

- 当前 `alembic.ini` 指向的迁移目录仍不存在，实际有 `init_db()` + `deploy/db-init/*.sql` 历史脚本；这是 P1 待补项。
- 任何 schema 变更必须新增可回滚 migration；不要只改 ORM。
- 敏感字段（密码、token、PII）不进入日志和前端响应。
