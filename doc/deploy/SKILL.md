---
name: openstudy-deploy
description: "OpenStudy 在线学习平台的部署安装说明书（给 AI 终端 / 部署人员）。首选方案：Linux 服务器上用 Docker Compose 一条命令起全套（pgvector+Redis+前后端）。备选：无 Docker 环境的手动安装（华为云 AI Shell / openEuler 沙箱）。含数据库一键导入、演示账号、公网访问说明。触发条件：(1) 部署/启动 OpenStudy；(2) 用户说『帮我跑起来这个项目』『部署到服务器』；(3) 关键词：openstudy、部署、安装、docker、pgvector、公网访问。"
---

# OpenStudy 部署安装说明书（SKILL）

> 本文件是 **OpenStudy 的部署安装说明**：面向「AI 终端 / 自动化部署」与「人工部署」。
> 面向最终使用者的**项目功能介绍**见 [`README.md`](./README.md)；本文件只讲**怎么把它装起来、跑起来、访问到**。

## 先选路线

| 你的环境 | 走哪条路线 | 难度 |
|---|---|---|
| ⭐ **Linux 服务器（云主机 / 自有服务器，有 root）** | **§A「服务器 Docker 一键部署」** —— 一条命令起全套 | 极简（推荐） |
| **华为云 AI Shell / openEuler 沙箱（Docker 装不了）** | §1~§11「免 Docker 手动安装」 | 繁琐 |
| **Windows 电脑 + Docker Desktop** | §12「Windows Docker 一键启动」 | 简单 |
| **需要公网地址供外部访问** | 见 §B「公网访问与常驻」 | — |

> 🔑 **一句话**：**只要服务器能用 Docker（能装 Docker），就用 §A，一条命令搞定，别去手动装。**
> 手动安装（§1~§11）只留给「Docker 确实装不了」的沙箱环境。

---

## §A. 服务器 Docker 一键部署（首选）

**前提**：一台 Linux 服务器（Ubuntu / CentOS / Debian / openEuler 均可），有 root 或 sudo。

### A.1 安装 Docker（服务器上一次即可）

```bash
# 官方一键脚本（支持主流发行版）
curl -fsSL https://get.docker.com | sh
# 启动 Docker
sudo systemctl enable --now docker
# 校验
docker --version && docker compose version
```

> 若 `docker compose` 提示找不到：装 compose 插件
> `sudo apt install -y docker-compose-plugin`（Debian/Ubuntu）或 `sudo dnf install -y docker-compose-plugin`（RHEL）。

### A.2 拉取代码并一键启动

```bash
git clone https://gitcode.com/123456/openstudy-fastapi-ts.git
cd openstudy-fastapi-ts

# 可选：配置 AI Key（不填则 AI 功能不可用，其余功能正常）
cp .env.example .env
# 编辑 .env 填 DEEPSEEK_API_KEY / SILICONFLOW_API_KEY

# 一键构建并启动（首次约 5~10 分钟）
docker compose up -d --build
```

### A.3 完成，访问

| 服务 | 地址 |
|---|---|
| 前端主页 | `http://<服务器IP>:3167` |
| 后端接口文档 | `http://<服务器IP>:9101/swagger-ui.html` |

**演示账号**（数据库已自动初始化，无需任何额外操作）：

| 账号 | 密码 |
|---|---|
| `admin` | `admin123` |
| `user1` / `user2` | `123456` |
| `guest` | 一键登录 |

> 数据库首次启动会**自动导入**两份 SQL（结构 + 演示数据），无需手动执行。
> 容器四件套：`db`（pgvector/pg16）+ `redis` + `backend` + `frontend`（Nginx）。
> 数据持久化在 Docker 卷（`openstudy_pgdata` 等），重启不丢。

### A.4 常用运维命令

```bash
docker compose ps                  # 查看状态
docker compose logs -f backend     # 看后端日志
docker compose restart backend     # 重启后端（改 .env 后执行）
docker compose down                # 停止（保留数据）
docker compose down -v             # 停止并清空数据（慎用）
```

### A.5 防火墙放行端口

```bash
# 云服务器还需在「安全组」里放行 3167
sudo firewall-cmd --add-port=3167/tcp --permanent && sudo firewall-cmd --reload   # firewalld
# 或 sudo ufw allow 3167/tcp    # ufw
```

---

## §B. 公网访问与常驻（供外部访问）

### B.1 直接暴露端口
服务器有公网 IP 时，放行 3167 端口后，`http://<公网IP>:3167` 即可访问。
建议在 `.env` 里把 `JWT_SECRET` 改成长随机串。

