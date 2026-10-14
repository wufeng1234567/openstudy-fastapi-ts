---
name: openstudy-deploy
description: "OpenStudy 在线学习平台的部署安装说明书（给 AI 终端 / 部署人员）。覆盖：华为云开发者空间 AI Shell 沙箱部署 + DevBridge 隧道公网访问、Windows/macOS/Linux 本机 Docker 部署、AI Key 配置、常见问题排障。触发条件：(1) 部署/启动 OpenStudy；(2) 用户说『帮我跑起来这个项目』『一键部署』；(3) 关键词：openstudy、一键启动、docker compose、DevBridge、公网访问、部署。"
---

# OpenStudy 部署安装说明书（SKILL）

> 本文件是 **OpenStudy 的部署安装说明**：面向「AI 终端 / 自动化部署」与「人工部署」两种使用者。
> 面向最终使用者的**项目功能介绍**见 [`README.md`](./README.md)；本文件只讲**怎么把它装起来、跑起来、访问到**。

---

## 0. 一分钟速览

| 场景 | 你要做的 | 访问方式 |
|---|---|---|
| **A. 华为云开发者空间 AI Shell（云端 Linux 沙箱）** | 让 AI 终端按 §1 自动部署；再用 **DevBridge 隧道**暴露端口 | 隧道生成的**公网 URL**（§1.4） |
| **B. 用户自己的 Windows 电脑** | 装 Docker Desktop → 双击 `start.bat` | `http://localhost:3167` |
| **C. macOS / Linux 本机** | 装 Docker → `./start.sh` | `http://localhost:3167` |

**统一端口**（三种场景一致，便于记忆与隧道复用）：

| 服务 | 端口 |
|---|---|
| 前端主页 | **3167** |
| 后端 API / Swagger | **9101** |
| PostgreSQL + pgvector | 5432（仅容器内网） |
| Redis | 6379（仅容器内网） |

**演示账号**：`admin` / `admin123`（首次登录后请改密）。

---

## 1. 场景 A：华为云开发者空间 AI Shell（推荐给「用户把项目丢给 AI 终端」）

> 华为云开发者空间的 **AI Shell** 是一个云端 Linux 沙箱，AI 终端可以用自然语言驱动它执行 shell 命令装软件。
> 本项目的目标就是让**用户把仓库地址丢给 AI 终端，AI 照着本文件自动部署并给出公网地址**。

### 1.1 环境前提

AI 终端需确认沙箱内具备：

```bash
docker --version && docker compose version   # 需要 Docker + Compose 插件
```

若未安装，AI 终端自行安装（Debian/Ubuntu 系）：

```bash
# 安装 Docker（官方一键脚本）
curl -fsSL https://get.docker.com | sh
# 启动服务
sudo service docker start 2>/dev/null || sudo systemctl start docker 2>/dev/null
# 校验
docker compose version
```

### 1.2 拉取代码并进入项目根目录

```bash
git clone <仓库地址> openstudy-fastapi-ts
cd openstudy-fastapi-ts
```

> 项目根目录 = 包含 `docker-compose.yml` 的那一层。

### 1.3 一键启动

```bash
cp .env.example .env        # 首次执行；如需 AI Key 则编辑 .env
docker compose up -d --build
```

首次构建约 3~6 分钟（装 Python/Node 依赖）。启动后：

```bash
docker compose ps           # 四个容器都应为 Up / healthy
```

- 容器清单：`openstudy-db`（pgvector）、`openstudy-redis`、`openstudy-backend`、`openstudy-frontend`
- 后端首次启动会自动建表，约 20~40 秒；`openstudy-backend` 变为 `healthy` 即就绪。
- 数据库种子数据（演示账号、菜单、AI 配置等）由 `deploy/db-init/*.sql` 在**数据库首次初始化**时自动导入。

**校验部署是否成功**（在沙箱内）：

```bash
curl -s http://localhost:9101/health          # 期望 {"code":200,...}
curl -s -X POST http://localhost:3167/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}'   # 期望 {"code":200,...,"token":"..."}
```

