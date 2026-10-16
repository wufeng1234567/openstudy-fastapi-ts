# OpenStudy 项目说明

## 启动服务（最重要）

用户说"启动"、"开机"、"start"时，立即执行：

```bash
bash /root/start.sh
```

等价于 `bash /root/workspace/openstudy-fastapi-ts/daily-start.sh`

脚本会自动：
- 检查并安装缺失的依赖（PostgreSQL、Redis、pgvector）
- 启动 PostgreSQL → 导入SQL种子数据(首次) → Redis → 后端(9101) → Nginx前端(3167)
- 复用或新建 DevBridge 隧道(30天固定)
- 启动 SQL 定时备份（每6小时）

## ⚠️ 部署前必做检查（LLM 执行 daily-start.sh 前必读）

**部署前检查（开一遍）：**
1. `.env.docker` 中 `VITE_APP_BASE_API` 必须是空字符串 `''`，**不能是 `/`**（否则所有 API 调用变成 `//ai/agent/...`，浏览器解析主机名报 ERR_NAME_NOT_RESOLVED）
2. `public/carousel-static/` 目录存在且包含 `carousel-1~5.jpg`（否则轮播图 404）
3. Nginx 配置用 `map $http_accept` 区分浏览器导航和 API 调用（否则 SPA 路由刷新 404）
4. PostgreSQL 数据目录在 `/root/workspace/pgsql-data`（持久化，否则重启丢数据）

**部署后验证（检查一遍）：**
```bash
URL="https://***REMOVED***"
COOKIE="bridge_phishing_protection=1"

# 1. 首页能加载
curl -s -H "Accept: text/html" -H "Cookie: $COOKIE" "$URL/" | grep -q "openstudy" && echo "✅ 首页" || echo "❌ 首页"

# 2. SPA 路由刷新不空白
curl -s -H "Accept: text/html" -H "Cookie: $COOKIE" "$URL/front/messages/notifications" | grep -q "openstudy" && echo "✅ SPA路由" || echo "❌ SPA路由"

# 3. API 不报 ERR_NAME_NOT_RESOLVED（检查构建产物无双斜杠）
grep -q '//ai/agent' /var/www/openstudy-dist/assets/*.js && echo "❌ 双斜杠bug" || echo "✅ API URL正常"

# 4. 轮播图能加载
curl -s -o /dev/null -w "%{http_code}" "$URL/carousel-static/carousel-1.jpg" | grep -q "200" && echo "✅ 轮播图" || echo "❌ 轮播图"

# 5. 登录能成功（admin 走账号密码；演示账号走一键登录 /quickLogin）
curl -s -X POST "$URL/login" -H "Content-Type: application/json" -d '{"username":"admin","password":"***REMOVED***"}' | grep -q "操作成功" && echo "✅ 登录" || echo "❌ 登录"

# 6. AI 接口能访问（需登录）
TOKEN=$(curl -s -X POST "$URL/login" -H "Content-Type: application/json" -d '{"username":"admin","password":"***REMOVED***"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['data']['token'])")
curl -s "$URL/ai/agent/experts" -H "Authorization: Bearer $TOKEN" | grep -q "experts" && echo "✅ AI接口" || echo "❌ AI接口"
```

**任何一项 ❌ 都必须修复后再交付。**

## 固定公网地址

```
https://***REMOVED***
```

- 30 天内不变
- 关机期间打不开，开机跑完 start.sh 后恢复
- 脚本会自动复用旧隧道，地址保持不变

## 验证启动成功

```bash
curl -s -o /dev/null -w "%{http_code}" https://***REMOVED***/
# 返回 200 就是成功
```

## 演示账号

- **演示模式开启时**（`sys.demo.mode=true`），登录页提供**一键登录**（`POST /quickLogin`，免密）：
  - `user1` = 演示用户1、`user2` = 演示用户2、`guest` = 游客
- **管理员**：`admin` / 密码 `***REMOVED***`（走普通登录 `/login`，不在一键登录白名单里）
- 账号密码登录（`/login`）：`admin`、`user1`、`user2`、`guest` 密码均为 `***REMOVED***`
- ⚠️ **演示模式关闭时**（线上体验版）`/quickLogin` 会**直接拒绝**，且登录页不显示一键登录入口；
  由后台「演示模式」开关（`sys_config.sys.demo.mode`）控制。
- 数据库中若无用户，daily-start.sh 会自动导入种子数据（`01_deploy` 建 admin，`97_demo_seed` 建 user1/user2/guest）

## SQL 备份与恢复

### 备份机制（自动）

- **启动时备份**：daily-start.sh 每次启动自动 `pg_dump` 到 `/root/workspace/sql-backup/latest.sql`
- **定时备份**：后台循环每6小时备份一次，保留最近7份
- **持久化**：备份文件在 `/root/workspace/` 下，重启不丢

### 手动备份

```bash
bash /root/workspace/openstudy-fastapi-ts/backup-sql.sh
```

### 恢复

