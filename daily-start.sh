#!/bin/bash
# ============================================================
# OpenStudy 每日一键启动（比赛用）- 环境恢复版
# 自动安装缺失依赖 + 启动全部服务 + 30天固定隧道
# 数据库数据存放在 workspace 持久目录，关机不丢
# 用法: bash /root/start.sh
# ============================================================

PROJECT_ROOT="/root/workspace/openstudy-fastapi-ts"
BACKEND_DIR="$PROJECT_ROOT/openstudy-fastapi"
FRONTEND_DIR="$PROJECT_ROOT/openstudy-vue3-ts"
BACKEND_PORT=9101
FRONTEND_PORT=3167
DB_SCRIPT="/root/.agents/skills/huawei-cloud-jobenv-devbridge-tunnel/scripts/devbridge_cmd.sh"
TUNNEL_NAME="openstudy"
TUNNEL_EXPIRATION=720   # 30 天
PG_DATA="/root/workspace/pgsql-data"  # 持久化数据库目录

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}==========================================${NC}"
echo -e "${CYAN}  OpenStudy 每日启动 (比赛部署)${NC}"
echo -e "${CYAN}==========================================${NC}"

# ---------- 0. 环境检查与恢复 ----------
echo -e "${YELLOW}[0/6] 环境检查...${NC}"

# 0a. 权限：让 postgres 用户能访问 workspace
chmod 755 /root /root/workspace 2>/dev/null

# 0b. PostgreSQL
if ! which pg_ctl >/dev/null 2>&1; then
    echo -e "  安装 PostgreSQL..."
    yum install -y postgresql postgresql-server postgresql-contrib >/dev/null 2>&1
fi
if ! id postgres >/dev/null 2>&1; then
    useradd -m postgres 2>/dev/null
fi
# 数据目录放在 workspace 里，关机不丢
if [ ! -f "$PG_DATA/PG_VERSION" ]; then
    echo -e "  初始化 PostgreSQL (数据存 workspace)..."
    mkdir -p "$PG_DATA"
    chown postgres:postgres "$PG_DATA"
    chmod 700 "$PG_DATA"
    su - postgres -c "/usr/bin/initdb -D $PG_DATA --encoding=UTF8" >/dev/null 2>&1
    echo "listen_addresses = 'localhost'" >> "$PG_DATA/postgresql.conf"
    echo "port = 5432" >> "$PG_DATA/postgresql.conf"
fi

# 0c. pgvector 扩展
if [ ! -f /usr/lib64/pgsql/vector.so ]; then
    echo -e "  编译 pgvector..."
    yum install -y postgresql-server-devel >/dev/null 2>&1
    if ! which pg_config >/dev/null 2>&1; then
        yum remove -y postgresql-server-devel >/dev/null 2>&1
        yum install -y libpq-devel >/dev/null 2>&1
        yumdownloader postgresql-server-devel >/dev/null 2>&1
        rpm -ivh --force postgresql-server-devel-*.rpm >/dev/null 2>&1
    fi
    cd /tmp
    if [ ! -d pgvector ]; then
        git clone --depth 1 https://github.com/pgvector/pgvector.git >/dev/null 2>&1
    fi
    cd /tmp/pgvector
    make >/dev/null 2>&1
    cp vector.so /usr/lib64/pgsql/ 2>/dev/null
    cp vector.control /usr/share/pgsql/extension/ 2>/dev/null
    cp sql/vector--*.sql /usr/share/pgsql/extension/ 2>/dev/null
fi

# 0d. Redis
if ! which redis-server >/dev/null 2>&1; then
    echo -e "  安装 Redis..."
    yum install -y redis >/dev/null 2>&1
fi

