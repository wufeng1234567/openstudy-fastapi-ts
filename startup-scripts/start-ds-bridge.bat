@echo off
setlocal enabledelayedexpansion
set SCRIPT_DIR=%~dp0
set BRIDGE_DIR=%SCRIPT_DIR%ds-bridge
set PORT=9200

call :hdr
echo.

rem ---- Node.js check ----
where node >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] Node.js not found in PATH.
    echo         Install Node.js 18+ ^(20/22 recommended^): https://nodejs.org
    pause
    exit /b 1
)
for /f "delims=" %%v in ('node -v') do set NODE_VER=%%v
echo [OK] Node.js %NODE_VER%

rem ---- Dependencies check (playwright-core) ----
if not exist "%BRIDGE_DIR%\node_modules\playwright-core" (
    echo [INFO] Installing ds-bridge dependencies ^(playwright-core^)...
    pushd "%BRIDGE_DIR%"
    call npm install --no-audit --no-fund
    popd
)
echo [OK] ds-bridge dependencies ready
echo.

rem ---- Port cleanup ----
echo [INFO] Checking port %PORT% ...
netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >nul 2>&1
if !errorlevel! equ 0 (
    echo [WARN] Port %PORT% occupied, killing...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
        taskkill /f /pid %%a >nul 2>&1
    )
    echo [INFO] Waiting for port %PORT% to be released...
    set /a tries=0
    :waitport
    set /a tries+=1
    netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >nul 2>&1
    if !errorlevel! equ 0 (
        if !tries! lss 10 (
            ping -n 2 127.0.0.1 >nul
            goto waitport
        )
        echo [ERROR] Port %PORT% still occupied. Kill it manually:
        netstat -ano | findstr ":%PORT% " | findstr "LISTENING"
        pause
        exit /b 1
    )
    echo [OK] Port released
) else (
    echo [OK] Port %PORT% is free
)

echo.
echo [INFO] Starting DS web bridge on port %PORT% ...
echo         Bridge: http://localhost:%PORT%   ^(model ds-free-nb^)
echo         Uses system Edge/Chrome ^(headless^), no browser extension required.
echo         First run: if not logged in, run:  node probe.js --login   in ds-bridge\
echo         Press Ctrl+C to stop
echo ------------------------------------------
echo.

cd /d "%BRIDGE_DIR%"
node server.js
set EXIT_CODE=%errorlevel%

if not "%EXIT_CODE%"=="0" (
    if not "%EXIT_CODE%"=="3221225786" (
        echo.
        echo [ERROR] DS bridge exited with code %EXIT_CODE%
        pause
    )
)
exit /b %EXIT_CODE%

:hdr
powershell -Command "Write-Host '==========================================' -ForegroundColor Cyan; Write-Host '  OpenStudy DS Web Bridge (ds-free-nb)' -ForegroundColor Cyan; Write-Host '==========================================' -ForegroundColor Cyan"
goto :eof
