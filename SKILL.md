---
name: openstudy-deploy
description: "OpenStudy 在线学习平台的部署安装说明书（给 AI 终端 / 部署人员）。覆盖：Linux（含华为云开发者空间 AI Shell / openEuler 沙箱）免 Docker 手动部署全流程 —— 装 PostgreSQL(+pgvector+pg_trgm)、Redis、Python 依赖、前端依赖，初始化数据库，启动前后端，并用 DevBridge 隧道暴露公网地址。触发条件：(1) 部署/启动 OpenStudy；(2) 用户说『帮我跑起来这个项目』『部署』；(3) 关键词：openstudy、部署、安装、pgvector、DevBridge、公网访问、start-all。"
---

# OpenStudy 部署安装说明书（SKILL）

> 本文件是 **OpenStudy 的部署安装说明**：面向「AI 终端 / 自动化部署」与「人工部署」。
> 面向最终使用者的**项目功能介绍**见 [`README.md`](./README.md)；本文件只讲**怎么把它装起来、跑起来、访问到**。

## 先选路线

| 你的环境 | 走哪条路线 |
|---|---|
| **Linux 服务器 / 云沙箱（华为云 AI Shell、openEuler 等）** | ⭐ **本文件正文（§1~§11）**：免 Docker，手动装各组件 |
| **用户自己的 Windows 电脑，且装了 Docker Desktop** | 见 §12「Windows Docker 一键启动」（备选，未在本项目实测） |

> ⚠️ 沙箱/云主机常常**装不了 Docker**（网络命名空间权限受限、无 systemd、openEuler 无官方支持），
> 此时一律走本文件正文的**免 Docker 手动安装**流程。

---

## 0. 一分钟速览

**要装的东西（共 5 样）**：

| # | 组件 | 版本要求 | 作用 |
|---|---|---|---|
| 1 | **PostgreSQL** | 16（14/15 亦可） | 主数据库 |
| 2 | **pgvector 扩展** | 0.5+（推荐 0.8.x） | RAG 知识库向量检索（**必须**） |
| 3 | **pg_trgm 扩展** | 附带 contrib 包 | 中文模糊检索 |
| 4 | **Redis** | 6+（推荐 7.x） | 登录态 / 验证码 / 缓存（**后端强依赖，必须先起**） |
| 5 | **Python / Node** | Python 3.11 / Node 18+ | 后端 / 前端运行时 |

**统一端口**：

| 服务 | 端口 |
|---|---|
| 前端主页 | **3167** |
| 后端 API / Swagger | **9101** |
| PostgreSQL | 5432 |
| Redis | 6379 |

**演示账号**：`admin` / `admin123`（首次登录后请改密）。

**数据库名**：`openstudy_v2_pgsql`（可在 `.env` 改，但 SQL 导入时必须一致）。

---

## 1. 整体流程（AI 终端执行清单）

```
1. 装系统依赖：PostgreSQL(+contrib) + pgvector + Redis + Python3.11 + Node20
2. 启动 PostgreSQL 与 Redis 服务，确认端口 5432 / 6379 可连
3. 【关键】在 PostgreSQL 里确认 vector 与 pg_trgm 扩展可创建
4. 建库并导入 deploy/db-init/01_openstudy_v2_pgsql_deploy.sql（结构+种子+演示数据）
5. 后端：建 venv → pip install -r requirements.txt → 写 .env → uvicorn 启动(9101)
6. 前端：npm install → npm run dev(3167)
7. 校验：curl 后端 /health 与前端登录接口，均 code==200
8. LOAD_SKILL huawei-cloud-jobenv-devbridge-tunnel，为 3167（必做）/9101（可选）建隧道
9. 从隧道日志取公网 URL，校验可达，把「前端 URL」交给用户
10. 告知用户：隧道有效期约 24h，过期后重新跑 start-all + 重建隧道
```

---

## 2. 系统依赖安装

> 下面同时给出 **Debian/Ubuntu**、**RHEL/CentOS/openEuler** 两套命令，按实际系统选用。
> **华为云开发者空间 AI Shell** 多为 openEuler / RHEL 系 —— 用第 2 组。

### 2.1 PostgreSQL + pgvector + pg_trgm

**pgvector 是本部署最容易卡住的一环**，务必装成功（RAG 向量列依赖它，缺了后端建表会失败）。

#### Debian / Ubuntu（推荐用 PGDG 官方源装 PG16）

