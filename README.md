# OpenStudy 在线学习平台

> 一个面向在线学习场景的全栈应用：题库刷题、错题本、笔记、学习分享、消息通知，并内置 **AI 助手（Agent + RAG 知识库 + 长期记忆）**。

- **后端**：Python 3.11 · FastAPI · SQLAlchemy 2.0（异步）· PostgreSQL + pgvector
- **前端**：Vue 3 · TypeScript · Vite · Element Plus · Pinia
- **AI**：LangChain · DeepSeek / 智谱 / 硅基流动 多模型动态路由
- **部署**：提供完整的逐步安装说明，支持 Linux 服务器 / 云沙箱 / 本机运行

---

## 目录结构

```
fastapi-v2/
├── openstudy-fastapi/        # 后端（FastAPI）
│   ├── app/
│   │   ├── api/v1/           # 路由层（题库/笔记/错题/AI/RAG/OCR… 共 30+ 模块）
│   │   ├── core/             # 安全、响应封装、中间件、异常
│   │   ├── models/           # SQLAlchemy ORM 模型
│   │   ├── schemas/          # Pydantic 模型
│   │   ├── repositories/     # 数据访问层
│   │   └── services/
│   │       ├── ai/           # AI 能力：多模型客户端、Agent 循环、工具、记忆
│   │       │   └── agent/    # Agent 运行时（loop / 工具注册表 / 回退 / 确认）
│   │       └── rag/          # 知识库：分块 / 向量化 / 混合检索 / 写入流水线
│   ├── requirements.txt      # Python 依赖
│   └── .env.example          # 环境变量样例（真实 .env 不入库）
├── openstudy-vue3-ts/        # 前端（Vue3 + TS）
│   ├── src/                  # 源码（api / views / components / layout / utils）
│   └── package.json
├── deploy/
│   └── db-init/              # 数据库初始化 SQL（结构 + 种子 + 演示数据）
├── startup-scripts/          # 启动脚本与数据库脚本
├── SKILL.md                  # ⭐ 部署安装说明书（给 AI 终端 / 部署人员，含公网访问方案）
└── README.md                 # 本文件（面向使用者的项目介绍）
```

> 📌 **要开始部署 / 在服务器或云端跑起来？请阅读 [`SKILL.md`](./SKILL.md)。**
> 本 README 只做项目介绍；具体的安装、启动、公网访问步骤都在 `SKILL.md` 里。

---

## 核心功能

### 学习域
- **题库 / 刷题**：题库管理、题目练习、答题卡
- **错题本 / 收藏**：错题与收藏题目的归类管理
- **笔记**：富文本笔记（TipTap）、笔记分类、题目关联
- **课程 / 单词本**：课程与词汇学习模块
- **学习分享**：题库分享与领取
- **消息通知 / 评论 / 轮播 / 敏感词** 等系统能力

### AI 能力
- **多模型动态路由**：DeepSeek、智谱、硅基流动等按配置选模型
- **AI 助手 Agent**：Function Calling 工具循环，支持参数校验、报错自纠
  - 工具集：题库管理、题目管理、笔记管理、记忆管理、学习统计、知识库管理与检索、题目标记等
- **RAG 知识库**：
  - 文档上传 → 解析 → 分块（jieba 中文分词）→ 向量化（bge-m3，1024 维）
  - 混合检索：**向量路（HNSW 余弦）+ 关键词路（tsvector / trigram）**
  - 知识库「屏蔽」闸门：被屏蔽的库对模型彻底不可见
- **长期记忆**：跨会话记忆摘要与按需检索
- **OCR**：图片文字识别
- **回退机制**：一轮对话的操作可撤销（含部分回退语义）

---

## 快速开始（一句话版）

本系统可运行于 **Linux 服务器 / 云沙箱 / 本机**，需要 PostgreSQL（含 pgvector、pg_trgm 扩展）、Redis、Python 3.11、Node 18+。

完成部署后访问：

| 服务 | 地址（本机） |
|---|---|
| 前端主页 | http://localhost:3167 |
| 后端文档（Swagger） | http://localhost:9101/swagger-ui.html |
| 演示账号 | `admin` / `admin123` |

> 完整的**逐步安装说明**（含各系统依赖安装命令、数据库初始化、依赖清单）、AI Key 配置、
> 以及**云端沙箱 / 公网访问**的操作，全部写在 **[`SKILL.md`](./SKILL.md)** 中。
> 若是把你的机器人 / AI 终端接入本项目，**让 AI 终端直接读取 `SKILL.md` 并按其指引执行即可**。

---

## 环境变量（AI Key 等）

后端读取 **`openstudy-fastapi/.env`**（从 `openstudy-fastapi/.env.example` 复制）。关键配置：

```dotenv
# 数据库
PG_NAME=openstudy_v2_pgsql
PG_USER=root
PG_PASSWORD=123456

# 安全：公开访问务必改成长随机串
JWT_SECRET=openstudy-change-me-in-production

# 上传目录（Linux 下必改为本机真实存在的目录）
UPLOAD_DIR=/opt/openstudy/uploadPath

# AI 模型 Key（不填则 AI 对话 / 知识库不可用，其余功能正常）
DEEPSEEK_API_KEY=
SILICONFLOW_API_KEY=      # RAG 向量化（BAAI/bge-m3）
ZHIPU_API_KEY=
```

> ⚠️ **安全提示**：请勿将任何真实密钥、数据库口令、账号信息提交到仓库。
> 所有敏感配置一律通过 `.env` 或系统环境变量注入；`.env` 已被 `.gitignore` 忽略。

---

## 技术要点

| 主题 | 说明 |
|---|---|
| 异步 ORM | SQLAlchemy 2.0 async + asyncpg，写操作用 SAVEPOINT 隔离 |
| 向量检索 | pgvector `vector(1024)`，HNSW + 余弦距离 |
| 中文全文检索 | jieba 分词写入 `content_tokens` → PG 生成列 `search_vec` |
| Agent 工具契约 | 统一结果信封 `{success, error, hint}`，描述分「模型侧（英文）/ 界面侧（中文）」两套 |
| 状态机 | 文档处理：`1待解析 → 2解析中 → 3已解析 → 5已向量化 / 4失败` |

---

## 声明

本项目为学习/研究用途。仓库中不包含任何生产密钥；使用时请自行配置各项服务凭据。
