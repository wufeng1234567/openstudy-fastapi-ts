@echo off
setlocal enabledelayedexpansion
set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..\
set FASTAPI_DIR=%PROJECT_ROOT%openstudy-fastapi
set VENV_PYTHON=%FASTAPI_DIR%\.venv\Scripts\python.exe
set PORT=9101

call :hdr
echo.

if exist "%VENV_PYTHON%" (
    echo [OK] Using venv Python: %VENV_PYTHON%
) else (
    echo [ERROR] .venv not found at: %VENV_PYTHON%
    echo         Create it first with Python 3.11:
    echo           py -3.11 -m venv "%FASTAPI_DIR%\.venv"
    echo           "%FASTAPI_DIR%\.venv\Scripts\pip" install -r "%FASTAPI_DIR%\requirements.txt"
    pause
    exit /b 1
)
echo.

echo [INFO] Checking port %PORT% ...
netstat -ano | findstr ":%PORT% " | findstr "LISTEN" >nul 2>&1
if !errorlevel! equ 0 (
    echo [WARN] Port %PORT% occupied, killing...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTEN"') do (
        taskkill /f /pid %%a >nul 2>&1
    )
    echo [INFO] Waiting for port %PORT% to be released...
    set /a tries=0
    :waitport
    set /a tries+=1
    netstat -ano | findstr ":%PORT% " | findstr "LISTEN" >nul 2>&1
    if !errorlevel! equ 0 (
        if !tries! lss 10 (
            ping -n 2 127.0.0.1 >nul
            goto waitport
        )
        echo [ERROR] Port %PORT% still occupied after kill. Kill it manually:
        netstat -ano | findstr ":%PORT% " | findstr "LISTEN"
        pause
        exit /b 1
    )
    echo [OK] Port released
) else (
    echo [OK] Port %PORT% is free
)

echo.
echo [INFO] Starting FastAPI backend on port %PORT% ...
echo         API:  http://localhost:%PORT%
echo         Docs: http://localhost:%PORT%/docs
echo         Press Ctrl+C to stop
echo ------------------------------------------
echo.

cd /d "%FASTAPI_DIR%"
"%VENV_PYTHON%" -m uvicorn app.main:app --host 0.0.0.0 --port %PORT% --log-level info --reload
set EXIT_CODE=%errorlevel%

if not "%EXIT_CODE%"=="0" (
    if not "%EXIT_CODE%"=="3221225786" (
        echo.
        echo [ERROR] FastAPI exited with code %EXIT_CODE%
        pause
    )
)
exit /b %EXIT_CODE%

:hdr
powershell -Command "Write-Host '==========================================' -ForegroundColor Cyan; Write-Host '  OpenStudy FastAPI Backend' -ForegroundColor Cyan; Write-Host '==========================================' -ForegroundColor Cyan"
goto :eof