```bash
# 官方 PGDG 源（含最新 PG + pgvector，最省事）
sudo apt update && sudo apt install -y curl ca-certificates gnupg lsb-release
sudo install -d /usr/share/postgresql-common/pgdg
curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo gpg --dearmor -o /usr/share/keyrings/postgresql.gpg
echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" | sudo tee /etc/apt/sources.list.d/pgdg.list
sudo apt update
# postgresql-16 自带 pg_trgm；postgresql-16-pgvector 是官方编译好的 pgvector
sudo apt install -y postgresql-16 postgresql-16-pgvector postgresql-contrib
```

#### RHEL / CentOS / openEuler

openEuler 自带源的 PG 版本较旧且**不带 PGXS 头文件**，导致 pgvector 编译失败。两条路任选：

**路线 R1（推荐）：装 PGDG 官方 RPM 源拿到 PG16 + pgvector**

```bash
# 安装 PGDG 仓库（RHEL 系通用）
sudo dnf install -y https://download.postgresql.org/pub/repos/yum/reporpms/EL-$(rpm -E %{rhel})-x86_64/pgdg-redhat-repo-latest.noarch.rpm
sudo dnf install -y postgresql16-server postgresql16-contrib
# pgvector：PGDG 仓库通常含 pgvector_16（包名以仓库实际为准）
sudo dnf install -y pgvector_16 2>/dev/null || echo "仓库无 pgvector 包，走源码编译见 R2"
# 头文件（编译 pgvector 或其它扩展时需要）
sudo dnf install -y postgresql16-devel
```

**路线 R2：用系统自带 PG + 源码编译 pgvector**

```bash
# 1) 装 PG 与其开发头文件（关键：必须有 -devel / pgxs）
sudo dnf install -y postgresql-server postgresql-contrib postgresql-devel
# 2) 编译安装 pgvector（GitHub 官方源码）
sudo dnf install -y git gcc make
git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git /tmp/pgvector
cd /tmp/pgvector
make            # 找不到 pg_config 时：make PG_CONFIG=$(which pg_config)
sudo make install
```

> ⚠️ **若编译报 `postgres.h: No such file or directory` 或找不到 `pgxs.mk`**：
> 说明缺 `postgresql-devel`，或版本不匹配（`pg_config` 路径不对）。
> 解决办法：装对应版本的 `-devel`（如 `postgresql16-devel`），再用 `make PG_CONFIG=/usr/pgsql-16/bin/pg_config` 指定正确的 pg_config。
>
> ⚠️ **若 dnf 源里确实拿不到 pgvector 且编译也无法进行**：见本文件 §7「无 pgvector 的应急方案」。

### 2.2 Redis

```bash
# Debian / Ubuntu
sudo apt install -y redis-server

# RHEL / openEuler
sudo dnf install -y redis
```

### 2.3 Python 3.11 与 Node 18+

```bash
# Python（多数系统已带 python3，需 ≥3.10，推荐 3.11）
python3 --version

# Node.js 20（Debian/Ubuntu 用 NodeSource；RHEL 用 dnf module）
# Debian/Ubuntu:
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
# RHEL/openEuler: sudo dnf module install -y nodejs:20
node -v && npm -v
```

---

## 3. 启动数据库与 Redis

### 3.1 启动 PostgreSQL

```bash
# Debian/Ubuntu（PGDG 装的是 16）
sudo systemctl enable --now postgresql

# RHEL/openEuler（自带 PG 或 PGDG 的 16）
sudo systemctl enable --now postgresql-16 2>/dev/null || sudo systemctl enable --now postgresql

# 若无 systemd（容器/沙箱）：手动初始化并后台启动
# PGDATA=/var/lib/pgsql/data 或 /var/lib/postgresql/16/main
# sudo -u postgres /usr/pgsql-16/bin/pg_ctl -D "$PGDATA" -l /tmp/pg.log start
```

> **沙箱无 systemd 时**：以 postgres 用户执行 `initdb` 初始化数据目录（若尚未初始化），再用 `pg_ctl start` 后台拉起。
> 常见数据目录：Debian 系 `/var/lib/postgresql/16/main`；RHEL 系 `/var/lib/pgsql/data`。

### 3.2 启动 Redis

```bash
sudo systemctl enable --now redis 2>/dev/null || sudo systemctl enable --now redis-server
# 无 systemd：
redis-server --daemonize yes
# 校验
redis-cli ping     # 期望 PONG
```

### 3.3 数据库用户与密码

项目 `.env` 默认用 **用户 `root` / 密码 `123456` / 库 `openstudy_v2_pgsql`**。
两种做法（**任选其一**）：