### B.2 绑定域名 + HTTPS（可选，更专业）
用 Nginx/Caddy 反代到 `127.0.0.1:3167`，配好域名和证书即可。

### B.3 常驻保障
`docker-compose.yml` 已给所有服务配 `restart: unless-stopped`，服务器重启后容器自动拉回。
如需开机自启：`sudo systemctl enable docker`。

> ⚠️ **不用** DevBridge 隧道（`hwtunnel.com`）对外长期提供访问——隧道 24~72h 就失效，只适合临时调试。

---

## 0. 一分钟速览

> 🔴 **华为云 AI Shell / openEuler 沙箱：不要尝试 Docker**。
> 实测装不了（官方脚本不支持 openEuler，dnf 装的 18.09 太旧，手动起 dockerd 因**网络命名空间权限不足**失败）。
> **沙箱环境按本文件 §1~§11 走无 Docker 手动安装；服务器环境用 §A 的 Docker 一键部署。**

**要装的东西（共 5 样）**：

| # | 组件 | 版本要求 | 作用 |
|---|---|---|---|
| 1 | **PostgreSQL** | 16 优先；openEuler 自带 13 也可用 | 主数据库 |
| 2 | **pgvector 扩展** | 0.5+（实测沙箱编译 0.5.1 成功） | RAG 知识库向量检索（**必须**） |
| 3 | **pg_trgm 扩展** | 附带 contrib 包 | 中文模糊检索 |
| 4 | **Redis** | 6+（推荐 7.x） | 登录态 / 验证码 / 缓存（**后端强依赖，必须先起**） |
| 5 | **Python / Node** | Python 3.11 / Node 18+ | 后端 / 前端运行时 |

**两个高频坑（务必先看）**：

- **pgvector 编译**：openEuler 的 `postgresql-devel` **不含** PGXS 头文件，常规 `make` 必失败 →
  按 §2.1 的 **R2** 用「下 PG 源码 + configure + 手建 PGXS」的方式编译。
- **bcrypt 版本**：全新 pip 会装 bcrypt 5.x，与 passlib 1.7.4 不兼容 → 登录报
  `password cannot be longer than 72 bytes`。必须 `pip install bcrypt==4.0.1`（requirements.txt 已锁，但手动装依赖时注意）。

**统一端口**：

| 服务 | 端口 |
|---|---|
| 前端主页 | **3167** |
| 后端 API / Swagger | **9101** |
| PostgreSQL | 5432 |
| Redis | 6379 |

**演示账号**：`admin` / `admin123`（SQL 自带，可管理员登录）。
> 「一键登录」的 user1/user2/guest 也已由 `97_demo_seed.sql` 一并导入，见 **§4.1**。

**数据库名**：`openstudy_v2_pgsql`（可在 `.env` 改，但 SQL 导入时必须一致）。

---

## 1. 整体流程（AI 终端执行清单）

