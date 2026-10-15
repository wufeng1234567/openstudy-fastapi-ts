#!/bin/bash
# SQL 定时备份后台服务
# 每6小时备份一次，用 setsid 启动不会被 shell 关闭
# 用法: setsid bash sql-backup-loop.sh &

BACKUP_SCRIPT="/root/workspace/openstudy-fastapi-ts/backup-sql.sh"
LOG_FILE="/root/workspace/sql-backup/loop.log"

echo "$(date): 备份循环启动 (每6小时)" >> "$LOG_FILE"

while true; do
    bash "$BACKUP_SCRIPT" >> "$LOG_FILE" 2>&1
    sleep 21600  # 6小时 = 21600秒
done