```bash
bash /root/workspace/openstudy-fastapi-ts/restore-sql.sh              # 用最新备份
bash /root/workspace/openstudy-fastapi-ts/restore-sql.sh /path/to.sql # 指定文件
```

### 意外关机恢复流程

1. 开机后运行 `bash /root/start.sh`
2. 脚本自动检测：若 sys_user 表为空 → 自动导入种子数据
3. 若需恢复到某个时间点的数据：`bash restore-sql.sh /root/workspace/sql-backup/openstudy_XXXXXXXX.sql`

## 历史踩坑记录（防止重复踩坑）

### 1. Nginx 代理配置导致白屏 + 登录页 captchaEnabled undefined

**现象**：
- 浏览器打开页面纯白，什么都不显示
- 登录页报错 `TypeError: Cannot read properties of undefined (reading 'captchaEnabled')`

**根因**：
- 前端 axios 的 `baseURL` 为空字符串，API 调用走根路径（如 `/captchaImage`、`/login`），**不带 `/api/` 前缀**
- 后端 auth 路由也是挂载在根路径（`app.include_router(auth.router)`，无 prefix）
- 最初 Nginx 只代理 `/api/` 到后端，根路径请求被 `try_files` 回退到 index.html
- 导致 API 请求收到 HTML 而非 JSON，`res.data` 为 undefined → 前端崩溃

**修复**：
- Nginx 配置改为 `try_files $uri $uri/ @backend`：先找静态文件，找不到才转后端
- 后端 catch_all.py 对浏览器导航请求（Accept: text/html）返回真正的 index.html（用 FileResponse）
- **不要**用 `location / { proxy_pass }` 全转后端——隧道 WAF 会拦截后端返回的 HTML，导致白屏

**正确的 Nginx 配置**（已写入 daily-start.sh）：

核心思路：用 `map` 指令检测请求的 `Accept` 头，浏览器导航（`Accept: text/html`）返回 index.html（SPA），API 调用（无 `text/html`）转发后端。

```nginx
# /etc/nginx/conf.d/00-map.conf (http 上下文)
map $http_accept $is_browser_nav {
    default 0;
    ~*text/html 1;
}

# /etc/nginx/conf.d/openstudy.conf
server {
    listen 3167;
    server_name _;
    root /var/www/openstudy-dist;
    index index.html;

    # 静态文件直接返回
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot|map|gz)$ {
        try_files $uri =404;
    }

    # index.html 直接返回
    location = /index.html {
        try_files $uri =404;
    }

    # 其他请求：浏览器导航返回 index.html (SPA)，API 调用转发后端
    location / {
        if ($is_browser_nav) {
            rewrite ^ /index.html last;
        }
        proxy_pass http://127.0.0.1:9101;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        client_max_body_size 20m;
    }
}
```

### 2. 环境重启后系统软件丢失

**现象**：关机再开机后，PostgreSQL、Redis、Nginx 配置全部消失，但 `/root/workspace/` 下的代码和数据保留。

**原因**：华为云开发环境重启时系统包不持久，只有 workspace 目录持久。

**修复**：daily-start.sh 已改为自动检测并安装缺失的 PostgreSQL、Redis、pgvector，每次开机自动恢复。

### 3. PostgreSQL 数据持久化

**现象**：重启后数据库数据丢失。

**修复**：PG 数据目录从 `/var/lib/pgsql/data`（临时）移到 `/root/workspace/pgsql-data`（持久）。需要 `chmod 755 /root` + `chmod 700` 数据目录。

### 4. pgvector 编译（ARM64 openEuler）

**现象**：`pg_config` 找不到，包冲突。

**修复**：安装 `postgresql-server-devel`，force install `libpq-devel`，用显式路径编译。clang bitcode 失败可忽略，手动拷贝 `vector.so` 和 control 文件即可。

### 5. DevBridge 隧道复用

**注意**：隧道 relay domain 是 `*.devbridge-s2.hwtunnel.com`（不是文档写的 `*.myhuaweicloud.com`）。始终用 `db_tunnel_url <id>` 获取真实地址，不要手动拼接。

### 6. 后端进程启动

**注意**：`nohup ... &` + `disown` 方式启动 uvicorn 可能不生效。直接用 `command & disown $!` 更可靠。shell timeout 会杀掉子进程，不要在 timeout 里启动后端。

### 7. SQL 种子数据未导入导致演示账号不存在

**现象**：登录提示"演示账号不存在，请先执行 seed_demo_users.py 初始化演示数据"

**根因**：
- 后端 SQLAlchemy `create_all` 只建表结构，不导入数据
- daily-start.sh 只建库建表，没有导入 `deploy/db-init/` 下的 SQL 种子数据
- 数据库 `openstudy_v2_pgsql` 存在、表存在，但 sys_user 表为空