# 0e. Nginx 配置
echo -e "  配置 Nginx..."
# map 指令必须在 http {} 上下文，放在独立 conf 文件
cat > /etc/nginx/conf.d/00-map.conf << 'MAPEOF'
map $http_accept $is_browser_nav {
    default 0;
    ~*text/html 1;
}
MAPEOF
cat > /etc/nginx/conf.d/openstudy.conf << 'NGINXEOF'
server {
    listen 3167;
    server_name _;
    root /var/www/openstudy-dist;
    index index.html;

    # 静态文件直接返回
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot|map|gz)$ {
        try_files $uri =404;
        add_header Cache-Control "no-cache" always;
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
NGINXEOF

# 0f. .env.docker 修复
if grep -q "VITE_APP_BASE_API = '/'" "$FRONTEND_DIR/.env.docker" 2>/dev/null; then
    sed -i "s|VITE_APP_BASE_API = '/'|VITE_APP_BASE_API = ''|" "$FRONTEND_DIR/.env.docker"
fi

echo -e "  ✅ 环境就绪"

# ---------- 1. PostgreSQL ----------
echo -e "${YELLOW}[1/6] PostgreSQL...${NC}"
# 重启后 pgsql-data 目录权限可能变回 root，postgres 用户读不了 → PG 起不来
chown -R postgres:postgres "$PG_DATA" 2>/dev/null
chmod 700 "$PG_DATA" 2>/dev/null
if su - postgres -c "pg_ctl -D $PG_DATA status" 2>/dev/null | grep -q "running"; then
    echo -e "  ✅ 已在运行"
else
    su - postgres -c "pg_ctl -D $PG_DATA -l $PG_DATA/logfile start" >/dev/null 2>&1
    sleep 3
    echo -e "  ✅ 已启动"
fi
# 确保数据库和用户存在
su - postgres -c "psql -c \"SELECT 1 FROM pg_roles WHERE rolname='root'\"" 2>/dev/null | grep -q "1" || \
    su - postgres -c "psql -c \"CREATE USER root WITH PASSWORD '123456' SUPERUSER;\"" >/dev/null 2>&1
su - postgres -c "psql -c \"SELECT 1 FROM pg_database WHERE datname='openstudy_v2_pgsql'\"" 2>/dev/null | grep -q "1" || \
    su - postgres -c "psql -c \"CREATE DATABASE openstudy_v2_pgsql OWNER root;\"" >/dev/null 2>&1
# 确保扩展存在
su - postgres -c "psql -d openstudy_v2_pgsql -c \"CREATE EXTENSION IF NOT EXISTS vector;\"" >/dev/null 2>&1
su - postgres -c "psql -d openstudy_v2_pgsql -c \"CREATE EXTENSION IF NOT EXISTS pg_trgm;\"" >/dev/null 2>&1

# 导入 SQL 种子数据（仅在 sys_user 为空时执行，避免重复导入）
USER_COUNT=$(psql -U postgres -d openstudy_v2_pgsql -t -c "SELECT count(*) FROM sys_user;" 2>/dev/null | tr -d ' ')
if [ -z "$USER_COUNT" ] || [ "$USER_COUNT" -eq 0 ]; then
    echo -e "  ${YELLOW}导入 SQL 种子数据...${NC}"
    SQL_DIR="/root/workspace/openstudy-fastapi-ts/deploy/db-init"
    for sqlf in 01_openstudy_v2_pgsql_deploy.sql 05_change_password.sql 06_ensure_config.sql 97_demo_seed.sql 98_social_seed.sql 99_note_public_seed.sql 07_fix_carousel.sql; do
        if [ -f "$SQL_DIR/$sqlf" ]; then
            psql -U postgres -d openstudy_v2_pgsql -f "$SQL_DIR/$sqlf" >/dev/null 2>&1
            echo "    ✅ $sqlf"
        fi
    done
    # 同步序列（防止插入失败）
    psql -U postgres -d openstudy_v2_pgsql -t -c "
    DO \$\$
    DECLARE r record;
    BEGIN
      FOR r IN SELECT s.relname AS seq, t.relname AS tbl, a.attname AS col
               FROM pg_class s JOIN pg_depend d ON d.objid=s.oid
               JOIN pg_class t ON d.refobjid=t.oid
               JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=d.refobjsubid
               WHERE s.relkind='S'
      LOOP
        EXECUTE 'SELECT setval('||quote_literal(r.seq)||', COALESCE((SELECT MAX('||r.col||') FROM '||r.tbl||'),1))';
      END LOOP;
    END\$\$;
    " >/dev/null 2>&1
    echo -e "  ✅ 种子数据导入完成"
else
    echo -e "  ✅ 数据已有 ${USER_COUNT} 个用户，跳过基础导入"
    # 99_note_public_seed.sql 是幂等的，每次都跑，确保笔记分享页有数据
    SQL_DIR="/root/workspace/openstudy-fastapi-ts/deploy/db-init"
    if [ -f "$SQL_DIR/99_note_public_seed.sql" ]; then
        psql -U postgres -d openstudy_v2_pgsql -f "$SQL_DIR/99_note_public_seed.sql" >/dev/null 2>&1
        echo -e "  ✅ 笔记分享数据已确保"
    fi
fi

# SQL 自动备份（每次启动时导出一份到持久目录）
BACKUP_DIR="/root/workspace/sql-backup"
mkdir -p "$BACKUP_DIR"
pg_dump -U postgres -d openstudy_v2_pgsql --format=plain --no-owner --no-privileges > "$BACKUP_DIR/latest.sql" 2>/dev/null
echo -e "  ✅ SQL 备份 → $BACKUP_DIR/latest.sql"

# 启动定时备份循环（每6小时备份一次）
if ! pgrep -f "sql-backup-loop" >/dev/null 2>&1; then
    setsid bash /root/workspace/openstudy-fastapi-ts/sql-backup-loop.sh & disown $!
fi

# ---------- 2. Redis ----------
echo -e "${YELLOW}[2/6] Redis...${NC}"
if redis-cli ping 2>/dev/null | grep -q "PONG"; then
    echo -e "  ✅ 已在运行"
else
    redis-server --daemonize yes --port 6379 >/dev/null 2>&1
    sleep 1
    echo -e "  ✅ 已启动"
fi

# ---------- 3. 后端 ----------
echo -e "${YELLOW}[3/6] FastAPI 后端 (port $BACKEND_PORT)...${NC}"
if curl -s -o /dev/null http://localhost:$BACKEND_PORT/health 2>/dev/null; then
    echo -e "  ✅ 已在运行"
else
    cd "$BACKEND_DIR"
    cat > /tmp/start-backend.sh << 'BKEOF'
#!/bin/bash
cd /root/workspace/openstudy-fastapi-ts/openstudy-fastapi
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 9101
BKEOF
    chmod +x /tmp/start-backend.sh
    nohup /tmp/start-backend.sh > /tmp/openstudy-backend.log 2>&1 &
    disown
    echo "  等待启动..."
    for i in $(seq 1 30); do
        sleep 1
        if curl -s -o /dev/null http://localhost:$BACKEND_PORT/health 2>/dev/null; then
            echo -e "  ✅ 后端就绪 (${i}s)"
            break
        fi
        [ $i -eq 30 ] && echo -e "  ${RED}❌ 30s 未就绪，查 /tmp/openstudy-backend.log${NC}"
    done
fi

# ---------- 4. Nginx 静态前端 ----------
echo -e "${YELLOW}[4/6] Nginx 静态前端 (port $FRONTEND_PORT)...${NC}"
if [ ! -f "$FRONTEND_DIR/dist/index.html" ]; then
    echo "  dist 不存在，重新构建..."
    cd "$FRONTEND_DIR"
    npx vite build --mode docker 2>&1 | tail -3
fi
mkdir -p /var/www
rm -rf /var/www/openstudy-dist
cp -r "$FRONTEND_DIR/dist" /var/www/openstudy-dist
chmod -R 755 /var/www/openstudy-dist
# 复制轮播图静态资源
if [ -d "$FRONTEND_DIR/public/carousel-static" ]; then
    cp -r "$FRONTEND_DIR/public/carousel-static" /var/www/openstudy-dist/
    echo -e "  ✅ 轮播图已复制"
fi
nginx -s reload 2>/dev/null || nginx 2>/dev/null
sleep 2
if curl -s -o /dev/null http://localhost:$FRONTEND_PORT 2>/dev/null; then
    echo -e "  ✅ Nginx 就绪"
else
    echo -e "  ${RED}❌ Nginx 未就绪${NC}"
fi

# ---------- 5. DevBridge 隧道（30天固定地址） ----------
echo -e "${YELLOW}[5/6] DevBridge 隧道 (30天固定)...${NC}"
source "$DB_SCRIPT"
db_init > /dev/null 2>&1

TUNNEL_ID=""
TUNNEL_URL=""

# 查找名为 openstudy 的旧隧道
EXISTING_ID=$(db_list 2>/dev/null | python3 -c "
import json, sys
try:
    for t in json.load(sys.stdin):
        if t.get('name') == 'openstudy':
            print(t['tunnelId']); break
except: pass
" 2>/dev/null)

if [ -n "$EXISTING_ID" ]; then
    echo -e "  发现旧隧道: $EXISTING_ID，复用..."
    db_processes 2>/dev/null | python3 -c "
import json, sys
try:
    for p in json.load(sys.stdin):
        if p.get('tunnelId') == '$EXISTING_ID' and p.get('type') == 'host':
            print(p['id'])
except: pass
" 2>/dev/null | while read pid; do db_process_stop "$pid" > /dev/null 2>&1; done
    sleep 1
    db_host "$EXISTING_ID" > /dev/null 2>&1
    sleep 3
    TUNNEL_URL=$(db_tunnel_url "$EXISTING_ID" 2>/dev/null)
    if [ -n "$TUNNEL_URL" ]; then
        TUNNEL_ID="$EXISTING_ID"
        echo -e "  ✅ 复用成功！地址不变"
    else
        echo -e "  ${YELLOW}旧隧道无法复用，新建...${NC}"
        db_delete "$EXISTING_ID" > /dev/null 2>&1
    fi
fi

if [ -z "$TUNNEL_ID" ]; then
    echo -e "  创建新隧道 (30天过期)..."
    TUNNEL_ID=$(db_create "$TUNNEL_NAME" "OpenStudy固定隧道" $TUNNEL_EXPIRATION 2>/dev/null)
    if [ -z "$TUNNEL_ID" ]; then
        TUNNEL_ID=$(db_create "${TUNNEL_NAME}-$RANDOM" "OpenStudy重试" $TUNNEL_EXPIRATION 2>/dev/null)
    fi
    if [ -n "$TUNNEL_ID" ]; then
        db_port_create "$TUNNEL_ID" $FRONTEND_PORT auto true 2>/dev/null
        db_host "$TUNNEL_ID" > /dev/null 2>&1
        sleep 3
        TUNNEL_URL=$(db_tunnel_url "$TUNNEL_ID" 2>/dev/null)
        echo -e "  ✅ 新隧道: $TUNNEL_ID"
    else
        echo -e "  ${RED}❌ 隧道创建失败${NC}"
    fi
fi

# ---------- 6. 验证 ----------
echo -e "${YELLOW}[6/6] 验证...${NC}"
sleep 2
FE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$TUNNEL_URL/" 2>/dev/null)
API_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$TUNNEL_URL/api/auth/captcha" 2>/dev/null)
echo -e "  前端: $FE_STATUS | API: $API_STATUS"
[ "$FE_STATUS" = "200" ] && echo -e "  ✅ 服务正常" || echo -e "  ${RED}❌ 异常${NC}"

# ---------- 完成 ----------
echo ""
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}  全部就绪！${NC}"
echo -e "${GREEN}==========================================${NC}"
echo ""
echo -e "  📌 评委访问地址: ${CYAN}${TUNNEL_URL}${NC}"
echo -e "  隧道ID:   $TUNNEL_ID (30天有效)"
echo ""
echo -e "  ${YELLOW}地址30天内不变，关机再开机地址相同${NC}"
echo -e "  ${YELLOW}用完记得点上方关机按钮省额度${NC}"
echo ""
