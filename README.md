# OpenStudy 在线学习平台

> 一个面向在线学习场景的全栈应用：题库刷题、错题本、笔记、学习分享、消息通知，并内置 **AI 助手（Agent + RAG 知识库 + 长期记忆）**。

- **后端**：Python 3 · FastAPI · SQLAlchemy 2.0（异步）· PostgreSQL + pgvector
- **前端**：Vue 3 · TypeScript · Vite · Element Plus · Pinia
- **AI**：LangChain · DeepSeek / 智谱 / 硅基流动 多模型动态路由

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
│   ├── tests/                # 测试与联调脚本
│   ├── requirements.txt      # Python 依赖
│   └── .env.example          # 环境变量样例（真实 .env 不入库）
├── openstudy-vue3-ts/        # 前端（Vue3 + TS）
│   ├── src/
│   │   ├── api/              # 接口封装
│   │   ├── views/            # 页面（admin 后台 / front 前台 / ai / …）
│   │   ├── components/       # 通用组件
│   │   ├── layout/           # 布局
│   │   └── utils/            # 工具
│   └── package.json
├── docs/                     # 设计与交付文档
├── startup-scripts/          # 一键启动脚本（Windows）
└── README.md
```

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

## 快速开始

### 环境要求
| 组件 | 版本 |
|---|---|
| Python | 3.10+ |
| Node.js | 18+（推荐 20/22） |
| PostgreSQL | 14+（需 `pgvector` 扩展） |
| Redis | 6+（可选，用于缓存/会话） |

### 1. 克隆仓库
```bash
git clone https://gitcode.com/qi142410131/openstudy-fastapi-ts.git
cd openstudy-fastapi-ts
```

### 2. 数据库（PostgreSQL 16，需 pgvector + pg_trgm）
```bash
# 建库并导入「结构 + 种子 + 演示数据」（已清洗所有真实 Key）
createdb openstudy_v2_pgsql
psql -U root -d openstudy_v2_pgsql -f startup-scripts/db/openstudy_v2_pgsql_deploy.sql
```
详见 `startup-scripts/db/README.md`。演示账号：`admin / admin123`（首次登录后请改密）。

### 3. 后端启动
```bash
cd openstudy-fastapi

# 创建虚拟环境
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
# source .venv/bin/activate

pip install -r requirements.txt

# 配置环境变量：复制样例并填写（切勿提交真实 .env）
# 需要配置：数据库连接、JWT 密钥、AI 服务密钥等
# cp .env.example .env

# 启动
uvicorn app.main:app --host 0.0.0.0 --port 9101 --reload
```

后端接口文档（Swagger）：`http://localhost:9101/docs`

### 4. 前端启动
```bash
cd openstudy-vue3-ts
npm install
npm run dev
```

前端默认地址：`http://localhost:80`（见 `.env.development`）。
`npm run dev` 会自动随前端拉起 **DS 网页桥**（`startup-scripts/ds-bridge`，端口 `9200`，模型 `ds-free-nb`，无头运行）。

### 5. DS 网页桥（可选，提供 `ds-free-nb` 模型）
```bash
startup-scripts/start-ds-bridge.bat   # 单独启动/查看桥（默认无头，无窗口）
# 首次登录：在 startup-scripts/ds-bridge 下执行  node probe.js --login
```
- 桥用本机 Edge 的**持久化 profile** 保存 DeepSeek 登录态，免插件。
- 在 OpenStudy 里选模型「DS 免费（无浏览器）」；输入框旁的「调试」按钮可临时打开可见窗口。

### 6. 一键启动（Windows）
```bash
startup-scripts/start-all.bat   # 启动后端(9101) + 前端(3167)；已运行的服务会跳过；桥随前端自动起
```

---

## 环境变量

后端读取 `openstudy-fastapi/.env`，**该文件已被 `.gitignore` 忽略，禁止提交**。关键配置项：

```dotenv
# 数据库（PostgreSQL 主线）
DB_DRIVER=postgres
PG_HOST=localhost
PG_PORT=5432
PG_NAME=openstudy
PG_USER=<your-db-user>
PG_PASSWORD=<your-db-password>

# JWT
JWT_SECRET=<your-secret>

# AI 模型（按需配置）
DEEPSEEK_API_KEY=<your-deepseek-key>
SILICONFLOW_API_KEY=<your-siliconflow-key>   # RAG 向量化

# 上传目录
UPLOAD_DIR=<absolute-writable-path>
```

> ⚠️ **安全提示**：请勿将任何真实密钥、数据库口令、账号信息提交到仓库。所有敏感配置一律通过 `.env` 或系统环境变量注入。

---

## 测试

```bash
cd openstudy-fastapi
# 单元测试 / 联调脚本见 tests 目录
pytest
```

后端测试指引详见 `openstudy-fastapi/TEST_GUIDE.md`。

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

## 文档

- `docs/fastapi_v2_交付部署环境要求.md` — 部署环境要求
- `docs/fastapi_v2_agent_knowledge_ingest_方案.md` — Agent 知识库写入能力方案

---

## 声明

本项目为学习/研究用途。仓库中不包含任何生产密钥；使用时请自行配置各项服务凭据。
