#!/bin/bash
# SQL 恢复脚本
# 用法: bash restore-sql.sh [备份文件路径]
# 不带参数则用 latest.sql

BACKUP_DIR="/root/workspace/sql-backup"
DB_NAME="openstudy_v2_pgsql"

if [ -n "$1" ]; then
    BACKUP_FILE="$1"
else
    BACKUP_FILE="$BACKUP_DIR/latest.sql"
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ 备份文件不存在: $BACKUP_FILE"
    echo ""
    echo "可用备份:"
    ls -lh "$BACKUP_DIR"/*.sql 2>/dev/null | awk '{print "  " $NF " (" $5 ")"}'
    exit 1
fi

echo "⚠️  即将从备份恢复数据库: $BACKUP_FILE"
echo "   这会覆盖现有数据！"
echo ""
read -p "确认恢复? (输入 yes 继续): " confirm
if [ "$confirm" != "yes" ]; then
    echo "已取消"
    exit 0
fi

# 先备份当前数据
echo "备份当前数据..."
pg_dump -U postgres -d "$DB_NAME" --format=plain --no-owner --no-privileges > "$BACKUP_DIR/pre_restore_$(date +%Y%m%d_%H%M%S).sql" 2>/dev/null

# 恢复
echo "恢复中..."
psql -U postgres -d "$DB_NAME" -f "$BACKUP_FILE" 2>&1 | tail -5

# 同步序列
psql -U postgres -d "$DB_NAME" -t -c "
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

echo "✅ 恢复完成"
echo ""
echo "用户列表:"
psql -U postgres -d "$DB_NAME" -t -c "SELECT user_name FROM sys_user ORDER BY user_name;" 2>&1
