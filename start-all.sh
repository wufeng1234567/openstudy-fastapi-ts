#!/bin/bash
# ============================================================
# OpenStudy 一键启动脚本 (Linux)
# 启动: PostgreSQL + Redis → FastAPI 后端 → Vue3 前端
# ============================================================

set -e

PROJECT_ROOT="/root/workspace/openstudy-fastapi-ts"
BACKEND_DIR="$PROJECT_ROOT/openstudy-fastapi"
FRONTEND_DIR="$PROJECT_ROOT/openstudy-vue3-ts"
BACKEND_PORT=9101
FRONTEND_PORT=3167

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}==========================================${NC}"
echo -e "${CYAN}  OpenStudy Launcher (FastAPI + Vue3-TS)${NC}"
echo -e "${CYAN}==========================================${NC}"
echo ""

# ---------- 1. 启动 PostgreSQL ----------
echo -e "${YELLOW}[Stage 1/4] Starting PostgreSQL...${NC}"

# 检查是否已运行
if su - postgres -c "pg_ctl -D /var/lib/pgsql/data status" 2>/dev/null | grep -q "running"; then
    echo -e "  PostgreSQL already running."
else
    su - postgres -c "pg_ctl -D /var/lib/pgsql/data -l /var/lib/pgsql/data/logfile start" 2>&1
    sleep 2
    echo -e "  PostgreSQL started."
fi

# ---------- 2. 启动 Redis ----------
echo -e "${YELLOW}[Stage 2/4] Starting Redis...${NC}"

if redis-cli ping 2>/dev/null | grep -q "PONG"; then
    echo -e "  Redis already running."
else
    redis-server --daemonize yes --port 6379 2>&1
    sleep 1
    echo -e "  Redis started."
fi

# ---------- 3. 启动后端 ----------
echo -e "${YELLOW}[Stage 3/4] Starting FastAPI backend (port $BACKEND_PORT)...${NC}"

# 检查端口是否被占用
if lsof -i :$BACKEND_PORT 2>/dev/null | grep -q LISTEN; then
    echo -e "  Backend port $BACKEND_PORT already in use, skipping."
else
    cd "$BACKEND_DIR"
    source .venv/bin/activate
    nohup uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT --reload > /tmp/openstudy-backend.log 2>&1 &
    BACKEND_PID=$!
    echo "  Backend PID: $BACKEND_PID"
    echo "  Waiting for backend to start..."
    
    # 等待后端启动（最多30秒）
    for i in $(seq 1 30); do
        if curl -s "http://localhost:$BACKEND_PORT/docs" > /dev/null 2>&1; then
            echo -e "  Backend ready (took ${i}s)."
            break
        fi
        sleep 1
        if [ $i -eq 30 ]; then
            echo -e "  ${RED}Backend failed to start within 30s. Check /tmp/openstudy-backend.log${NC}"
            tail -20 /tmp/openstudy-backend.log
        fi
    done
fi

# ---------- 4. 启动前端 ----------
echo -e "${YELLOW}[Stage 4/4] Starting Vue3 frontend (port $FRONTEND_PORT)...${NC}"

if lsof -i :$FRONTEND_PORT 2>/dev/null | grep -q LISTEN; then
    echo -e "  Frontend port $FRONTEND_PORT already in use, skipping."
else
    cd "$FRONTEND_DIR"
    nohup npm run dev > /tmp/openstudy-frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo "  Frontend PID: $FRONTEND_PID"
    echo "  Waiting for frontend to start..."
    
    for i in $(seq 1 30); do
        if curl -s "http://localhost:$FRONTEND_PORT" > /dev/null 2>&1; then
            echo -e "  Frontend ready (took ${i}s)."
            break
        fi
        sleep 1
        if [ $i -eq 30 ]; then
            echo -e "  ${RED}Frontend failed to start within 30s. Check /tmp/openstudy-frontend.log${NC}"
            tail -20 /tmp/openstudy-frontend.log
        fi
    done
fi

# ---------- 完成 ----------
echo ""
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}  All services started!${NC}"
echo -e "${GREEN}==========================================${NC}"
echo ""
echo -e "  Backend API:   ${CYAN}http://localhost:$BACKEND_PORT${NC}"
echo -e "  Backend Docs:  ${CYAN}http://localhost:$BACKEND_PORT/docs${NC}"
echo -e "  Frontend:      ${CYAN}http://localhost:$FRONTEND_PORT${NC}"
echo ""
echo -e "  Backend log:   /tmp/openstudy-backend.log"
echo -e "  Frontend log:  /tmp/openstudy-frontend.log"
echo ""
echo -e "  To stop: kill the uvicorn and vite processes, or:"
echo -e "          su - postgres -c 'pg_ctl -D /var/lib/pgsql/data stop'"
echo -e "          redis-cli shutdown"
echo ""
