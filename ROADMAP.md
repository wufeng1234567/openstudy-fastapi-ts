# OpenStudy 后续迭代方向（已知边界与改进路线）

> 用途：记录当前版本的**已知缺陷 / 能力边界**，并给出对应的迭代方向。
> 既作为开发待办清单，也可作为「后续迭代计划」的素材来源。
>
> 记录口径：只写**已在代码/数据中实测确认**的边界，每条给出根因与证据位置，
> 不写猜测。最后按优先级排序。

---

## 0. 当前版本定位

当前版本做透的核心闭环：

- AI 学习平台主流程（题库 / 刷题 / 错题 / 笔记 / 分享）
- **RAG 知识库**：上传文档 → 分块 → 向量化 → 混合检索（向量 + jieba 全文，RRF 融合）
- **多智能体协同**：指挥家 + 官方专家（题库 / 笔记 / 知识库 / 统计）+ 用户自定义智能体
- **知识库取材出题**：先检索用户资料原文，再据此出题并注明出处

本文件聚焦其中**尚未做透的一类场景：知识库与图片 / 扫描件**。

---

## 1. RAG 知识库 × 图片 / 扫描件（本轮实测发现）

### 1.1 扫描版（图片型）PDF 无法有效解析 🔴 P0

**现象**
上传扫描版 PDF（每页是一张大图、没有文字层）后：
- 正文抽出来是**目录骨架**，全是 `. . . . . .` 点线，没有真实内容
- 抽出大量「整页图」（实测一份 500 页教材抽出 **560 张图**）
- 检索基本失效 —— 搜到的都是目录，不是内容

**实测数据（本机 DB）**
| 项 | 值 |
|---|---|
| 文档 | `14. 数据结构与算法（Java描述）.pdf` |
| `image_map` 条数 | **560**（键 `"0"` ~ `"559"`） |
| 分块数 | 72 |
| 其中「分块关联到图」的 | **1 / 72** |
| 正文里的 `【图N】` 标记 | 373 个 |

**根因**
PDF 解析用 `pypdf`（`file_parser.py` 的 `_parse_pdf`）：
- 对**扫描版**，PDF 里没有文字层 → 抽不到正文，只能拿到书签/目录
- `page.images` 把**整页扫描图**当作插图抽出 → 图片数量爆炸
- 图片位置只能精确到「页」，与正文段落**无法对齐** → 绝大多数分块关联不到图

**影响**
扫描版教材/试卷/课件（高校场景极常见）传进知识库后，**看起来"能检索"、实际检索不到内容**。

**迭代方向**
- 接入 **OCR**：复用项目已有的多模态识图能力（`app/api/v1/ocr.py`），把每页扫描图转成文字后再入库
- 前置**版式检测**：识别「文字型 / 扫描型」PDF，扫描型走 OCR 分支
- 进阶：OCR + 版面分析，保留「段落 / 标题 / 图表」结构，让图文位置可对齐

---

### 1.2 无法「用文字搜图」/「以图搜图」🟡 P1

**现象**
图片**没有参与向量化**，只能「伴随文字被检索到」，不能作为检索目标。

**根因**
embedding 用 `BAAI/bge-m3`，接口是 `embed_texts(texts: list[str])` —— **纯文本模型**。图片不生成向量。

**影响**
- 「帮我找那张关于电路图的图」→ 找不到
- 纯图片扫描件（无文字）→ 完全检索不到

**迭代方向**
- 引入**多模态向量**（图文同一向量空间，如 CLIP 系）或对图做**图注生成**后再向量化
- 图片单独建索引，与文本索引做**跨模态检索**

---

### 1.3 前端知识库面板不支持图文预览 ✅ 已修复（P0，演示价值高）

**原始现象**
知识库面板里看「文档内容 / 分块 / 试检索结果」时，**看不到图片** —— 上传带图的 `.docx`
后，正文末尾的 `【图0】` 只是原样显示成一个**光秃秃的文字标记**，图不出现。
（复现：文档 `题库测试.docx`，`rag_document.id=443`，`chunk_count=1`，
`image_map={"0": "/profile/upload/2026/10/16/d6ce...jpg"}`，图片**已正确落盘**。）

