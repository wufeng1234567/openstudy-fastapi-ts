# OpenStudy 0.7.2 发布说明：智能体画廊取图

> 0.7.2 是 0.7.1 的补丁版本。本次不改变主界面结构，补上智能体主动从画廊列出、搜索、取用图片的能力。

## 1. 为什么要做

在 0.7.2 之前，智能体只能通过 `chat_file_manage` 取「本次对话上传过的文件和图片」。
画廊里的图片资产（文档插图、历史聊天图片）没有对应工具入口，于是会出现：

- 用户说「把画廊里那张电路图插到文档里」，智能体不知道去哪里找；
- 用户说「用资料里那张图」，智能体只能凭文字检索结果猜；
- `wiki_manage.attach_image` 需要 `assetKey`，但智能体没有入口拿到它；
- 画廊明明有图，智能体却让用户重新上传。

## 2. 新增能力

新增只读工具 `gallery_manage`，作为全局工具对所有官方角色和自定义智能体可用：

| 动作 | 作用 |
|---|---|
| `list` | 列出最近图片；支持 `source`（全部 / 文档 / 聊天）、`doc_id`、`kb_id`、`status`、`limit` |
| `search` | 按图片描述、OCR、文件名、来源资料、章节标题、关键词搜索；需要 `query` |
| `get` | 按 `asset_key` 读取单张图片的 URL、来源、描述、OCR、使用记录 |

返回字段包含：

- `assetKey`：稳定图片键，文档图为 `doc:{docId}:{seq}`，聊天图为 `chat:{imageId}`；
- `url`：站内 `/profile/...` 图片地址，可直接用于 `document_compose` 的 image 块、
  `question_manage` 的图片字段；
- `caption` / `ocrText` / `keywords` / `sourceName` / `sectionTitle` /
  `descriptionStatus`：用于判断图片是什么、来自哪里；
- `usableAsImageSource`：明确标记这个 URL 可以作为图片源。

## 3. 搜索口径

`search` 不是向量语义检索，而是**可解释的元数据检索**：

- 精确命中整句时优先；
- 中文自然语言会拆成词和 2 字片段匹配。例如「概率论第三章的分布图」可以分别命中
  来源资料「概率论与数理统计」、章节「第三章」和描述「分布函数的图像」；
- 图片没有生成描述时，只按文件名、来源资料、章节、关键词匹配，并明确提示
  「这些图片还没有生成描述，不要凭空猜测画面内容」；
- 不伪造 `caption` / `ocrText`，也不编造不存在的 `assetKey`。

## 4. 前端表现

- 工具结果里的 `images[]` 复用现有资产卡，卡片标题显示「画廊图片」；
- 每张图显示缩略图、图片名、描述和来源章节；
- 工具名显示为「画廊图片」，动作为「查询列表 / 搜索 / 查看图片」，不再露出英文标识符；
- 图片详情字段补齐中文标签。

## 5. 安全边界

- 工具只读：不修改用户题目、笔记、资料或画廊图片；
- 所有查询按当前 `user_id` 过滤；
- 返回的 `assetKey` 必须来自当前用户的画廊列表，不能凭空生成；
- 图片描述缺失时如实说明，不把文件名当成图片内容。

## 6. 验证

- 单元测试 `tests/test_gallery_agent_tool.py` + `tests/test_gallery_service.py`：11/11 通过；
- 真实库、真实用户验证：
  - `list` 返回画廊图片，`total = 72`；
  - `search("概率论第三章的分布图")` 正确命中 1 张概率论图片；该图尚未生成描述，工具明确提示“不要凭空猜测画面内容”；
  - `search("人工智能实操")` 返回 3 张相关图片；
  - `get("doc:671:26")` 成功返回图片 URL 与真实描述；
- `gallery_manage` 已加入 `GLOBAL_TOOLS`，角色工具名无未知项；
- 后端全量语法编译通过；前端 `vite build --mode development` 通过；
- `gallery_manage` / `get` 的工具名与动作中文标签已补齐并核对。

## 7. 主要文件

- `openstudy-fastapi/app/services/ai/agent/tools/gallery_manage.py`（新增）
- `openstudy-fastapi/app/services/ai/agent/tools/__init__.py`
- `openstudy-fastapi/app/services/ai/agent/roles.py`
- `openstudy-fastapi/tests/test_gallery_agent_tool.py`（新增）
- `openstudy-vue3-ts/src/components/ChatFileAssetCard/index.vue`
- `openstudy-vue3-ts/src/components/AgentToolResult/index.vue`
- `openstudy-vue3-ts/src/components/AgentConfirmCard/index.vue`
- `openstudy-vue3-ts/src/components/AgentToolDetail/index.vue`

## 8. 兼容性

- 版本保持 `0.x` 语义化：`0.7.1 → 0.7.2`；
- 不新增数据库表、不新增 HTTP 接口、不修改用户数据；
- 现有 `chat_file_manage` 行为不变；画廊取图是独立工具，避免两个数据源混在一个工具描述里。
