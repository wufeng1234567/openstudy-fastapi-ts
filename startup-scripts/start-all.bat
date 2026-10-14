@echo off
setlocal enabledelayedexpansion
set SCRIPT_DIR=%~dp0
set BACKEND_PORT=9101
set FRONTEND_PORT=3167

call :hdr
echo.

rem ============================================================
rem Idempotent guard: if a port is already LISTENING, treat the
rem service as "already running" and SKIP it (do not restart).
rem Otherwise start-fastapi/start-vue would taskkill the port
rem owner and kill a service currently in use.
rem Port check uses netstat (pure cmd, no quoting hell).
rem ============================================================

call :portinuse %BACKEND_PORT%
if "!INUSE!"=="1" (
    echo [SKIP] FastAPI backend already running on port %BACKEND_PORT%
) else (
    echo [START] FastAPI backend...
    start "OpenStudy FastAPI" cmd /k "%SCRIPT_DIR%start-fastapi.bat"
)

call :portinuse %FRONTEND_PORT%
if "!INUSE!"=="1" (
    echo [SKIP] Vue3 frontend already running on port %FRONTEND_PORT%
) else (
    echo [START] Vue3 frontend...
    start "OpenStudy Vue3" cmd /k "%SCRIPT_DIR%start-vue.bat"
)

echo.
call :hdr2
echo.
powershell -Command "Write-Host '  Backend API:   http://localhost:%BACKEND_PORT%'"
powershell -Command "Write-Host '  Backend Docs:  http://localhost:%BACKEND_PORT%/docs'"
powershell -Command "Write-Host '  Frontend:      http://localhost:%FRONTEND_PORT%'"
echo.
powershell -Command "Write-Host '  Already-running services are skipped (idempotent launcher).'"
echo.
powershell -Command "Write-Host '  Each service runs in its own window; close it to stop that service.'"
echo.
pause
goto :eof

rem ============================================================
rem :portinuse <port>  -> sets INUSE=1 (LISTENING) or 0 (free)
rem ============================================================
:portinuse
set "INUSE=0"
for /f "tokens=*" %%a in ('netstat -ano ^| findstr /R /C:":%1 .*LISTENING"') do set "INUSE=1"
goto :eof

:hdr
powershell -Command "Write-Host '==========================================' -ForegroundColor Cyan"
powershell -Command "Write-Host '  OpenStudy Launcher (FastAPI + Vue3-TS)' -ForegroundColor Cyan"
powershell -Command "Write-Host '==========================================' -ForegroundColor Cyan"
goto :eof

:hdr2
powershell -Command "Write-Host '==========================================' -ForegroundColor Cyan"
powershell -Command "Write-Host '  Launcher done!' -ForegroundColor Green"
powershell -Command "Write-Host '==========================================' -ForegroundColor Cyan"
goto :eof