**根因（两层）**
1. 后端 `rag_write_service.list_chunks` 只回 `content`，**没把 `chunk.meta_data.images` 带出来**
   → 前端即使想渲染也拿不到图的 URL
2. 前端 `KnowledgeBasePanel/index.vue` 分块预览用纯文本插值 `{{ c.content }}`
   → `【图N】` 当字符串直接显示，不渲染成图

**修复（本轮，对应提交见 git log）**
- 后端：`list_chunks` 每条结果新增 `images` 字段（从 `chunk.meta_data` 取，带容错）；
  `get_document_content` 新增 `imageMap`（供「查看原文」用，UI 暂未消费）
- 前端：分块预览改为**图文混排**——按正文 `【图N】` 切段，标记处渲染成 `el-image`
  缩略图（可点击放大）；块头显示「N 张图」标签；标记指向的图缺失时退化为原文文本
- 类型：`api/ai/rag.ts` 的 `RagChunk` 增加 `images?: string[]`
- 探针：`tests/_probe_rag_chunks_images.py`（7 项）

**遗留（后续可做）**
- 试检索结果旁显示命中片段的**图片缩略图**（目前仍只是文本高亮）
- 「查看原文」UI 尚未消费 `imageMap`（接口已就绪）
- 文档详情页「按页 / 按块」浏览，解决长文档预览不完整

---

### 1.4 `.txt` / `.md` 里的图片不解析 🟡 P1

**现象**
Markdown 里写 `![](http://xxx/a.png)`，上传后图片不进知识库。

**根因**
`.md` 没有专用解析器，走 `file_parser.py` 的 `_parse_txt` —— 只 `decode` 成文本，**无图片提取逻辑**（全仓无 Markdown 图片正则）。

**迭代方向**
- 新增 Markdown 解析器：提取 `![alt](url)` 与 HTML `<img>`，外链图可选下载入库
- 纯文本里的图片 URL 可自动识别并入 `image_map`

---

### 1.5 `.docx` 页眉 / 页脚 / 文本框 / 批注里的图片取不到 🟢 P2

**根因**
`_collect_image_rels` 只收 `doc.part` 的关系，`_walk_docx_body` 只遍历 `body` —— 页眉页脚等区域不在遍历路径上。

**迭代方向**
- 遍历 `headers / footers / footnotes / comments` 各 part 的图片关系
- 或对 docx 做**全包扫描**（解压 zip 取 `word/media/`）+ 建立与正文的映射

---

### 1.6 图片位置对齐精度有限 🟢 P2

**现象**
PDF 图只能定位到「页」，无法精确到所在段落/句子。

**迭代方向**
- 用**带坐标的解析器**（如 pdfplumber）拿到图文坐标，按坐标把图嵌进对应段落
- 分块时按坐标而不是纯文本顺序归属图片

---

### 1.7 单文档图片数量上限（出题链路）🟢 P2

**现象**
出题链路最多只把**前 8 张图**交给模型（`chat_engine.py` 的 `MAX_DOC_IMAGES = 8`）。

**根因**
防止单次请求体过大被上游拒绝。

**迭代方向**
- 按「与问题相关度」挑图（而不是按顺序取前 8 张）
- 分页/分批处理，或对图片做更强的压缩与去重

---

### 1.8 小图 / 特殊格式静默丢弃 🟢 P3

**现象**
任一边 < 50px 的图（图标、分隔线）、EMF/WMF/TIFF 转码失败的图，被静默丢弃，用户无感知。

**迭代方向**
- 解析报告里给出「跳过 N 张图（过小 / 格式不支持）」的可见提示
- 补充 EMF/WMF 的转换支持

---

### 1.9 `knowledge_ingest` 工具入库路径未接图 🟢 P2

**现象**
通过智能体（Agent）对话把资料存进知识库时，`knowledge_ingest` 工具未处理图片（只有上传接口那两条路径接了）。