- **做法 A（推荐，省事）**：直接创建 `root` 用户并设密码 `123456`：
  ```bash
  sudo -u postgres psql -c "CREATE ROLE root LOGIN SUPERUSER PASSWORD '123456';"
  ```
- **做法 B**：改用 postgres 自带用户，把 `.env` 里的 `PG_USER` / `PG_PASSWORD` 改成你的实际值。

---

## 4. 初始化数据库（建库 + 导入 SQL）

```bash
cd <仓库根目录>

# 1) 建库（默认 openstudy_v2_pgsql；如自定义，务必与 .env 的 PG_NAME 一致）
sudo -u postgres createdb -O root openstudy_v2_pgsql   # 或 createdb -U root ...

# 2) 导入「结构 + 种子 + 演示数据」
psql -U root -d openstudy_v2_pgsql -f deploy/db-init/01_openstudy_v2_pgsql_deploy.sql

# 3) 校验扩展已就位（关键！）
psql -U root -d openstudy_v2_pgsql -c "SELECT extname FROM pg_extension WHERE extname IN ('vector','pg_trgm');"
# 期望输出两行：vector / pg_trgm。若 vector 缺失 → 回 §2.1 把 pgvector 装好再重来。
```

> SQL 第一段会执行 `CREATE EXTENSION IF NOT EXISTS vector;` 与 `pg_trgm`。
> **若这一步报 `could not open extension control file .../vector.control`** → pgvector 没装成功，必须先解决 §2.1。

> SQL 已清洗：**不含真实 API Key / 密码 / 隐私数据**；演示账号密码统一 `admin123`；`sys_ai_config.api_key` 为占位符，用户自行在后台填自己的 Key。

---

## 5. 启动后端（FastAPI，端口 9101）

```bash
cd openstudy-fastapi

# 1) 创建虚拟环境并装依赖（Python 3.11）
python3.11 -m venv .venv           # 无 3.11 时用 python3，但需 ≥3.10
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 2) 生成配置文件
cp .env.example .env
```

编辑 `.env`，**至少确认这几项**（连接本机服务）：

```dotenv
DB_DRIVER=postgres
PG_HOST=localhost
PG_PORT=5432
PG_NAME=openstudy_v2_pgsql
PG_USER=root
PG_PASSWORD=123456
REDIS_HOST=localhost
REDIS_PORT=6379
JWT_SECRET=换成随机长字符串
# 上传目录：改成服务器上真实存在的可写目录（默认 D:/ruoyi/uploadPath 是 Windows 路径，Linux 下必改）
UPLOAD_DIR=/opt/openstudy/uploadPath
```

```bash
# 3) 启动后端（后台 + 日志）
mkdir -p /opt/openstudy/uploadPath
nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 9101 --log-level info > /tmp/openstudy-backend.log 2>&1 &

# 4) 校验
curl -s http://localhost:9101/health        # 期望 {"code":200,...}
```

> **后端强依赖 Redis**：Redis 没起时，`app/main.py` 启动阶段 ping 失败会直接退出。先确保 §3.2 的 `redis-cli ping` 返回 PONG。

---

## 6. 启动前端（Vue3 + Vite，端口 3167）

```bash
cd openstudy-vue3-ts

# 安装依赖（package-lock.json 存在，用 npm；也可 pnpm i）
npm install

# 开发模式启动（dev server 会把 /dev-api、/ai、/system 等前缀代理到 9101）
nohup npm run dev > /tmp/openstudy-frontend.log 2>&1 &

# 校验
curl -s -o /dev/null -w "%{http_code}" http://localhost:3167/   # 期望 200
```

> 前端 dev server 默认端口 **3167**（见 `vite.config.ts`），代理目标 `http://localhost:9101`。
> 若后端不在本机 9101，改 `vite.config.ts` 里各 `target` 即可。
>
> **可选**：前端 dev 会自动尝试拉起 DS 网页桥（`startup-scripts/ds-bridge`，端口 9200）。桥依赖宿主机的 Edge/Chrome，**沙箱里通常没有浏览器 → 桥自动跳过，不影响前端运行**。

### 6.1 一键启动脚本（可选）

仓库提供 `startup-scripts/start-all.bat`（Windows）。Linux 沙箱可参照其逻辑自建 `start-all.sh`：

