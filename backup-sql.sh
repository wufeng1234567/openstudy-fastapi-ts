#!/bin/bash
# SQL 自动备份脚本
# 用法: bash backup-sql.sh
# 备份存到 /root/workspace/sql-backup/ (持久目录，重启不丢)

BACKUP_DIR="/root/workspace/sql-backup"
DB_NAME="openstudy_v2_pgsql"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# 检查 PG 是否运行
if ! pg_isready >/dev/null 2>&1; then
    echo "❌ PostgreSQL 未运行，跳过备份"
    exit 1
fi

# 生成备份
BACKUP_FILE="$BACKUP_DIR/openstudy_${TIMESTAMP}.sql"
pg_dump -U postgres -d "$DB_NAME" --format=plain --no-owner --no-privileges > "$BACKUP_FILE" 2>/dev/null

if [ $? -eq 0 ]; then
    # 同时更新 latest.sql
    cp "$BACKUP_FILE" "$BACKUP_DIR/latest.sql"
    
    # 只保留最近 7 份备份
    ls -t "$BACKUP_DIR"/openstudy_*.sql 2>/dev/null | tail -n +8 | xargs rm -f 2>/dev/null
    
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "✅ 备份成功: $BACKUP_FILE ($SIZE)"
    echo "   latest.sql 已更新"
    
    # 列出所有备份
    echo ""
    echo "现有备份:"
    ls -lh "$BACKUP_DIR"/*.sql 2>/dev/null | awk '{print "  " $NF " (" $5 ")"}'
else
    echo "❌ 备份失败"
    exit 1
fi