**迭代方向**
- 统一入库入口，让「对话入库」与「页面上传」同口径处理图片

---

### 1.10 部署层：`/profile` 静态代理隐患 🔴 P0（交付前必查）

**现象**
图片存为 `/profile/upload/...`，依赖 Nginx 反代 `/profile` 到后端。若线上 Nginx 配置漏了该规则 → **图片全部 404**。

**证据**
- 仓库内 `openstudy-vue3-ts/nginx.conf` 有 `/profile` 反代
- 服务器手写的 `/etc/nginx/conf.d/openstudy.conf` 是否含该规则**未确认**

**迭代方向**
- 部署检查清单增加「`/profile` 可访问」一项（本文件落定后应同步进部署校验）
- 或改为对象存储直传（OBS/S3），彻底摆脱对本地静态目录的依赖

---

## 2. 其他已知边界（非图片类，顺带记录）

| # | 边界 | 影响 | 方向 |
|---|---|---|---|
| 2.1 | 公网地址 = DevBridge 隧道，隧道 ID 服务端随机、环境断连 12h 自动关机 | 每天需重新拉环境，地址可能变化 | 固定入口（跳转页 / 命名隧道 / 真实服务器） |
| 2.2 | AI 限流（每用户每分钟 10 次、每日 50 次） | 评测时连续操作会 429 | 评测期放宽（已有环境变量） |
| 2.3 | 本地/线上 embedding 依赖（本地模型或云端 Key） | Key 失效则知识库无法向量化 | 多后端自动回退（已部分实现） |
| 2.4 | `deepseek-v4-pro` 不支持图片，需回退 flash | 选 pro 时传图会回退 | 前端已提示，可做更细的能力路由 |

---

## 3. 迭代优先级（建议排期）

### 第一批（交付前 / 演示稳定性）
- ~~**1.3** 前端知识库面板图文预览~~ ✅ **已完成** —— 「AI 看得到图」现已变成「人也看得到图」
- **1.10** 部署层 `/profile` 代理校验（否则图片全丢）

### 第二批（能力补全）
- **1.1** 扫描版 PDF 接入 OCR —— 解决高校最常见的教材形态
- **1.4** Markdown 图片解析
- **1.9** 入库入口统一

### 第三批（技术纵深）
- **1.2** 多模态向量 / 以图搜图 —— 技术亮点，适合写进「创新性」
- **1.6** 图片位置精确对齐
- **1.5 / 1.7 / 1.8** 边角打磨

---

## 4. 相关代码位置（便于后续改动定位）

| 位置 | 作用 |
|---|---|
| `openstudy-fastapi/app/services/file_parser.py` | 文档解析（`_parse_pdf` / `_parse_docx` / `_parse_txt` / `build_marked_document`） |
| `openstudy-fastapi/app/services/rag/document_pipeline.py` | 解析 → 分块 → 向量化 流水线 |
| `openstudy-fastapi/app/services/rag/chunker.py` | 分块（纯文本） |
| `openstudy-fastapi/app/services/rag/embedding.py` | 向量化（`BAAI/bge-m3`，纯文本） |
| `openstudy-fastapi/app/services/rag/hybrid_search.py` | 混合检索；`ChunkHit.images` 已带图 |
| `openstudy-fastapi/app/services/rag/rag_write_service.py` | `persist_document_images` / `build_chunk_rows`（按 `【图N】` 归属图） |
| `openstudy-fastapi/app/models/rag.py` | `RagDocument.image_map` / `RagDocumentChunk.meta_data` |
| `openstudy-fastapi/app/services/ai/chat_engine.py` | 知识库取材带图 + 多模态回传；`MAX_DOC_IMAGES` |
| `openstudy-fastapi/app/services/ai/agent/tools/knowledge_search.py` | 检索工具回灌字段（含 `images`） |
| `openstudy-fastapi/app/api/v1/ocr.py` | 已有的多模态 OCR 能力（接入 RAG 的复用点） |
| `openstudy-vue3-ts/src/components/KnowledgeBasePanel/index.vue` | 前端知识库面板（图文预览改造点） |
