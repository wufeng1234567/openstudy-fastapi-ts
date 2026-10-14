#!/usr/bin/env bash
# ============================================================
# OpenStudy 一键启动（Linux / macOS）
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "  OpenStudy 一键启动 (Docker)"
echo "=========================================="
echo

# ---------- 1. 检查 Docker ----------
if ! command -v docker >/dev/null 2>&1; then
    echo "[错误] 未检测到 Docker。"
    echo "  自动安装（Linux）：curl -fsSL https://get.docker.com | sh"
    echo "  或参考：https://docs.docker.com/engine/install/"
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    echo "[错误] Docker 已安装但未运行或当前用户无权限。"
    echo "  尝试：sudo systemctl start docker"
    echo "  免 sudo：sudo usermod -aG docker \$USER  后重新登录"
    exit 1
fi

# 兼容 docker compose v2 与旧版 docker-compose
if docker compose version >/dev/null 2>&1; then
    DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DC="docker-compose"
else
    echo "[错误] 未找到 docker compose 插件。"
    exit 1
fi

# ---------- 2. 准备 .env ----------
if [ ! -f .env ] && [ -f .env.example ]; then
    echo "[提示] 未找到 .env，正在从 .env.example 生成..."
    cp .env.example .env
    echo "[提示] 已生成 .env。如需填写 AI Key，请编辑 .env 后重新运行。"
fi

# ---------- 3. 拉起服务 ----------
echo "[执行] 正在构建并启动容器（首次较慢，请耐心等待）..."
$DC up -d --build

echo
echo "=========================================="
echo "  启动完成！"
echo "=========================================="
echo "  前端主页 : http://localhost:3167"
echo "  后端文档 : http://localhost:9101/swagger-ui.html"
echo "  演示账号 : admin / admin123"
echo
echo "  查看日志 : $DC logs -f"
echo "  停止服务 : ./stop.sh"
echo "=========================================="
