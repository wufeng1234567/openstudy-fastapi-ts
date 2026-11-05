# OpenStudy · 把不会的，问到会

> 把任意混乱学习材料，编译成可执行、可追溯、会进化的个人学习资产包。
>
> 上传一份 Word / PDF / Markdown，它自己读、自己体检、自己整理、自己出题——还能把同一份资料装配成讲义、复习卡和微课。

**仓库地址**：[gitee.com/wufeng1234567/openstudy-fastapi-ts](https://gitee.com/wufeng1234567/openstudy-fastapi-ts)
　|　[GitHub](https://github.com/wufeng1234567/openstudy-fastapi-ts)
　|　[GitCode](https://gitcode.com/qi142410131/openstudy-fastapi-ts)

<p align="center">
  <img src="doc/screenshots/18-workspace-folder-search.png" width="920" alt="我的资料：资料空间、资料夹与 AI 找资料">
</p>

<p align="center">
  <b>对话即入口</b> · <b>资产可执行</b> · <b>结果可追溯</b>
  <br><br>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white">
  <img alt="Vue" src="https://img.shields.io/badge/Vue-3.4-4FC08D?logo=vuedotjs&logoColor=white">
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-16+pgvector-4169E1?logo=postgresql&logoColor=white">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-green">
</p>

---

## 这是什么

**学生不缺资料，缺的是「把资料编译成学习资产」这几步。**

老师的课件、历年真题、教材，大多是 Word / PDF / 扫描件。想变成能刷的题，得手动录入——
20 道题大约一小时，公式和图还会丢。刷完之后，错题散落在各处，没人告诉你下一步该练什么。

OpenStudy 把这条链路做通了：

```
上传 / 对话收集  →  我的资料（资料空间）  →  资料诊疗室（体检 / 刨析 / 装配）  →  整理手术台
Word/PDF/MD/图片   统一解析 · 自动归位      四维评分     可审阅的变更      题库 · 讲义 · 复习卡 · 微课
```

**它不是一个聊天框。** 对话里的每个动作都调用真实工具、写真实数据表——
你说"用这份资料建个题库，出 10 道题"，它真的会建出来，你能点进去刷。

> 📖 四步各自做了什么、代码在哪 → **[doc/CORE-FLOW.md](doc/CORE-FLOW.md)**

### 从 Spring Boot 到 FastAPI

这个项目**最初是 Spring Boot 3 + Vue 3 实现的**（[Java 版仓库](https://github.com/wufeng1234567/open-study-backend)），
跑通之后重构到了 FastAPI。换技术栈不是赶潮流，是两个具体问题：

| 问题 | Spring Boot 版 | 重构后 |
|---|---|---|
| **流式输出** | SSE 要走 WebFlux，同步栈里接 Agent 的逐字流很别扭 | FastAPI 原生 `StreamingResponse`，纯 ASGI 透传即可逐字下发 |
| **AI 生态** | LangChain / sentence-transformers / bge-m3 的主力都在 Python | 直接 `pip install`，本地向量化同进程加载，不用再起一个 Python 服务 |

Java 那套的多模块分层（admin / common / framework / quartz / system）保留了思路，
Python 版按 `api / models / repositories / services` 重新组织，业务规则逐条对齐。

---

## 核心功能：从「我的资料」到「多种产出」的闭环

### ⓪ 我的资料空间：所有资料，一个入口

<p align="center">
  <img src="doc/screenshots/18-workspace-folder-search.png" width="880" alt="我的资料：资料夹、AI 找资料、智能体自动收集">
</p>

不是文件管理器，也不是普通的 RAG 问答框。**对话里传过的附件、页面上传的文件，最终都进同一个「我的资料」。**

- **两个入口，一个资料库**：对话输入框的附件、拖拽或粘贴的图片，发送消息时自动存入「我的资料 · 收件箱」；页面也支持上传、整页拖拽、批量选择。
- **智能整理**：拆出标题、公式、表格、图片；自动命名、归类、归位；低置信度进「待确认」，不弹窗、不阻塞。
- **资料夹**：按学科或专题组织，支持搜索、右键菜单（重命名 / 分享 / 屏蔽检索 / 删除）。
- **分享与副本**：分享资料夹，领取方得到一份独立副本；原资料后续变化不影响副本。
- **资产账本**：每张图知道来自哪份资料（第几页 / 图几），被哪道题、哪篇笔记用过——图片不是附件，是资产。

### ⓪-1 资料诊疗室：先体检，再刨析，最后装配

<p align="center">
  <img src="doc/screenshots/25-document-health.png" width="920" alt="资料诊疗室 · 资料体检：四维评分、问题清单与章节覆盖热力图">
</p>

上传后的第一屏不是文件列表，而是一张体检单：

- **四维评分**：结构完整度、图文相关度、知识覆盖度、可学习化程度；每项都给出计算依据，不是拍脑袋的分数。
- **问题清单**：按 P0 / P1 / P2 排序，每条都能追到原文证据；支持「去整理 / 去出题 / 看章节」。
- **章节覆盖热力图**：绿=讲解+练习，黄=有讲解缺练习，红=内容过薄；可搜索、可点击定位到章节。
- **纯规则计算**：不调用模型，同一份资料两次体检结果一致，可复现、可解释。

### ⓪-2 整理手术台：AI 改了什么，一条条摊开

<p align="center">
  <img src="doc/screenshots/26-organize-surgery.png" width="920" alt="整理手术台：变更对比、逐项确认、可回退">
</p>

智能整理不再是一个「一键黑盒」：

- **变更对比**：左原文 / 右整理后，点一条两边同步高亮；红色删除、绿色新增。
- **每条都有理由**：删除广告图、合并重复段落、重排章节、改写不通顺内容，均给出原因和置信度。
- **逐项接受 / 拒绝**：默认不勾选；可以全选、逐条拒绝，也可以一键回退。
- **复检**：应用后回到同一份体检报告，看结构问题是否清零、可学习化程度是否提升。

### ⓪-3 资料装配：资料诊疗室里的第三步

<p align="center">
  <img src="doc/screenshots/27-study-pack.png" width="920" alt="资料诊疗室 · 资料装配：选章节、写要求、AI 生成讲义/复习卡">
</p>

把体检后的章节选进装配区，由 LLM 读取完整的选中章节后重新组织：

- **选章节**：左侧素材可以点击或拖进装配区，装配区内可以调整顺序；默认选中全部章节，不偷偷漏内容。
- **写要求**：可以补充使用场景、复习重点和输出偏好，AI 会据此组织内容。
- **AI 生成**：复习卡、讲义、提纲都由 LLM 依据原文重新生成，不是本地截断拼接；生成过程实时显示，完成后下载 Markdown / Word。
- **不伪造**：题单走智能出题，微课走现有生成器，装配结果只依据选中章节原文，不编造内容。

### ① 上传资料 → 自动解析

支持 **Word（.doc / .docx）、PDF、Markdown、TXT**。

不只是抽文字。解析器会：

- **拆结构**：按标题/段落分块，保留章节层级
- **认公式**：Word 原生公式（OMML）和 LaTeX 都能识别，前端用 KaTeX 渲染
- **抠图片**：Word 内嵌图、PDF 里的图，按位置归属到对应段落，正文里留 `【图N】` 标记
- **转格式**：老版 `.doc` 自动调 Word 转 `.docx`，扩展名骗人的文件也能识别（改名的 docx/pdf 会被看穿）

> 传统方案在这一步就断了：扫描件抽不出正文、图片和文字对不上、公式变成乱码。
> 我们做的是**图文一起进**，所以后面出的题才带图、带公式。

<p align="center">
  <img src="doc/screenshots/23-word-source.png" width="330" alt="Word 原文：复杂公式与图">
  <img src="doc/screenshots/24-question-formula-image.png" width="620" alt="导入后：公式与图片落在题目里">
</p>

一份带复杂公式和图的 Word，导入后公式按 LaTeX 渲染、图片落在原题位置，不需要二次排版。

### ② 导入系统 → 变成能检索的知识

解析完的文档进知识库，走完整流水线：

| 环节 | 做了什么 |
|---|---|
| 分块 | jieba 中文分词，按语义切，不是硬切字数 |
| 向量化 | bge-m3 模型，1024 维，存进 pgvector |
| 索引 | 两套索引并行：HNSW 向量索引 + GIN 全文索引 |
| 检索 | 两种方式同时找，再按排名合并（RRF），不拍脑袋定权重 |

**这套东西的价值是：AI 出题时能找到原文，并在每道题后面标注「出自哪一段」。**
不是凭空编题。

#### RAG 跑在哪：本地优先，云端可选

向量化（把文字变成可检索的数字）有两条路，**默认走本地**：

| 方式 | 说明 | 适用场景 |
|---|---|---|
| **本地（默认）** | 本机加载 `BAAI/bge-m3` 模型，文档**不出内网**、不消耗云端额度 | 有 GPU/大内存的服务器、注重数据隐私 |
| **云端（硅基流动）** | 调云端 embeddings 接口，**无需下载 2.2GB 模型** | 轻量服务器、本地装不下模型 |
| 自动 | 优先本地，本地不可用时自动回退云端 | 不想操心的默认选项 |

> **本项目实际部署采用本地向量化**——`openstudy-fastapi` 同机加载 bge-m3，
> 文档切片、向量、检索全部在本地 PostgreSQL + pgvector 内完成，不经过第三方。

后台「系统管理 → 知识库向量化」可视化配置：

<p align="center">
  <img src="doc/screenshots/07-rag-config.png" width="820" alt="知识库向量化配置页">
</p>

- **自动检测环境**：进了页面先告诉你「本地模型装了没、云端 Key 配了没」
- **没装本地模型会引导**：直接给出两种可选方案（装本地 / 切云端），不会让你卡在报错里
- **检索参数可调**：分块大小、重叠、返回条数、RRF 常数，改完即时生效、不用重启
- **换模型会提醒重建索引**：新旧向量不在同一空间，混用会让检索失真

### ③ 出题 → 变成你的题库

三种方式：

- **一句话出题**：「用这份资料出 10 道单选题，覆盖前三章」
- **按知识点出题**：指定知识点和数量，AI 从知识库里取材
- **整份文档直接入库**：上传即建库

出的题可以带图、带公式、带解析，题型覆盖单选/多选/判断/填空/简答，还能生成组合题（材料 + 若干小题）。

**原文依据**：从资料生成的题会写入 `question_source` 锚点（资料 ID、片段 ID、逐字引用的原文句）。
在题目解析和学情诊断里点「原文依据」，可以直接看到这道题来自哪份资料的哪一句——不是模型改写的二手话。

### ④ 开刷 → 练习与诊断

<p align="center">
  <img src="doc/screenshots/04-bank-detail.png" width="760" alt="题库详情：四种练习模式">
</p>

| 模式 | 说明 |
|---|---|
| 顺序练习 | 按章节顺序逐题练 |
| 随机练习 | 随机抽题，一次抽定不刷新 |
| 错题练习 | 只练答错过的题 |
| 模拟考试 | 自定义组卷、限时、交卷判分、历史回看 |

刷完还有：**错题本、收藏、斩题、笔记（草稿自动保存）、学习统计（正确率/趋势/薄弱点 TOP5）。**

<p align="center">
  <img src="doc/screenshots/05-stats.png" width="760" alt="学习统计：正确率、趋势、薄弱知识点">
</p>

### ⑤ 一份资料，多种产出

同一份资料，除了出题，还能做讲义、复习卡、提纲、微课——资料只上传一次，产出可以有很多种。

| 产出 | 说明 |
|---|---|
| **题库练习** | 建库 / 组卷 / 顺序·随机·错题·模拟考；答题卡、自动判分、考试记录 |
| **讲义文档** | 导出 Word / PDF：原生公式与表格，3 套主题，封面、目录、页码齐全 |
| **复习卡 / 提纲** | 资料诊疗室 → 资料装配里拖拽章节生成：复习卡每节约 300 字，提纲保留标题与首句 |
| **资料微课** | 按原文结构拆成 7 站学习路径（31 分钟），每站有检查点与复述 |
| **教学微课** | 11 页 HTML 课件，按提示词改页，一键导出 PPT，可分享给同学 |

<p align="center">
  <img src="doc/screenshots/11-micro-course.png" width="440" alt="资料微课：按原文结构拆成 7 站学习路径">
  <img src="doc/screenshots/20-micro-course-html.png" width="440" alt="教学微课：11 页 HTML 课件，可导出 PPT">
</p>

### ⑥ 扩展能力：英语学习，从识词到统计

同一套「资料 → 练习 → 诊断」的思路，在英语科目上做了一遍垂直版本：

| 环节 | 能做什么 |
|---|---|
| 拍照识词 | 拍一张书页照片，或直接传 PDF / Word / Markdown / txt，AI 抽出单词自动建词库 |
| 我的词库 | 增删改查、批量删除、搜索、朗读；**可导出 Anki / Excel / Word** |
| 单词听写 | 三种模式（纯听力 / 打字输入 / 自动听写）× 三档播放内容（中文 / 英文 / 中英） |
| 阅读练习 | AI 生成短文 + 阅读理解题，答完即时判分 |
| 学习统计 | 正确率趋势（7 天 / 30 天）、各模式对比、最常写错的词、连续练习天数 |

几个刻意的设计：

- **听写的「题目范围」可选** —— 全部 / 最近加入的 20 个 / 前几个，不必每次从第一页刷起。
  顺序上**先取子集再打乱**，否则「最近 20 个」会变成"随机抽 20 个"。
- **统计页不是只读报表** —— 「最常写错」下面直接有个「用这些错词练一轮」，
  点了就带着错词跳进听写页。错词跨词库也能练到（会按单词去别的词库查回来）。
- **导出不经过后端** —— Anki 是 TSV、Excel 用 SpreadsheetML、Word 用 HTML + `.doc`，
  三种都只是字符串拼接，纯前端生成 Blob 直接下载。不占带宽，也不用为三种格式各写一个接口。

---

## AI 智能体：会办事，不只是会聊

<p align="center">
  <img src="doc/screenshots/02-agent-session.png" width="820" alt="对话式建题库：从资料到 20 道题">
</p>

- **多专家并行**：一句话要干两件事，两个专家同时开工；只有一件事就不打扰你
- **写操作先确认**：改数据之前弹确认卡，看清楚再点
- **改错能撤回**：题库、题目、分享、智能体四个域支持整树快照恢复；回退不了的会明确告诉你
- **跨会话记忆**：记住你做过的操作，下次接着聊
- **对话文件资产卡**：调用对话里的文件/图片时，显示文件名、图片名、大小、上传时间；点名字直接预览，不把内部 JSON 字段丢给用户
- **题库入口一句话直达**：说「打开『题库测试』的入口链接」，智能体返回「去刷题」卡片，一键跳到题库练习页
- **20+ 个工具**：题库管理、题目管理、笔记、资料空间、检索、学情统计、记忆、导出…

---

## 快速开始

### 方式一：本地部署（Docker，推荐自建）

```bash
# Gitee（国内访问最快，推荐国内用户）
git clone https://gitee.com/wufeng1234567/openstudy-fastapi-ts.git

# GitHub（海外 / 镜像备份）
git clone https://github.com/wufeng1234567/openstudy-fastapi-ts.git

# GitCode（国内备用线路）
git clone https://gitcode.com/qi142410131/openstudy-fastapi-ts.git

cd openstudy-fastapi-ts
docker compose up -d --build
```

浏览器打开 **http://localhost:3167**。

**本地部署的演示账号**（数据库首次启动自动创建）：

| 账号 | 密码 | 说明 |
|---|---|---|
| `admin` | `123456` | 管理员，可进后台 |
| `user1` | `123456` | 演示用户，带题库 / 笔记 / 学习统计 |
| `user2` | `123456` | 分享接收方 |
| `guest` | 免密一键登录 | 只读游客 |

> ⚠️ 以上密码**仅适用于本地自建环境**，且仅用于快速体验。
> **正式对外部署前必须修改**：改 `deploy/db-init/05_change_password.sql` 里的初始密码，
> 并同步修改 `openstudy-fastapi/.env` 的 `JWT_SECRET`。

### 方式二：公网体验环境

公网演示环境**不提供任何账号密码**——请自行**注册**后登录体验。

> 出于安全考虑，线上环境不开放演示账号，也不对外公布任何凭据。
> 注册后你会得到一个独立账号，可以完整走通「我的资料 → 自动解析 → 建题库 / 做讲义 / 生成微课」全流程。

> 数据库首次启动会自动建表 + 导种子数据，无需手动操作。
> **不配 AI Key 也能跑**——除 AI 对话和知识库外，其余功能全部可用。
> 完整部署说明（含 Linux 手动部署、公网访问、Windows 本地）见 [`doc/deploy/SKILL.md`](doc/deploy/SKILL.md)。

### AI Key 配置（可选）

复制 `openstudy-fastapi/.env.example` 为 `.env`：

```dotenv
DEEPSEEK_API_KEY=      # 对话模型
SILICONFLOW_API_KEY=   # 向量化（BAAI/bge-m3）
ZHIPU_API_KEY=         # 备用模型
```

> 知识库向量化默认走本地模型（首次自动下载 bge-m3 约 2.2GB）。
> 小内存机器可设 `EMBEDDING_BACKEND=siliconflow` 走云端。

---

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3.4 · TypeScript · Vite · Element Plus · Pinia |
| 后端 | Python 3.11 · FastAPI · SQLAlchemy 2.0（异步）· asyncpg |
| 数据库 | PostgreSQL 16 + pgvector（向量检索）+ pg_trgm（模糊匹配） |
| 缓存 | Redis 7（登录态 / 限流） |
| AI | LangChain · DeepSeek / 智谱 / 硅基流动 多模型动态路由 |
| 部署 | Docker Compose 一键起（PG + Redis + 后端 + Nginx） |

### 几个技术选择

**为什么自己写 Agent 循环，不用 LangGraph？**
因为要省 token、要可控。路由用关键词规则而不是再打一次模型——省下的钱不能被路由花回去。
按功能域把工具切成 5 类专家，每个只挂自己那组，工具越少选错越少。

**为什么检索用 RRF 不用加权分数？**
加权要先拍一个"向量分 0.8、关键词分 0.6"的系数，换个查询就反过来了。
RRF 只看排名不看分数，天然规避这个问题。

**为什么流式要自己写中间件？**
默认的 ASGI 中间件会把响应攒批，表现为"思考过程卡住几秒然后一次性刷出来"。
改成纯 ASGI 透传后才真正逐字下发。

---

## 项目结构

```
openstudy-fastapi-ts/
├── openstudy-fastapi/          # 后端（FastAPI）
│   ├── app/
│   │   ├── api/v1/             # 路由层（32 个模块）
│   │   ├── models/             # ORM 模型
│   │   ├── repositories/       # 数据访问
│   │   └── services/
│   │       ├── ai/             # 模型客户端 / Agent 循环 / 工具 / 记忆
│   │       │   └── agent/      # 编排 / 子代理 / 回退 / 确认
│   │       ├── rag/            # 分块 / 向量化 / 混合检索
│   │       ├── document_health_service.py  # 资料体检（四维评分 / 章节热力）
│   │       └── file_parser.py  # 文档解析（Word / PDF / MD）
│   └── tests/                  # 自动化探针与单元测试
├── openstudy-vue3-ts/          # 前端（Vue3 + TS）
│   └── src/
├── deploy/db-init/             # 数据库初始化 SQL
├── doc/                        # 文档
│   ├── CORE-FLOW.md            # 核心链路（上传→解析→导入→刷题）
│   ├── ITERATION-PLAN.md       # 迭代计划
│   ├── deploy/                 # 部署说明
│   ├── dev-process/            # 开发过程记录（码道）
│   ├── screenshots/            # 产品截图
│   ├── testing/                # 接口测试用例
│   └── competition/            # 项目材料
└── docker-compose.yml          # 一键部署
```

---

## 开发方式：核心能力用华为云码道 CodeArts 开发

本项目的**智能体核心三块**——Agent 工具循环、工具链、RAG 检索——
是使用**华为云码道 CodeArts 代码智能体**完成优化与重构的，全过程留痕、可复核。

| 证据 | 位置 |
|---|---|
| 每日开发日志（5 天，10.9 MB） | [`doc/dev-process/logs/`](doc/dev-process/logs/) |
| 完整 AI 分析会话（6 份） | [`doc/dev-process/sessions/`](doc/dev-process/sessions/) |
| 决策与踩坑笔记（91 份） | [`doc/dev-process/memory/`](doc/dev-process/memory/) |
| 代码库索引记录 | [`doc/dev-process/codebase/index-report.md`](doc/dev-process/codebase/index-report.md) |
| 说明与复现方式 | [`doc/dev-process/README.md`](doc/dev-process/README.md) |

> 五天里码道执行了 **3,248 次工具调用**（1,720 次命令 / 638 次读文件 / 482 次改代码 / 193 次新建文件），
> 产生 **50 次 Git 提交**，改写 **186 个文件**。会话 ID、时间戳、工具调用记录、提交记录四者可交叉核对。

---

## 迭代方向

产品已经跑通「资料 → 题 → 练习 → 诊断」这一条闭环，接下来分三段推进：

### 30 天：补主链路的短板

| 事项 | 为什么优先 |
|---|---|
| **扫描版 PDF 接 OCR** | 高校最常见的资料形态。现在扫描件抽不出正文，等于这批资料白传 |
| Markdown 图片解析 | `![](url)` 外链图现在不进知识库 |
| 入库入口统一 | 「页面上传」和「对话入库」对图片处理不一致 |
| `/profile` 代理自检 | 线上配置漏了会让图片全 404 |

### 90 天：把「能用」做成「好用」

- **多模态向量**：现在图片不参与向量化，搜不到「那张电路图」。目标是以图搜图 / 文字搜图
- **移动端适配**：补响应式布局与软键盘适配
- **对象存储直传（OBS）**：摆脱对本地磁盘和 Nginx 静态代理的依赖
- **知识库增量更新**：教材改版只重传变更章节，不整份重来

### 更远：从工具到平台

- **校园版多租户**：一个学校一个租户，教师组卷、看班级学情
- **教师端**：按知识点 / 难度自动组卷，考后看班级薄弱点分布
- **开放 API**：题库、笔记、知识库对外开放，接入教务系统或题库供应商
- **更多华为云能力**：OCR、搜索加速

> 完整的边界分析、验收标准与优先级排序见 **[doc/ITERATION-PLAN.md](doc/ITERATION-PLAN.md)**。

---

## 文档

| 文档 | 内容 |
|---|---|
| [doc/deploy/SKILL.md](doc/deploy/SKILL.md) | 完整部署说明（Docker / Linux / Windows / 公网访问） |
| [doc/deploy/TROUBLESHOOTING.md](doc/deploy/TROUBLESHOOTING.md) | 常见问题排查 |
| [doc/deploy/DEPLOY-EXPERIENCE.md](doc/deploy/DEPLOY-EXPERIENCE.md) | 部署踩坑记录 |
| [ROADMAP.md](ROADMAP.md) | 已知边界与迭代方向 |
| [doc/testing/](doc/testing/) | 题库域接口功能测试用例表 |
| [doc/dev-process/](doc/dev-process/) | 开发过程原始记录 |

---

## 已知边界（如实说明）

- **扫描版 PDF** 目前抽不出正文（没有文字层），只能拿到目录骨架 → 已在 30 天计划里排 OCR
- 图片**不参与向量化**，只能随文字被检索到，不能"以图搜图"
- 公网演示环境依赖隧道，地址可能变化
- AI 限流：每用户每分钟 10 次、每日 50 次（评测期可通过环境变量放宽）

---

## License

[MIT](LICENSE)
