@echo off
setlocal enabledelayedexpansion
set SCRIPT_DIR=%~dp0
set BACKEND_PORT=9101

call :hdr
echo.

call :y "[Stage 1/2] Starting FastAPI backend..."
start "OpenStudy FastAPI" cmd /k "%SCRIPT_DIR%start-fastapi.bat"

call :y "[Stage 2/2] Starting Vue3 frontend..."
start "OpenStudy Vue3" cmd /k "%SCRIPT_DIR%start-vue.bat"

echo.
call :hdr2
echo.
powershell -Command "Write-Host '  Backend API:   http://localhost:%BACKEND_PORT%'"
powershell -Command "Write-Host '  Backend Docs:  http://localhost:%BACKEND_PORT%/docs'"
powershell -Command "Write-Host '  Frontend:      http://localhost:3167'"
echo.
powershell -Command "Write-Host '  Each service runs in its own window'"
powershell -Command "Write-Host '  Close window to stop service'"
echo.
pause
goto :eof

:hdr
powershell -Command "Write-Host '==========================================' -ForegroundColor Cyan"
powershell -Command "Write-Host '  OpenStudy Launcher (FastAPI + Vue3-TS)' -ForegroundColor Cyan"
powershell -Command "Write-Host '==========================================' -ForegroundColor Cyan"
goto :eof

:hdr2
powershell -Command "Write-Host '==========================================' -ForegroundColor Cyan"
powershell -Command "Write-Host '  All services started!' -ForegroundColor Green"
powershell -Command "Write-Host '==========================================' -ForegroundColor Cyan"
goto :eof

:r
powershell -Command "Write-Host '%~1' -ForegroundColor Red"
goto :eof

:g
powershell -Command "Write-Host '%~1' -ForegroundColor Green"
goto :eof

:y
powershell -Command "Write-Host '%~1' -ForegroundColor Yellow"
goto :eof

:cy
powershell -Command "Write-Host '%~1' -ForegroundColor Cyan"
goto :eof
