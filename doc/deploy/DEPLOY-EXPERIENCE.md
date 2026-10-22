# OpenStudy 部署经验总结

> 本文档记录部署过程中遇到的所有 bug 及其根因、修复方案，供 LLM 部署前查阅避免重复踩坑。
> AGENTS.md 中的「部署前必做检查」是精简版，本文档是详细版。

---

## 一、部署前检查清单（LLM 必读）

部署前逐项检查，任何一项不通过都必须先修复：

| # | 检查项 | 检查命令 | 期望结果 | 不通过的后果 |
|---|--------|---------|---------|-------------|
| 1 | `VITE_APP_BASE_API` 是空字符串 | `grep "VITE_APP_BASE_API" .env.docker` | `VITE_APP_BASE_API = ''` | 所有 API 调用 + 轮播图 + profile 图片全挂 (ERR_NAME_NOT_RESOLVED) |
| 2 | 轮播图在 public 目录 | `ls public/carousel-static/carousel-*.jpg` | 5 个 jpg 文件 | 轮播图 404 |
| 3 | Nginx 用 map 区分导航/API | `grep "is_browser_nav" /etc/nginx/conf.d/*.conf` | 有匹配 | SPA 路由刷新空白 |
| 4 | PG 数据目录在持久路径 | `grep "PG_DATA" daily-start.sh` | `/root/workspace/pgsql-data` | 重启丢数据库 |
| 5 | 00-map.conf 存在 | `ls /etc/nginx/conf.d/00-map.conf` | 文件存在 | Nginx 启动失败 |

---

## 二、部署后验证清单（LLM 必做）

部署完成后逐项验证，任何一项 ❌ 都必须修复后再交付：

```bash
URL="${DEMO_URL}"
COOKIE="bridge_phishing_protection=1"

# 1. 首页能加载
curl -s -H "Accept: text/html" -H "Cookie: $COOKIE" "$URL/" | grep -q "openstudy" && echo "✅ 首页" || echo "❌ 首页"

# 2. SPA 路由刷新不空白（核心验证）
curl -s -H "Accept: text/html" -H "Cookie: $COOKIE" "$URL/front/messages/notifications" | grep -q "openstudy" && echo "✅ SPA路由" || echo "❌ SPA路由"

# 3. 构建产物无双斜杠 URL
grep -q '//ai/agent' /var/www/openstudy-dist/assets/*.js && echo "❌ 双斜杠bug" || echo "✅ API URL正常"

# 4. 轮播图能加载
curl -s -o /dev/null -w "%{http_code}" "$URL/carousel-static/carousel-1.jpg" | grep -q "200" && echo "✅ 轮播图" || echo "❌ 轮播图"

# 5. 静态资源能加载
JS=$(curl -s -H "Cookie: $COOKIE" "$URL/" | grep -oP 'src="\K[^"]*\.js' | head -1)
curl -s -o /dev/null -w "%{http_code}" "$URL$JS" | grep -q "200" && echo "✅ 静态资源" || echo "❌ 静态资源"

# 6. 登录能成功
LOGIN=$(curl -s -X POST "$URL/login" -H "Content-Type: application/json" -d '{"username":"demo","password":"${DEMO_PASSWORD}"}')
echo "$LOGIN" | grep -q "操作成功" && echo "✅ 登录" || echo "❌ 登录"

# 7. AI 接口能访问（需先登录）
TOKEN=$(echo "$LOGIN" | python3 -c "import json,sys; print(json.load(sys.stdin)['data']['token'])")
curl -s "$URL/ai/agent/experts" -H "Authorization: Bearer $TOKEN" | grep -q "experts" && echo "✅ AI接口" || echo "❌ AI接口"

# 8. profile 图片能加载
PROFILE=$(ls /var/www/openstudy-dist/assets/profile-*.jpg 2>/dev/null | head -1 | xargs basename)
curl -s -o /dev/null -w "%{http_code}" "$URL/assets/$PROFILE" | grep -q "200" && echo "✅ profile图片" || echo "❌ profile图片"
```

