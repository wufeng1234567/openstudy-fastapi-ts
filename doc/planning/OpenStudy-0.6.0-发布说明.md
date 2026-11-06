# OpenStudy 0.6.0 发布说明：知识百科（可编辑版）

> 版本号说明：项目尚未发布 1.0，继续使用语义化 `0.x` 版本。本次对应 `0.5.0 → 0.6.0`，属于新增能力，不称 V6。

## 这次解决什么问题

0.5.0 的知识百科已经能“读”，但用户不能改、不能把画廊图片挂进去、对话也只能检索不能管理主题页。0.6.0 把主题页变成可编辑、可挂图、可被对话操作的学习枢纽。

## 主题页手动编辑

- `PUT /rag/wiki/pages/{page_id}`：编辑标题、摘要、小节正文；保存后自动生成新版本；
- `GET /rag/wiki/pages/{page_id}/revisions`：查看历史版本；
- `POST /rag/wiki/pages/{page_id}/revisions/{revision_id}/restore`：恢复任意历史版本；
- 版本快照保存标题、摘要、正文、结构化小节和来源；
- 用户手写 / Agent 编辑过的页面，后续批量“更新知识百科”不会静默覆盖；
- 编辑器的“来源”只读，避免用户手填不存在的 chunk id；正文可写 LaTeX，详情用 `LatexRenderer` 渲染。

## 对话中的知识百科 CRUD

新增 Agent 工具 `wiki_manage`：

- `list` / `search` / `get`：列主题页、按标题/摘要搜索、读取完整主题页；
- `create`：手动创建主题页；
- `update`：编辑标题、摘要、小节；
- `delete`：删除主题页（破坏性操作，强制确认）；
- `attach_image` / `detach_image`：把画廊图片关联到主题页 / 取消关联。

写入走独立会话并保留版本快照；归属校验按 `user_id → kb_id → page_id → asset_key` 逐层执行。模型不允许凭空编造 pageId / assetKey / referenceId。

## 对话检索知识百科

- `knowledge_search` 回灌结果新增 `sourceType`、`wikiPageId`、`wikiPageTitle`、`wikiSection`、`wikiStale`；
- 对话可以区分「原文命中」「知识百科命中」「图谱邻居命中」；
- Wiki 命中可以展开到来源小节和原始资料；
- `stale` 主题页仍参与检索，但会带 `wikiStale=true`，回答提示「该主题页可能已过期」；
- 系统提示词明确：知识百科是整理稿，原文优先于整理稿。

## 画廊 ↔ 知识百科双向联动

- 复用 `ContentReference`，新增 `target_type=wiki_page`，不复制原图；
- 主题页详情可以「从画廊添加图片」，图片 `rawUrl` 只保存相对路径；
- 画廊图片详情可以「插入知识百科」，选择当前资料夹的主题页；
- 画廊详情的引用关系会显示「知识百科 · 主题页标题」；
- 删除资料时同步清理该资料的图片资产、图片引用和用途账本，避免画廊死链与主题页 404；
- 文档图片只允许挂到同一资料夹的主题页，聊天图片没有资料夹限制。

## 学习入口

- 主题页详情提供「问 AI 这一页」和「生成练习」：通过工作区跳转到智能对话，预填带主题页标题的请求；
- Agent 可继续调用现有 `question_manage` / `bank_manage` 完成出题，或调用 `wiki_manage` 修改主题页；
- 编辑、历史版本、画廊配图都在同一个主题页详情里完成。

## 数据与接口

新增表：

- `rag_wiki_page_revision`：主题页历史版本快照。

新增/扩展接口：

- `POST /rag/wiki/pages`
- `PUT /rag/wiki/pages/{page_id}`
- `DELETE /rag/wiki/pages/{page_id}`
- `GET /rag/wiki/pages/{page_id}/revisions`
- `POST /rag/wiki/pages/{page_id}/revisions/{revision_id}/restore`
- `POST /rag/wiki/pages/{page_id}/images`
- `DELETE /rag/wiki/pages/{page_id}/images/{reference_id}`
- `GET /rag/references?targetType=wiki_page`
- `POST /rag/references` 支持 `targetType=wiki_page`

## 验证

- 核心回归：`pytest tests/test_wiki_service.py tests/test_knowledge_graph_service.py tests/test_chat_suggestion_service.py tests/test_gallery_service.py tests/test_version_diff_service.py`：21 passed；纯函数全量基线（排除三个脚本式探针）43 passed；
- 前端构建：`npx vite build --mode development`：通过；
- 真实 API 验证：主题页手动创建 / 编辑 / 历史版本 / 删除、画廊图片挂载 / 取消挂载、`/rag/references` 的 `wiki_page` 目标、知识百科检索与 `wikiStale` 字段；
- 真实界面截图：`43-knowledge-wiki-editor-0.6.0.png`（手动编辑）、`45-gallery-insert-wiki-0.6.0.png`（画廊插入知识百科）。