**修复**：
- daily-start.sh 已加入 SQL 导入逻辑：检测 sys_user 为空时自动按顺序导入所有 SQL 文件
- 导入后同步序列（setval），防止后续插入失败
- SQL 文件导入顺序：01_deploy → 05_password → 06_config → 97_demo → 98_social → 99_note → 07_carousel → 08_fix_ai_model_options → 09_add_role_pref_model

### 8. SQL 备份机制（防止意外关机丢数据）

**方案**：
- `/root/workspace/sql-backup/` — 持久目录，存放 pg_dump 备份
- `backup-sql.sh` — 手动备份脚本
- `restore-sql.sh` — 恢复脚本（带确认提示）
- `sql-backup-loop.sh` — 后台循环，每6小时自动备份
- daily-start.sh 每次启动时自动备份一份 latest.sql
- 保留最近7份备份，自动清理旧备份
### 9. DevBridge 隧道防钓鱼保护页面（安全警告）

**现象**：浏览器打开隧道地址，显示"安全警告"页面，提示"你即将连接到以下位置的开发者隧道"，需要点击"继续"按钮才能访问。

**根因**：
- DevBridge 隧道有平台级防钓鱼保护（HWWAF）
- 所有带 `Accept: text/html` 的请求（即浏览器导航）首次访问都会被拦截
- 拦截页面设置 cookie `bridge_phishing_protection=1`（365天有效），点击"继续"后放行

**这不是 bug，是安全功能**。用户只需第一次访问时点一次"继续"，之后 365 天内不再出现。

**注意**：
- API 调用（`Accept: application/json` 或 `*/*`）不受影响，直接放行
- curl 默认不带 `Accept: text/html`，所以 curl 测试不会看到防钓鱼页面
- 如果用户反映"打不开"，让他们点"继续"按钮即可

### 10. SPA 路由刷新返回 404/空白

**现象**：在 `/front/messages/notifications` 等 SPA 路由页面按 F5 刷新，页面空白或 404。

**根因**：
- Nginx 把 SPA 路由（如 `/front/messages/notifications`）转发到后端
- 后端没有这个路由，返回 404 JSON
- 浏览器收到 JSON 而非 HTML，无法渲染 SPA

**修复**：
- Nginx 用 `map` 指令检测 `Accept: text/html`（浏览器导航）
- 浏览器导航 → 返回 index.html（SPA 接管路由）
- API 调用（无 text/html）→ 转发后端
- 详见上方 Nginx 配置

### 11. VITE_APP_BASE_API = '/' 导致 ERR_NAME_NOT_RESOLVED（轮播图 + AI 接口全挂）

**现象**：
- 轮播图无法加载，`carousel-1.jpg:1 Failed to load resource: net::ERR_NAME_NOT_RESOLVED`
- AI 智能体聊天报错，`ai/agent/stream:1 Failed to load resource: net::ERR_NAME_NOT_RESOLVED`
- `ai/agent/configs`、`ai/agent/experts` 同样报错
- `assets/profile-xxx.jpg` 也报错

**根因**：
- `.env.docker` 中 `VITE_APP_BASE_API = '/'`（斜杠）
- 前端 axios 的 `baseURL = '/'`，拼接 URL 时：`baseURL + '/ai/agent/stream'` = `'/' + '/ai/agent/stream'` = `'//ai/agent/stream'`
- 浏览器看到 `//ai/agent/stream`，解释为**协议相对 URL**，尝试解析主机名 `ai` → DNS 解析失败 → `ERR_NAME_NOT_RESOLVED`
- 同理 `//carousel-static/carousel-1.jpg` → 解析主机名 `carousel-static` → 失败

**修复**：
- `.env.docker` 中改为 `VITE_APP_BASE_API = ''`（空字符串）
- 拼接结果变成 `'' + '/ai/agent/stream'` = `'/ai/agent/stream'`（单斜杠相对路径，正确）
- 改完后必须**重新构建前端**（`npx vite build --mode docker`），因为 Vite 把 env 变量编译进 JS 产物
- daily-start.sh 已有自动检测修复逻辑（第 125 行）

**检查方法**：
```bash
# 检查构建产物中是否有双斜杠 URL
grep '//ai/agent' /var/www/openstudy-dist/assets/*.js && echo "❌ 有双斜杠bug" || echo "✅ 正常"
```

### 12. 轮播图静态资源未包含在前端构建产物中

**现象**：轮播图 `carousel-1~5.jpg` 返回 404。

**根因**：
- 轮播图图片在后端目录 `openstudy-fastapi/app/static/carousel/`
- 前端引用路径是 `/carousel-static/carousel-1.jpg`
- 但前端 `public/carousel-static/` 目录不存在，Vite 构建时不会包含这些图片
- 构建产物 `dist/` 中没有 `carousel-static/` 目录 → Nginx 返回 404

**修复**：
- 将轮播图复制到前端 `public/carousel-static/`（Vite 构建时自动包含 `public/` 内容）
- 同时复制到 `/var/www/openstudy-dist/carousel-static/`（立即生效）
- daily-start.sh 已新增复制步骤（第 237 行附近）