```
1. 【先别装 Docker】沙箱/云主机直接走无 Docker 流程
2. 装系统依赖：PostgreSQL(+contrib) + pgvector + Redis + Python3.11 + Node20
   - openEuler 的 pgvector 走 §2.1 R2（下 PG 源码 + 手建 PGXS + 编译）
3. 启动 PostgreSQL 与 Redis（无 systemd 时用 pg_ctl / redis-server --daemonize）
4. 【关键】确认 vector 与 pg_trgm 扩展可创建
5. 建库，依次导入 4 份 SQL（**顺序不能乱**）：
   - deploy/db-init/01_openstudy_v2_pgsql_deploy.sql（结构+基础种子）
   - deploy/db-init/05_change_password.sql（把演示账号密码改为强密码，防他人乱登）
   - deploy/db-init/97_demo_seed.sql（演示账号 user1/user2 + 题库/笔记等演示数据）
   - deploy/db-init/98_social_seed.sql（评论/分享/通知，让页面不空）
6. 后端：venv → pip install -r requirements.txt（确保 bcrypt==4.0.1）→ 写 .env → uvicorn 启动(9101)
   - RAG 向量化默认用**本地模型**（EMBEDDING_BACKEND=auto），首次导入知识库会下载 bge-m3（约 2.2GB）
   - 若服务器内存 < 4GB，设 EMBEDDING_BACKEND=siliconflow 并配 SILICONFLOW_API_KEY 走云端
7. 前端：npm install → npm run dev(3167)
8. 校验：curl 后端 /health 与前端登录接口，均 code==200
9. LOAD_SKILL huawei-cloud-jobenv-devbridge-tunnel，为 3167（必做）/9101（可选）建隧道
10. 从隧道日志取公网 URL，校验可达，把「前端 URL」交给用户
11. 告知用户：隧道有效期约 24~72h，过期后重建隧道（服务不用重启）
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

openEuler 自带源的 PG 版本较旧（实测 **13.12**），且**不提供 PGXS 头文件**（`pgxs.mk` / `postgres.h`），
导致 pgvector 常规编译失败。按下面顺序尝试，**R2 是华为云沙箱实测走通的路径**。

**路线 R1：装 PGDG 官方 RPM 源拿到 PG16 + pgvector**（沙箱网络受限时常拿不到，拿不到就走 R2）

```bash
sudo dnf install -y https://download.postgresql.org/pub/repos/yum/reporpms/EL-$(rpm -E %{rhel})-x86_64/pgdg-redhat-repo-latest.noarch.rpm
sudo dnf install -y postgresql16-server postgresql16-contrib
sudo dnf install -y pgvector_16 2>/dev/null || echo "仓库无 pgvector 包，走 R2"
sudo dnf install -y postgresql16-devel
```

**路线 R2（开放欧拉沙箱实测成功）：用系统自带 PG + 从源码补齐 PGXS 头文件 + 编译 pgvector**

> 关键点：openEuler 的 `postgresql-devel` 里**没有** `pgxs.mk` 和 `postgres.h`，
> 所以必须**下载与系统 PG 同版本的源码**，`./configure` 出头文件，手动搭出 PGXS 目录，再编译 pgvector。

```bash
# ---- 1) 装系统 PG + 编译工具 ----
sudo dnf install -y postgresql-server postgresql-contrib redis git gcc make bison flex readline-devel zlib-devel

# 查系统 PG 版本（决定下哪份源码）
rpm -q postgresql-server            # 例如 postgresql-server-13.12-...
pg_config --version

# ---- 2) 启动 PG 并 initdb（无 systemd，手动来）----
sudo -u postgres /usr/bin/initdb -D /var/lib/pgsql/data 2>/dev/null || true
sudo -u postgres /usr/bin/pg_ctl -D /var/lib/pgsql/data -l /tmp/pg.log start
# 或：sudo systemctl start postgresql（有 systemd 时）

# ---- 3) 下载「同版本」PG 源码（用华为云镜像，快且稳）----
cd /tmp
# 版本号换成上面 rpm -q 查到的实际版本，例如 13.12
PGVER=13.12
curl -fL -o postgresql-$PGVER.tar.gz \
  https://mirrors.huaweicloud.com/postgresql/source/v$PGVER/postgresql-$PGVER.tar.gz \
  || wget https://mirrors.huaweicloud.com/postgresql/source/v$PGVER/postgresql-$PGVER.tar.gz
tar xzf postgresql-$PGVER.tar.gz
cd postgresql-$PGVER

# ---- 4) configure 生成 config 头文件（不真正安装，只为拿头文件/PGXS）----
./configure --without-readline --without-zlib