两条都返回 `code:200` 即代表**前后端 + 数据库 + Redis 全链路正常**。

### 1.4 用 DevBridge 隧道生成公网地址（沙箱内的关键一步）

沙箱里的 `localhost` 指的是**沙箱本身**，用户的浏览器访问不到。必须把端口**暴露到公网**。
华为云开发者空间提供了 **DevBridge 隧道**能力，由名为 **`huawei-cloud-jobenv-devbridge-tunnel`** 的 skill 提供。

**操作（AI 终端执行）**：

1. **加载隧道 skill**：`LOAD_SKILL huawei-cloud-jobenv-devbridge-tunnel`
   （若当前 agent 支持 skill 机制，按该 skill 的说明操作；它负责创建隧道并返回公网 URL。）
2. **为以下端口各建一条隧道**：
   - `3167` —— 前端主页（**给用户访问的主入口**）
   - `9101` —— 后端 API / Swagger（可选，用于调试）
3. **从隧道进程日志 / skill 输出中取出公网 URL**，形如：
   - 前端：`https://<随机子域>-3167.devbridge-s2.hwtunnel.com`
   - 后端：`https://<随机子域>-9101.devbridge-s2.hwtunnel.com/docs`
4. **校验隧道可达**：对返回的公网 URL 发一次请求，确认返回 200 / 正常页面。

**把前端公网 URL 交给用户**——用户用它就能打开 OpenStudy。后端隧道 URL 用于访问 `/swagger-ui.html` 或 `/docs`。

> ⚠️ **隧道有有效期（通常 24 小时）**。过期后重新执行：
> ```bash
> bash ./start.sh          # 若服务已停：重新拉起
> # 然后重新建立 DevBridge 隧道（重复 §1.4 步骤）
> ```

### 1.5 日常运维命令

```bash
docker compose logs -f backend      # 看后端日志
docker compose logs -f frontend     # 看前端/Nginx 日志
docker compose restart backend      # 重启后端
docker compose down                 # 停止（保留数据）
docker compose down -v              # 停止并清空数据卷（慎用）
```

---

## 2. 场景 B：用户自己的 Windows 电脑（Docker Desktop）

### 2.1 安装 Docker Desktop（给小白的分步教学）

1. 打开官网下载页：**https://www.docker.com/products/docker-desktop/**
2. 点 **Download for Windows**，下载 `Docker Desktop Installer.exe`。
3. 双击安装，**保持默认勾选**（尤其是 “Use WSL 2 instead of Hyper-V”），一路 Next → Install。
4. 安装完成后**重启电脑**。
5. 重启后打开 **Docker Desktop**，等待左下角/托盘的鲸鱼图标变成**绿色（Running）**。
6. （可选）首次可能需要登录 Docker 账号，可跳过。

> **系统要求**：Windows 10/11 64 位，开启 WSL2（安装程序会引导）。内存建议 ≥ 8GB。

### 2.2 启动项目

1. 把项目文件夹拷到本机（含 `docker-compose.yml` 的那一层）。
2. 双击 **`start.bat`**（会自动：检查 Docker → 若无 `.env` 则从 `.env.example` 生成 → 构建并启动）。
3. 首次构建约 5~10 分钟，请耐心等待。
4. 脚本结束会打印访问地址，浏览器打开 **http://localhost:3167**。

**停止服务**：双击 `stop.bat`。

### 2.3 配置 AI Key（可选）

编辑项目根目录 `.env`，填入你自己的 Key：

```dotenv
DEEPSEEK_API_KEY=sk-xxxxxxxx          # DeepSeek 官方（对话/生成）
SILICONFLOW_API_KEY=sk-xxxxxxxx       # 硅基流动（RAG 知识库向量化）
ZHIPU_API_KEY=                        # 智谱（可选）
```

改完 `.env` 后重启后端生效：

```bat
docker compose restart backend
```

不上 Key 也能用：除 AI 对话与知识库向量化外，其余学习功能全部正常。

---

## 3. 场景 C：macOS / Linux 本机

