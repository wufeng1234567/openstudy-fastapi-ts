@echo off
setlocal enabledelayedexpansion
set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..\
set VUE_DIR=%PROJECT_ROOT%openstudy-vue3-ts
set PORT=3167

call :hdr
echo.

if not exist "%VUE_DIR%\node_modules" (
    call :y "[WARN] node_modules not found, installing..."
    cd /d "%VUE_DIR%"
    call npm install
    if !errorlevel! neq 0 ( call :r "[ERROR] npm install failed" & pause & exit /b 1 )
    call :g "[OK] Dependencies installed"
)

echo.
powershell -Command "Write-Host '[INFO] Checking port %PORT% ...' -NoNewline"
netstat -ano | findstr ":%PORT% " | findstr "LISTEN" >nul 2>&1
if !errorlevel! equ 0 (
    call :y " Occupied, killing..."
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTEN"') do (
        taskkill /f /pid %%a >nul 2>&1
    )
    call :g "[OK] Port released"
) else (
    call :g " Free"
)

echo.
call :cy "[INFO] Starting Vue3 frontend, port: %PORT% ..."
echo.
call :cy "  Access:"
powershell -Command "Write-Host '    Frontend:  http://localhost:%PORT%'"
powershell -Command "Write-Host '    Backend:   http://localhost:9101'"
echo.
powershell -Command "Write-Host '  Press Ctrl+C to stop'"
echo ------------------------------------------
echo.

cd /d "%VUE_DIR%"
call npm run dev
if errorlevel 1 ( call :r "[ERROR] Vue3 failed" & pause )
goto :eof

:hdr
powershell -Command "Write-Host '==========================================' -ForegroundColor Cyan"
powershell -Command "Write-Host '  OpenStudy Vue3-TS Frontend' -ForegroundColor Cyan"
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