# ---- 5) 手动搭出 PGXS 目录结构，指向系统 PG 的扩展目录 ----
PG_SHAREDIR=$(pg_config --sharedir)          # 如 /usr/share/pgsql
PG_LIBDIR=$(pg_config --pkglibdir)           # 如 /usr/lib64/pgsql
sudo mkdir -p "$PG_SHAREDIR/extension" "$PG_SHAREDIR/pgxs" "$PG_LIBDIR/extension"
# 把源码里的 PGXS 模板复制到系统 sharedir（pgvector 的 Makefile 会去这里找 pgxs.mk）
sudo cp -r src/makefiles/* "$PG_SHAREDIR/pgxs/" 2>/dev/null || true
sudo cp src/Makefile.global "$PG_SHAREDIR/pgxs/src/Makefile.global" 2>/dev/null || true
# 生成 Makefile.global / Makefile.port（configure 已产出 src/Makefile.global）
# 若报 Makefile.port 缺失，手动补：
sudo tee "$PG_SHAREDIR/pgxs/src/Makefile.port" >/dev/null <<'EOF'
# Minimal Makefile.port stub
EOF

# ---- 6) 编译安装 pgvector（版本可自选，沙箱实测 0.5.1 成功）----
cd /tmp
git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git
# GitHub 慢/不通时用镜像：git clone https://gitee.com/mirrors/pgvector.git
cd pgvector
make PG_CONFIG=$(which pg_config)
sudo make install

# ---- 7) 校验扩展文件就位 ----
ls "$(pg_config --sharedir)/extension/" | grep vector   # 应看到 vector.control 等
```

> ⚠️ **R2 常见报错与对策**：
> - `postgres.h: No such file or directory` → 第 4 步 `./configure` 没执行或没成功。
> - `pgxs.mk: No such file` / 找不到 PGXS → 第 5 步目录没搭对，检查 `pg_config --sharedir` 路径。
> - `Makefile.port could not be read` → 第 5 步末尾的 stub 没建。
> - 下载 PG 源码**不完整**（tar 报错）→ 换华为云镜像（已用），或重试 `curl -fL`。
>
> ⚠️ 若 R1/R2 都最终失败：见 §7「无 pgvector 的应急方案」。

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

**依次导入 4 份 SQL**（顺序不能乱），即可获得完整可演示环境：

```bash
cd <仓库根目录>

# 1) 建库（默认 openstudy_v2_pgsql；如自定义，务必与 .env 的 PG_NAME 一致）
createdb -U root openstudy_v2_pgsql        # 或 sudo -u postgres createdb -O root openstudy_v2_pgsql

# 2) 结构 + 基础种子（建表、菜单、admin/demo 账号等）
psql -U root -d openstudy_v2_pgsql -f deploy/db-init/01_openstudy_v2_pgsql_deploy.sql

# 3) 演示账号改强密码（防他人乱登）
psql -U root -d openstudy_v2_pgsql -f deploy/db-init/05_change_password.sql

# 4) 演示数据：user1/user2 + 演示题库 + 学习统计/错题/收藏/笔记
psql -U root -d openstudy_v2_pgsql -f deploy/db-init/97_demo_seed.sql

# 5) 社交数据：评论 / 分享 / 站内通知（让页面不空）
psql -U root -d openstudy_v2_pgsql -f deploy/db-init/98_social_seed.sql

# 6) 校验扩展已就位（关键！）
psql -U root -d openstudy_v2_pgsql -c "SELECT extname FROM pg_extension WHERE extname IN ('vector','pg_trgm');"
# 期望输出两行：vector / pg_trgm。若 vector 缺失 → 回 §2.1 把 pgvector 装好再重来。
```

> SQL 第一段会执行 `CREATE EXTENSION IF NOT EXISTS vector;` 与 `pg_trgm`。
> **若报 `could not open extension control file .../vector.control`** → pgvector 没装成功，必须先解决 §2.1。
>
> 所有 SQL 已清洗：**不含真实 API Key / 隐私数据**；`sys_ai_config.api_key` 为占位符，用户自行在后台填自己的 Key。

### 4.1 演示账号（导入上面 4 份 SQL 后即全部就位）

| 账号 | 密码 | 说明 |
|---|---|---|
| `admin` | `123456` | 管理员（可进后台） |
| `user1` | `123456` | 普通用户，带 **2 个演示题库**（10 题 + 8 题）+ 学习统计/错题/收藏/笔记 |
| `user2` | `123456` | 普通用户（分享接收方） |
| `guest` | 免密（一键登录） | 只读游客 |

> ⚠️ **密码由 `05_change_password.sql` 统一改为强密码**（默认 `123456`）。
> 想换密码：跑 `python -c "from app.core.security import hash_password; print(hash_password('新密码'))"`
> 生成 bcrypt 哈希，替换该 SQL 里的值（或直接在数据库里 UPDATE）。
>
> 登录页的**「一键登录」**按钮对应 `user1 / user2 / guest / admin`，导入后**全部可用**。

### 4.2 演示模式 vs 体验版（`sys.demo.mode`）

数据库配置项 `sys.demo.mode` 控制登录页行为：

| 值 | 登录页表现 | 适用 |
|---|---|---|
| `true`（默认） | 显示「演示账号 · 一键登录」入口 | 自己演示/自用 |
| `false` | **直接显示账号密码登录 / 注册**，不暴露演示账号 | 上线给别人体验 |

切换：管理员登录后台 →「系统管理 → 参数设置」→ 搜索「演示模式」→ 改值（即时生效，无需重启）。

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

# ---------- AI ----------
# 对话模型（DeepSeek 官方）
DEEPSEEK_API_KEY=你的deepseek key
# RAG 知识库向量化后端：
#   auto（默认）—— 优先本地模型，不可用再回退硅基流动
#   local       —— 纯本地（需 sentence-transformers + 足够内存，无需任何 Key）
#   siliconflow —— 走云端（需下面的 SILICONFLOW_API_KEY；内存 <4GB 的机器建议用这个）
EMBEDDING_BACKEND=auto
SILICONFLOW_API_KEY=          # 仅 siliconflow / auto 回退时需要
```

> **本地向量化说明**：`EMBEDDING_BACKEND=local/auto` 时，后端用本地 `bge-m3` 模型做向量化，
> **不需要任何外部 Key**。首次导入知识库文档时会自动下载模型（约 2.2GB）到缓存目录，
> 之后离线可用。内存建议 ≥4GB。
> 内存较小的机器（如 2GB）请设 `EMBEDDING_BACKEND=siliconflow` 并配 `SILICONFLOW_API_KEY`。

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
2. **按该 skill 的「Quick Create Flow」创建隧道**，为端口建隧道：
   - `3167` —— 前端主页（**给用户的主入口**）
   - `9101` —— 后端 API / Swagger（可选，调试用）
3. **取公网 URL**（从隧道输出 / 进程日志）。实测格式为：
   `https://<隧道ID>-<端口>.devbridge-s2.hwtunnel.com`
   - 例（实测成功）：`https://gb3wa6li-3167.devbridge-s2.hwtunnel.com`
4. **校验可达**：用权威方式对公网 URL 发一次请求，确认返回 200。
5. **把前端公网 URL 交给用户**。

> ⚠️ 隧道有效期约 **24~72 小时**（以 skill 输出为准）。
> 过期后**只需重建隧道**，后端/前端服务不用重启（它们还在沙箱里跑着）。

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

**Q9：AI 对话用哪个模型？**
→ 登录后台「系统管理 → AI 模型配置」，选 DeepSeek 官方（`deepseek-flash` / `deepseek-v4-pro`）并填入自己的 API Key；RAG 知识库向量化用硅基流动 Key。不填 Key 时 AI 功能不可用，其余学习功能正常。

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
| 演示账号 | user1/user2/guest | `psql -c "SELECT user_name FROM sys_user"` | 含 user1/user2/guest（导入 97_demo_seed.sql 后即有） |
| 端口 | 9101 / 3167 | `ss -lntp` | 两个都在监听 |

---

## 11. 给 AI 终端的逐步执行脚本（可直接照抄）

```bash
# ========== 1. 系统依赖 ==========
# Debian/Ubuntu:
#   sudo apt install -y postgresql-16 postgresql-16-pgvector postgresql-contrib redis-server
# RHEL/openEuler（pgvector 需源码编译，详见 §2.1 R2）:
sudo dnf install -y postgresql-server postgresql-contrib redis git gcc make
# ⚠️ openEuler 需先补齐 PGXS 头文件再编译 pgvector（见 §2.1 R2 完整步骤）

# ========== 2. 起服务 ==========
sudo systemctl start postgresql redis 2>/dev/null || { redis-server --daemonize yes; }
# 无 systemd 时用 pg_ctl start（见 §3.1）
redis-cli ping   # 期望 PONG

# ========== 3. 建库 + 用户 ==========
sudo -u postgres psql -c "CREATE ROLE root LOGIN SUPERUSER PASSWORD '123456';" 2>/dev/null || true
sudo -u postgres createdb -O root openstudy_v2_pgsql 2>/dev/null || true

# ========== 4. 导入 SQL（两份）==========
cd <仓库根>
psql -U root -d openstudy_v2_pgsql -f deploy/db-init/01_openstudy_v2_pgsql_deploy.sql
psql -U root -d openstudy_v2_pgsql -f deploy/db-init/97_demo_seed.sql
psql -U root -d openstudy_v2_pgsql -c "SELECT extname FROM pg_extension WHERE extname IN ('vector','pg_trgm');"

# ========== 5. 后端依赖与配置 ==========
cd openstudy-fastapi
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # 改 UPLOAD_DIR=/opt/openstudy/uploadPath，按需填 AI Key
mkdir -p /opt/openstudy/uploadPath

# ========== 6. 启动后端 ==========
nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 9101 > /tmp/backend.log 2>&1 &
sleep 5 && curl -s http://localhost:9101/health    # 期望 code 200

# ========== 7. 前端 ==========
cd ../openstudy-vue3-ts
npm install
nohup npm run dev > /tmp/frontend.log 2>&1 &
sleep 5 && curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3167/

# ========== 8. 隧道 ==========
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