---

## 三、Bug 详细记录

### Bug 1: VITE_APP_BASE_API = '/' 导致 ERR_NAME_NOT_RESOLVED

**严重程度**: 🔴 致命 — 轮播图、AI 接口、profile 图片全部无法加载

**现象**:
```
carousel-1.jpg:1  Failed to load resource: net::ERR_NAME_NOT_RESOLVED
ai/agent/stream:1  Failed to load resource: net::ERR_NAME_NOT_RESOLVED
ai/agent/configs?includeDisabled=false:1  Failed to load resource: net::ERR_NAME_NOT_RESOLVED
ai/agent/experts:1  Failed to load resource: net::ERR_NAME_NOT_RESOLVED
assets/profile-DruvkrZU.jpg:1  Failed to load resource: net::ERR_NAME_NOT_RESOLVED
```

**根因**:
- `.env.docker` 中 `VITE_APP_BASE_API = '/'`
- 前端 axios `baseURL = '/'`
- URL 拼接: `baseURL + '/ai/agent/stream'` = `'/' + '/ai/agent/stream'` = `'//ai/agent/stream'`
- 浏览器将 `//ai/agent/stream` 解释为**协议相对 URL** (protocol-relative URL)
- 浏览器尝试解析主机名 `ai` → DNS 失败 → `ERR_NAME_NOT_RESOLVED`
- 同理: `//carousel-static/carousel-1.jpg` → 解析主机名 `carousel-static` → 失败

**修复**:
```bash
# 修复 .env.docker
sed -i "s|VITE_APP_BASE_API = '/'|VITE_APP_BASE_API = ''|" .env.docker

# 重新构建前端（Vite 把 env 编译进 JS，必须重建）
npx vite build --mode docker

# 部署
rm -rf /var/www/openstudy-dist/*
cp -r dist/* /var/www/openstudy-dist/
```

**验证**:
```bash
# 构建产物中不应有双斜杠 URL
grep '//ai/agent' /var/www/openstudy-dist/assets/*.js  # 应无输出
grep '/ai/agent' /var/www/openstudy-dist/assets/*.js   # 应有输出（单斜杠）
```

**预防**: daily-start.sh 第 125 行已有自动检测修复逻辑。

---

### Bug 2: 轮播图静态资源未包含在前端构建产物中

**严重程度**: 🟡 功能缺失 — 首页轮播图区域空白

**现象**: `carousel-1~5.jpg` 返回 HTTP 404

**根因**:
- 轮播图源文件在后端目录: `openstudy-fastapi/app/static/carousel/carousel-{1-5}.jpg`
- 前端引用路径: `/carousel-static/carousel-{1-5}.jpg`
- 前端 `public/carousel-static/` 目录不存在
- Vite 构建只包含 `public/` 目录下的文件，所以 `dist/` 中没有 `carousel-static/`
- Nginx 在 `/var/www/openstudy-dist/` 找不到文件 → 404

**修复**:
```bash
# 复制到前端 public 目录（以后构建自动包含）
mkdir -p public/carousel-static
cp ../openstudy-fastapi/app/static/carousel/carousel-*.jpg public/carousel-static/

# 复制到当前部署目录（立即生效）
mkdir -p /var/www/openstudy-dist/carousel-static
cp public/carousel-static/*.jpg /var/www/openstudy-dist/carousel-static/
```

**预防**: daily-start.sh 已新增复制步骤。

---

### Bug 3: SPA 路由刷新返回 404/空白

**严重程度**: 🔴 致命 — 用户刷新任何非首页 URL 都看到空白

**现象**: 在 `/front/messages/notifications`、`/dashboard`、`/login` 等页面按 F5 刷新，页面空白

