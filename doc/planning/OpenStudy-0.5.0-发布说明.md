# OpenStudy 0.5.0 发布说明：知识百科（Wiki）

> 版本号说明：项目尚未发布 1.0，继续使用语义化 `0.x` 版本。本次对应 `0.4.1 → 0.5.0`，不称 V5。

## 这次解决什么问题

0.4.1 已经有实体-关系图谱，但用户点开一个实体时，看到的是几十条原始关系（例如「智能体」下 36 条「包含」）。这是后台索引的形态，不是用户能读的知识形态。

0.5.0 在实体图之上增加了**知识百科主题页**：

- 实体图继续作为后台索引，供 GraphRAG 召回；
- 前台把实体整理成可读主题页：定义、核心要点、知识结构、易混淆、来源；
- 页面之间形成「知识地图」，点节点打开主题页，不再直接铺原始关系；
- 主题页的小节进入检索，与原文、图谱邻居一起参与融合。

## 知识百科

- 新增 `rag_wiki_page`：主题页标题、摘要、正文、结构化小节、来源、状态、版本；
- 新增 `rag_wiki_page_link`：主题页之间的导航边（结构 / 先学 / 对比 / 相关）；
- 新增 `rag_wiki_chunk`：主题页小节级检索块（pgvector + tsvector）；
- 页面生成只使用原始资料 chunk，不拿其他主题页做二次摘要；
- 每个小节必须引用真实 chunk；找不到来源的小节不写入，不编造事实；
- 文档重新解析、删除或更新后，相关主题页标记为 `stale`，不继续参与 Wiki RAG。

## 知识地图

- 顶部「知识图谱」改为「知识百科」；
- 「知识百科」内部提供「主题页 / 知识地图」两个视图；
- 知识地图的节点是主题页，不是原始实体；点击节点打开主题页；
- 页面级关系由实体关系推导，默认只展示结构、先学、对比、相关，不再展示几十条「包含」。

## Wiki RAG

- `hybrid_search` 在向量、关键词、图谱三路之外增加 Wiki 小节一路，统一用 RRF 融合；
- 回答引用同时保留 `wikiPageId`、`wikiPageTitle`、`wikiSection` 和原始 `docId/chunkId`；
- Wiki 命中只作为增强，不替代原文；`stale` 页面不参与检索；
- 检索预览会返回 `sourceType=wiki`，前端可区分「知识百科命中」和「原文命中」。

## 图谱质量修正

- 实体和关系现在记录真正出现该名称的 chunk，不再把整篇文档的所有 chunk 挂给每个实体；
- 关系抽取提示词要求优先使用具体关系，避免所有关系都退化成「包含」；
- 单篇文档抽取 chunk 上限从 8 提到 12，关系上限 60 收到 40，减少低价值关系噪声；
- 保留 PostgreSQL 的 `rag_graph_entity` / `rag_graph_relation`，不引入 Neo4j。

## 接口

- `GET /rag/wiki/pages`
- `POST /rag/wiki/build`
- `GET /rag/wiki/pages/{page_id}`
- `GET /rag/wiki/pages/by-entity/{entity_id}`
- `GET /rag/wiki/graph`

## 验证

- `pytest tests/test_wiki_service.py tests/test_knowledge_graph_service.py tests/test_chat_suggestion_service.py tests/test_gallery_service.py tests/test_version_diff_service.py`：19 passed；
- `npx vite build --mode development`：通过；
- 真实运行验证：知识百科 10 个主题页、知识地图 10 节点 / 8 边；
- RAG 检索命中 `sourceType=wiki`，问答引用同时包含主题页小节和原始资料；
- 真实界面截图：`40-knowledge-wiki-0.5.0.png`、`41-knowledge-wiki-detail-0.5.0.png`、`42-knowledge-wiki-map-0.5.0.png`。
