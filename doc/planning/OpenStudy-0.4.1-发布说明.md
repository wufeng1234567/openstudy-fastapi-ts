# OpenStudy 0.4.1 发布说明：资料知识网络

> 版本号说明：项目尚未发布 1.0，统一使用语义化 `0.x` 版本。本次不叫 V4，对应 `0.4.0 → 0.4.1`。

## 0.4.0：可找 + 可引 + 可验证

### 画廊
- 「我的资料」顶部新增「画廊」，替换原图片墙；
- 汇总文档图片、聊天图片，支持按当前资料夹 / 全部资料查看；
- 搜索覆盖图片描述、OCR、文件名、来源资料、章节标题；
- 图片详情展示真实来源章节、附近原文、描述、OCR、用途和引用；
- 顶部「补全未描述」只描述当前列表内未完成的图片，不自动消耗额度；
- 视觉模型返回 `caption / ocrText / kind / keywords`，结果写入 `rag_image_asset`。

### 统一引用
- 新增 `content_reference`：`source_type / source_id / source_sub_id → target_type / target_id`；
- 支持文档图片 / 聊天图片 / 笔记 / 题目之间的引用；
- 从画廊把图片插入笔记或题目时，自动写入引用账本；
- 画廊详情展示「被谁引用」；知识图谱的实体关系来自资料正文抽取，实体和关系都能回到来源 chunk。

### 学习处方导出
- 处方支持导出 `PDF / Word / Markdown / TXT`；
- Word 继续走原生 OMML 公式，PDF 使用 CJK 字体并做 LaTeX 符号降级；
- 导出内容包含目标、周期、每天主题、任务、原文章节和复诊节点，并带任务完成状态。

### 版本对照
- 编辑器「版本对照」升级为时间线 + 左右 diff + 体检变化；
- 支持选两个历史版本，或历史版本 ↔ 当前正文；
- 差异按新增 / 删除 / 修改着色，同时显示字数、体检分、问题数变化；
- 恢复历史版本仍会先保存当前快照，不覆盖历史。

## 0.4.1：实体-关系知识图谱

### 方案
- 节点 = LLM 从资料 chunk 抽取的实体，类型限定为概念 / 定理公式 / 方法 / 人物 / 机构 / 事件 / 作品 / 其他；
- 边 = 实体之间的有向语义关系（包含、属于、定义、推导、应用、前置、对比、相关），带 1-10 关系强度；
- 每个实体和关系都保存 `doc_id` + `chunk_id` 证据，可回到资料刨析定位原文；
- 使用 PostgreSQL 的 `rag_graph_entity` / `rag_graph_relation`，不新增 Neo4j 或独立图服务；
- 前端用力导向 + 类型着色 + 连接度节点大小；隐藏孤立实体、类型筛选、搜索、点击详情都在同一张图完成。

### 交互
- 路由导航上移到全局最顶层顶栏：面包屑（我的资料 / 当前资料夹 / 当前视图）+ 工作台 tabs（资料夹 / 书架 / 画廊 / 知识图谱）直接位于页面顶部，不再下放到内容区；
- 第二层统一为「当前视图计数 + 全局搜索」：资料夹显示全部资料夹数量，画廊显示全部图片数量，知识图谱显示实体数量；
- 资料夹页的搜索升级为级联搜索：同时匹配资料夹名称和内部文档的文件名、备注、正文，并按资料夹分组展示；资料夹名称命中但内部没有文档命中时也保留该资料夹；
- 四类视图的搜索框统一复用 `SearchFilterInput`，筛选下拉复用 `CommonFilterSidebar`：资料视图筛选资料类型/处理状态，画廊筛选图片类型/描述状态，知识图谱筛选实体类型；
- 知识图谱使用 LLM 从资料 chunk 抽取实体与有向关系，存储 `rag_graph_entity` / `rag_graph_relation`；节点大小按连接度、边按关系强度绘制，实体详情可查看来源分块并跳回原文；
- 知识图谱支持隐藏孤立实体、实体类型筛选、实体搜索、点击查看邻居与来源证据，不依赖 Neo4j；
- 新会话首页重做：`Hi，我是 OpenStudy` 欢迎语 + 「你可以这样问我」动态提问推测；有资料时由 LLM 读取最近资料生成问题，没有资料时给起步体验问题；上传文档后会基于该文档刷新提问；
- 画廊改为瀑布流：按图片原始比例自然排布，卡片高度有梯度，不再固定 4:3 裁切；
- 画廊移除「全部状态」筛选；只保留当前资料夹 / 全部资料、图片来源和补描述动作；
- 图谱详情展示实体描述、出现次数、关联邻居和来源 chunk；点击来源可回到资料刨析定位原文；
- 图谱没有实体或关系时显示空态和「抽取当前资料夹」按钮，不伪造节点、边或强度。

## 数据与接口
- `GET /rag/gallery`、`GET /rag/gallery/{asset_key}`、`POST /rag/gallery/describe`
- `GET /rag/references`、`POST /rag/references`、`DELETE /rag/references/{id}`
- `GET /rag/knowledge-graph`、`POST /rag/knowledge-graph/build`、`GET /rag/knowledge-graph/entity/{entity_id}`
- `GET /rag/chat/suggestions`（新会话提问推测，可带 `docId`）
- `GET /rag/document/versions/{doc_id}/diff`

## 验证
- `pytest tests/test_gallery_service.py tests/test_knowledge_map_service.py tests/test_version_diff_service.py tests/test_knowledge_graph_service.py tests/test_study_prescription_export_service.py`：28 passed；
- `npx vite build --mode development`：通过；
- 真实界面截图：`gallery-0.4.0.png`、`gallery-detail-0.4.0.png`、`36-knowledge-graph-0.4.1.png`、`37-chat-new-session.png`、`version-diff-0.4.0.png`。
