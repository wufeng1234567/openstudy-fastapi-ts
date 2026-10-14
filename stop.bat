@echo off
setlocal
chcp 65001 >nul
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo ==========================================
echo   OpenStudy 停止服务
echo ==========================================
docker compose down
echo.
echo [完成] 服务已停止（数据卷保留，下次启动数据仍在）。
echo   如需彻底删除数据：docker compose down -v
echo.
pause
