# OpenStudy 0.7.0 发布说明：智能资料阅读器

> 版本号说明：项目尚未发布 1.0，继续使用语义化 `0.x` 版本。本次对应 `0.6.1 → 0.7.0`，属于原「资料剖析」的能力重构。

## 这次解决什么问题

原「资料剖析」虽然展示了原文、结构树和图片，但左侧目录是静态列表，点不了、没有当前章节高亮，右侧图片栏永久占用阅读宽度，本质上只是一个调试式查看器。

0.7.0 将它重构为「资料原文阅读器」：

- 目录是真导航：点击滚动、滚动高亮、目录搜索、展开/收起；
- 正文限宽、以阅读为主；图片收进抽屉，不抢正文空间；
- LLM 清洗标题与分段，解决 Word / Markdown 标题格式不统一；
- 选中原文可以直接问 AI、出题、引用笔记、加入学习处方；
- 体检章节、知识百科来源、画廊图片与聊天引用都复用同一个阅读器。

## LLM 目录清洗与定位

新增 `rag_document_section` 章节表：

- `title / level / start_offset / end_offset / source`；
- 规则优先：Markdown 标题、中文序号、数字序号、`第X章`；
- 规则无法形成可用目录时，调用 `POST /rag/document/outline/{doc_id}/rebuild`：
  - LLM 只判断标题行和层级，返回 `start_line`；
  - 后端用原文行号计算字符偏移，**不接受模型编造的字符位置**；
  - 无标题资料按 `RagDocumentChunk` 生成「第 N 段」目录；
- 文档正文版本变化后，新 `index_version` 自动使旧章节失效。

## 阅读器交互

- 左侧目录：点击、滚动高亮、搜索、收起；
- 正文：限宽 760–860px，标题锚点，段落行高优化；
- 文档内搜索：命中数量、下一处、黄色高亮；
- 图片：顶部「图片 N」打开抽屉，可按当前章节过滤，点击图片回到原文位置；
- 阅读位置：按文档保存在本地，重新打开自动恢复；
- 选中文字工具条：
  - 问 AI 这段
  - 从这段出题
  - 引用到笔记
  - 加入学习处方
  - 查看相关主题页
  - 复制原文

## 数据与接口

- 新增表：`rag_document_section`（章节标题 / 层级 / start_offset / end_offset / source）。
- `GET /rag/document/outline/{doc_id}`：返回 `sections`、`needsAiOutline`，同时保留原 `tree` 兼容旧调用。
- `POST /rag/document/outline/{doc_id}/rebuild`：LLM 清洗标题并重建目录。

## 联动

- `资料体检`章节 → 打开原文对应偏移；
- `知识百科`来源 → 打开原文对应 chunk；
- `画廊`图片 → 打开原文图片位置；
- 对话/学习处方中的原文定位继续复用同一阅读器；
- 主题页的「问 AI 这一页」与该阅读器使用同一套资料上下文。

## 验证

- 后端分段纯函数测试：25 passed（含 `test_document_section_service.py`）；
- 真实 API：`/rag/document/outline/670` 返回 5 个 LLM 清洗后的章节，`start/end` 连续覆盖原文；
- 前端 `npx vite build --mode development`：通过；
- 阅读器真实截图：`doc/screenshots/46-reader-0.7.0.png`；目录点击测试截图：`doc/screenshots/47-reader-navigation-0.7.0.png`。