```bash
#!/usr/bin/env bash
# 依次：确保 PG/Redis 在跑 → 起后端(9101) → 起前端(3167)
set -e
sudo systemctl start postgresql redis 2>/dev/null || true
cd "$(dirname "$0")/../openstudy-fastapi"
nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 9101 > /tmp/backend.log 2>&1 &
cd ../openstudy-vue3-ts && nohup npm run dev > /tmp/frontend.log 2>&1 &
echo "backend: http://localhost:9101   frontend: http://localhost:3167"
```

---

## 7. 无 pgvector 的应急方案（仅在实在装不上 pgvector 时）

pgvector 若确实无法安装（源里没有、编译失败），有两种降级：

1. **仅演示非 AI 功能**：不导入含向量表的完整 SQL，改为让后端只在无 RAG 表的情况下运行。
   注意：本项目 `init_db` 会尝试 `CREATE EXTENSION vector` 并建 `rag_*` 表，**缺 pgvector 时会在建表阶段报错**。
   这需要改后端代码才能跳过 —— 若你选择此路，请联系项目作者提供「无向量」分支，**不要自行魔改**。
2. **优先目标仍是装好 pgvector**：绝大多数报错是「缺 `-devel` 头文件」或「pg_config 路径不对」，
   按 §2.1 的 R2 提示指定 `PG_CONFIG` 即可解决。**先全力尝试装成功。**

> 一句话：**pgvector 是硬依赖，能装就一定装。**

---

## 8. 用 DevBridge 隧道生成公网地址（沙箱内关键一步）

沙箱里的 `localhost` 指的是**沙箱本身**，用户浏览器访问不到，必须把端口**暴露到公网**。
华为云开发者空间提供 **DevBridge 隧道**能力，由 skill **`huawei-cloud-jobenv-devbridge-tunnel`** 提供。

**操作（AI 终端执行）**：

1. **加载隧道 skill**：`LOAD_SKILL huawei-cloud-jobenv-devbridge-tunnel`
2. **为端口建隧道**：
   - `3167` —— 前端主页（**给用户的主入口**）
   - `9101` —— 后端 API / Swagger（可选，调试用）
3. **从隧道进程日志 / skill 输出取公网 URL**，形如：
   - 前端：`https://<子域>-3167.devbridge-s2.hwtunnel.com`
   - 后端：`https://<子域>-9101.devbridge-s2.hwtunnel.com/swagger-ui.html`
4. **校验可达**：对公网 URL 发一次请求确认 200。
5. **把前端公网 URL 交给用户**。

> ⚠️ 隧道有效期约 **24 小时**。过期后重新 `start-all.sh` 并重建隧道。

---

## 9. 常见问题（FAQ）

**Q1：`localhost:3167` 打不开（云端沙箱）**
→ 你在沙箱里跑，`localhost` 是沙箱自己。按 §8 建 DevBridge 隧道，用公网 URL。

**Q2：后端启动即退出 / 日志报 Redis 连接失败**
→ Redis 没起。先 `redis-server --daemonize yes` 或 `systemctl start redis`，`redis-cli ping` 返回 PONG 后再起后端。

**Q3：后端建表报 `could not open extension control file .../vector.control`**
→ pgvector 没装成功。回 §2.1 装好 pgvector（注意 `-devel` 头文件与 `pg_config` 路径），再重新导入 SQL。

**Q4：导入 SQL 报 `database "openstudy_v2_pgsql" does not exist`**
→ 先 `createdb openstudy_v2_pgsql`（§4），且库名必须与 `.env` 的 `PG_NAME` 一致。

**Q5：登录报 `password cannot be longer than 72 bytes`**
→ `bcrypt` 版本问题。本项目 `requirements.txt` 已锁 `bcrypt==4.0.1`；若手动升过 bcrypt，请 `pip install bcrypt==4.0.1`。

**Q6：AI 对话 / 知识库报「未配置 API Key」**
→ 正常。在 `.env` 填 `DEEPSEEK_API_KEY` / `SILICONFLOW_API_KEY`，或登录后台「系统管理 → AI 模型配置」里填。

**Q7：前端页面能开，但接口全部 404**
→ 确认访问的是**前端端口 3167**；前端 dev server 会把 `/dev-api`、`/ai`、`/system` 等代理到 9101。

**Q8：`npm install` 很慢/失败**
→ 换国内镜像：`npm config set registry https://registry.npmmirror.com`；pip 同理：`pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple`。

**Q9：DS 网页桥（模型 `ds-free-nb`）用不了**
→ 该桥依赖宿主机 Edge/Chrome 做 DOM 自动化，沙箱里没有浏览器，故不可用（设计如此）。改用其它 provider（DeepSeek 官方 / 硅基流动）并在后台配置 Key。