**根因**:
- Nginx 配置 `try_files $uri $uri/ @backend`
- SPA 路由 (如 `/front/messages/notifications`) 没有对应静态文件
- Nginx 转发到后端 (FastAPI)
- 后端没有这个路由 → 返回 404 JSON
- 浏览器收到 JSON 而非 HTML → 无法渲染 SPA

**修复**: Nginx 用 `map` 指令检测 `Accept` 头区分请求类型:
- `Accept: text/html` (浏览器导航) → 返回 index.html (SPA 接管路由)
- 其他 (API 调用) → 转发后端

```nginx
# /etc/nginx/conf.d/00-map.conf
map $http_accept $is_browser_nav {
    default 0;
    ~*text/html 1;
}

# /etc/nginx/conf.d/openstudy.conf
server {
    listen 3167;
    root /var/www/openstudy-dist;
    index index.html;

    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot|map|gz)$ {
        try_files $uri =404;
    }

    location = /index.html {
        try_files $uri =404;
    }

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

---

### Bug 4: DevBridge 隧道防钓鱼保护页面

**严重程度**: 🟢 正常安全功能 — 首次访问需点一次"继续"

**现象**: 浏览器打开隧道地址，显示"安全警告"页面

**根因**: DevBridge 隧道平台级防钓鱼保护 (HWWAF)，所有 `Accept: text/html` 请求首次访问被拦截

**修复**: 无需修复，用户点"继续"按钮后设置 cookie `bridge_phishing_protection=1` (365天有效)

---

### Bug 5: Nginx 代理配置导致白屏 + captchaEnabled undefined

**严重程度**: 🔴 致命

**现象**: 页面纯白，`TypeError: Cannot read properties of undefined (reading 'captchaEnabled')`

**根因**: Nginx 只代理 `/api/` 前缀，但前端 API 调用走根路径 (`/captchaImage`、`/login`)，不带 `/api/` 前缀

**修复**: Nginx 用 `try_files` + `map` 区分静态文件、浏览器导航、API 调用

---

### Bug 6: 环境重启后系统软件丢失

**严重程度**: 🟡 需手动恢复

**现象**: 关机再开机后 PostgreSQL、Redis、Nginx 配置消失

**根因**: 华为云开发环境重启时系统包不持久，只有 `/root/workspace/` 持久

**修复**: daily-start.sh 自动检测并安装缺失的 PostgreSQL、Redis、pgvector

---

### Bug 7: PostgreSQL 数据持久化

**严重程度**: 🔴 数据丢失

**修复**: PG 数据目录从 `/var/lib/pgsql/data` (临时) 移到 `/root/workspace/pgsql-data` (持久)

---

### Bug 8: SQL 种子数据未导入

**严重程度**: 🟡 无法登录

**现象**: 登录提示"演示账号不存在"

**修复**: daily-start.sh 检测 sys_user 为空时自动导入 SQL 种子数据

---

## 四、关键配置项速查

| 配置项 | 正确值 | 错误值 | 影响 |
|--------|--------|--------|------|
| `VITE_APP_BASE_API` | `''` (空字符串) | `'/'` | 全部 API + 静态资源挂 |
| Nginx `map $http_accept` | 有 | 无 | SPA 路由刷新空白 |
| `public/carousel-static/` | 存在 | 不存在 | 轮播图 404 |
| PG 数据目录 | `/root/workspace/pgsql-data` | `/var/lib/pgsql/data` | 重启丢数据 |
| 隧道域名 | `*.devbridge-s2.hwtunnel.com` | `*.myhuaweicloud.com` | URL 错误 |

---

## 五、部署流程（LLM 执行步骤）

```
1. 读本文件 + AGENTS.md
2. 执行部署前检查清单（第三节）
3. 执行 bash /root/start.sh
4. 等待启动完成
5. 执行部署后验证清单（第二节）
6. 如有 ❌，按 Bug 详细记录修复
7. 全部 ✅ 后交付
```
