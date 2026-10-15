@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo ==========================================
echo   OpenStudy 一键启动 (Docker)
echo ==========================================
echo.

rem ---------- 1. 检查 Docker ----------
where docker >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Docker。
    echo.
    echo   请先安装 Docker Desktop：
    echo     https://www.docker.com/products/docker-desktop/
    echo   安装后启动 Docker Desktop，等托盘图标变绿，再运行本脚本。
    echo.
    pause
    exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
    echo [错误] Docker 已安装但未运行。
    echo   请先打开 Docker Desktop，等待其完全启动后再试。
    echo.
    pause
    exit /b 1
)

rem ---------- 2. 准备 .env ----------
if not exist ".env" (
    if exist ".env.example" (
        echo [提示] 未找到 .env，正在从 .env.example 生成...
        copy ".env.example" ".env" >nul
        echo [提示] 已生成 .env。如需填写 AI Key，请编辑 .env 后重新运行。
        echo.
    )
)

rem ---------- 3. 拉起服务 ----------
echo [执行] 正在构建并启动容器（首次较慢，请耐心等待）...
echo.
docker compose up -d --build
if errorlevel 1 (
    echo.
    echo [错误] 启动失败，请查看上方日志。
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   启动完成！
echo ==========================================
echo   前端主页 : http://localhost:3167
echo   后端文档 : http://localhost:9101/swagger-ui.html
echo   演示账号 : admin / admin123
echo.
echo   查看日志 : docker compose logs -f
echo   停止服务 : 运行 stop.bat 或 docker compose down
echo ==========================================
echo.
echo   首次启动后端建表需要约 20-40 秒，若页面暂时打不开请稍候刷新。
echo.
pause