---

## 10. 依赖清单速查（复制给 AI 终端）

| 组件 | 目标版本 | 校验命令 | 期望 |
|---|---|---|---|
| PostgreSQL | 16（≥14） | `psql --version` | PostgreSQL 16.x |
| pgvector | 0.8.x | `psql -c "SELECT extname FROM pg_extension WHERE extname='vector'"` | 有 vector 行 |
| pg_trgm | 1.x | `psql -c "...WHERE extname='pg_trgm'"` | 有 pg_trgm 行 |
| Redis | 7.x（≥6） | `redis-cli ping` | PONG |
| Python | 3.11（≥3.10） | `python3 --version` | 3.11.x |
| Node.js | 20（≥18） | `node -v` | v20.x |
| 数据库 | openstudy_v2_pgsql | `psql -lqt` | 库存在 |
| 端口 | 9101 / 3167 | `ss -lntp` | 两个都在监听 |

---

## 11. 给 AI 终端的逐步执行脚本（可直接照抄）

```bash
# ========== 1. 系统依赖 ==========
# Debian/Ubuntu:
#   sudo apt install -y postgresql-16 postgresql-16-pgvector postgresql-contrib redis-server
# RHEL/openEuler（源码编译 pgvector）:
sudo dnf install -y postgresql-server postgresql-contrib postgresql-devel redis git gcc make
git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git /tmp/pgvector && cd /tmp/pgvector && make && sudo make install

# ========== 2. 起服务 ==========
sudo systemctl start postgresql redis 2>/dev/null || { redis-server --daemonize yes; }
# 无 systemd 时用 pg_ctl start（见 §3.1）
redis-cli ping   # 期望 PONG

# ========== 3. 建库 + 用户 ==========
sudo -u postgres psql -c "CREATE ROLE root LOGIN SUPERUSER PASSWORD '123456';" 2>/dev/null || true
sudo -u postgres createdb -O root openstudy_v2_pgsql 2>/dev/null || true

# ========== 4. 导入 SQL ==========
cd <仓库根>
psql -U root -d openstudy_v2_pgsql -f deploy/db-init/01_openstudy_v2_pgsql_deploy.sql
psql -U root -d openstudy_v2_pgsql -c "SELECT extname FROM pg_extension WHERE extname IN ('vector','pg_trgm');"

# ========== 5. 后端 ==========
cd openstudy-fastapi
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # 改 UPLOAD_DIR=/opt/openstudy/uploadPath，按需填 AI Key
mkdir -p /opt/openstudy/uploadPath
nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 9101 > /tmp/backend.log 2>&1 &
sleep 5 && curl -s http://localhost:9101/health    # 期望 code 200

# ========== 6. 前端 ==========
cd ../openstudy-vue3-ts
npm install
nohup npm run dev > /tmp/frontend.log 2>&1 &
sleep 5 && curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3167/

# ========== 7. 隧道 ==========
# LOAD_SKILL huawei-cloud-jobenv-devbridge-tunnel
# 为 3167 建隧道 → 取公网 URL → 交给用户
```

---

## 12. Windows Docker 一键启动（备选路线，未实测）

> 仅当**用户自己的 Windows 电脑装了 Docker Desktop** 时可用。
> 这是备选方案；Linux / 云沙箱请走正文 §1~§11。

仓库提供了容器化文件（`docker-compose.yml`、各 `Dockerfile`、`start.bat` / `stop.bat`）。

**步骤**：

1. 安装 Docker Desktop：https://www.docker.com/products/docker-desktop/ → 安装后重启 → 等托盘鲸鱼图标变绿。
2. 进入仓库根目录，双击 **`start.bat`**（会自动：检查 Docker → 生成 `.env` → 构建并启动）。
3. 首次构建约 5~10 分钟。完成后浏览器打开 **http://localhost:3167**。
4. 停止：双击 `stop.bat`。

**容器化架构**：`db`（pgvector/pgvector:pg16）+ `redis`（redis:7）+ `backend`（FastAPI）+ `frontend`（Nginx）。
对外仅暴露 3167（前端）与 9101（后端）；数据库与 Redis 仅容器内网。
数据库种子由 `deploy/db-init/` 自动导入。

> ⚠️ 说明：Docker 路线在 **Windows** 上可用；**云端沙箱通常装不了 Docker**，不要硬试，直接走正文的手动流程。

