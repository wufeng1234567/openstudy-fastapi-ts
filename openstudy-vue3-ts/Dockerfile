# ============================================================
# OpenStudy Vue3-TS 前端镜像（多阶段构建）
# ------------------------------------------------------------
# 阶段 1：Node 构建静态产物（dist/）
# 阶段 2：Nginx 托管 dist/，并把 API 前缀反代到后端容器
#
# 构建上下文为 openstudy-vue3-ts/ 目录。
# 使用 --mode docker 读取 .env.docker（VITE_APP_BASE_API=/ 相对路径）。
# ============================================================

# ---------- 阶段 1：构建 ----------
FROM node:20-slim AS build

WORKDIR /app

# 先拷贝依赖清单，利用层缓存
COPY package.json package-lock.json ./
# npm ci 需要 lockfile 与 package.json 一致；若不一致退回 npm install
RUN npm ci || npm install

# 拷贝其余源码
COPY . .

# 用 docker 模式构建（相对路径 API 基址）
# 注意：项目构建脚本名是 build:prod（对应 vite build）
RUN npm run build:prod -- --mode docker

# ---------- 阶段 2：运行 ----------
FROM nginx:1.27-alpine

# 自定义站点配置：SPA history 回退 + API 反代
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 静态产物
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD wget -qO- http://localhost/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