```bash
git clone <仓库地址> openstudy-fastapi-ts
cd openstudy-fastapi-ts
cp .env.example .env          # 如需 AI Key 则编辑
./start.sh                    # 自动检查 Docker → 构建 → 启动
```

访问 **http://localhost:3167**。停止：`./stop.sh`。

若提示权限不足，把当前用户加入 docker 组后重新登录：

```bash
sudo usermod -aG docker $USER
```

---

## 4. 服务组成与端口（排查时对照）

`docker-compose.yml` 定义四个服务，均接入私有网络 `openstudy`：

| 服务 | 镜像 / 构建 | 宿主端口 | 作用 |
|---|---|---|---|
| `db` | `pgvector/pgvector:pg16` | 无（仅内网） | PostgreSQL 16 + **pgvector** + **pg_trgm** |
| `redis` | `redis:7-alpine` | 无（仅内网） | 登录态 / 验证码 / 缓存 |
| `backend` | `openstudy-fastapi/Dockerfile` | `9101` | FastAPI（容器内 9101） |
| `frontend` | `openstudy-vue3-ts/Dockerfile` | `3167` | Nginx 托管 Vue 产物 + 反代后端 |

**数据持久化（命名卷）**：`openstudy_pgdata`（数据库）、`openstudy_redisdata`（Redis）、`openstudy_uploads`（用户上传文件）。
`docker compose down` **不会**删除这些卷；`down -v` 才会。

---

## 5. 常见问题（FAQ）

**Q1：`localhost:3167` 打不开（云端沙箱场景）**
→ 你在沙箱里跑，`localhost` 是沙箱自己，浏览器访问不到。请按 **§1.4** 建 DevBridge 隧道，用公网 URL。

**Q2：后端容器一直 unhealthy / 反复重启**
→ 大概率是数据库还没就绪。`docker compose logs backend` 看报错；等 `openstudy-db` 显示 `healthy` 后后端会自动重试。若持续失败，检查 `.env` 的 `PG_*` 是否被意外改动。

**Q3：登录报 “password cannot be longer than 72 bytes”**
→ 这是 `bcrypt` 版本不兼容（passlib 1.7.4 需 `bcrypt<4.1`）。本项目 `requirements.txt` 已锁 `bcrypt==4.0.1`，正常构建不会出现。若你手动改过依赖，请恢复该版本并 `docker compose build backend`。

**Q4：AI 对话 / 知识库报 “未配置 API Key”**
→ 正常，未填 Key 时 AI 功能不可用。按 §2.3 填 `.env` 后 `docker compose restart backend`。

**Q5：前端页面能开，但所有接口 404 / 报错**
→ 确认访问的是**前端端口 3167**（不是 9101）。前端 Nginx 会把 `/login`、`/system`、`/ai` 等前缀反代到后端；直接访问后端端口会绕过反代。

**Q6：想彻底重来（清空所有数据）**
→ `docker compose down -v && docker compose up -d --build`

**Q7：DS 网页桥（模型 `ds-free-nb`）为什么用不了？**
→ 该桥依赖**宿主机本地的 Edge/Chrome 浏览器**做 DOM 自动化，未纳入容器（设计如此）。容器版不提供该模型；如需，请改用其它 provider（DeepSeek 官方 / 硅基流动等）并在后台配置对应 Key。

---

## 6. 给 AI 终端的执行清单（可直接照做）

```
1. 确认沙箱有 docker + docker compose；没有则 curl -fsSL https://get.docker.com | sh
2. git clone <仓库> && cd <仓库根>（含 docker-compose.yml 的目录）
3. cp .env.example .env
4. docker compose up -d --build
5. 轮询 docker compose ps，直到 backend 为 healthy（约 20-40s）
6. 校验：
   curl -s localhost:9101/health
   curl -s -X POST localhost:3167/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}'
   两者 code==200 即成功
7. LOAD_SKILL huawei-cloud-jobenv-devbridge-tunnel
8. 为 3167（必做）和 9101（可选）各建一条 DevBridge 隧道
9. 从日志取出公网 URL，校验可达，把「前端 URL」交给用户
10. 告知用户：隧道有效期约 24h，过期后重新跑 start.sh 并重建隧道
```
