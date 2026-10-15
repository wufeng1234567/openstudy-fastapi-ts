#!/usr/bin/env bash
# OpenStudy 停止服务（Linux / macOS）
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if docker compose version >/dev/null 2>&1; then
    DC="docker compose"
else
    DC="docker-compose"
fi

$DC down
echo "[完成] 服务已停止（数据卷保留）。彻底删除数据：$DC down -v"
