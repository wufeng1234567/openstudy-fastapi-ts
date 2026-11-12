@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "ROOT=%~dp0.."
set "FAIL=0"

echo ============================================================
echo OpenStudy quality verification
echo ============================================================

pushd "%ROOT%\openstudy-fastapi"
if not exist ".venv\Scripts\python.exe" (
  echo [FAIL] backend venv not found: openstudy-fastapi\.venv
  set "FAIL=1"
) else (
  echo [1/6] backend compileall
  ".venv\Scripts\python.exe" -m compileall -q app
  if errorlevel 1 set "FAIL=1"

  echo [2/6] backend ruff syntax gate
  ".venv\Scripts\python.exe" -m ruff check app --select E9,F63,F7,F82
  if errorlevel 1 set "FAIL=1"

  echo [3/6] backend pytest
  ".venv\Scripts\python.exe" -m pytest tests -q
  if errorlevel 1 set "FAIL=1"
)
popd

pushd "%ROOT%\openstudy-vue3-ts"
if not exist "node_modules" (
  echo [FAIL] frontend node_modules not found
  set "FAIL=1"
) else (
  echo [4/6] frontend lint
  call npm run lint
  if errorlevel 1 set "FAIL=1"

  echo [5/6] frontend build
  call npm run build:prod
  if errorlevel 1 set "FAIL=1"

  echo [6/6] frontend type-check ^(report-only; known historical debt^)
  call npm run type-check > "..\_tc_verify.log" 2>&1
  set "TC_EXIT=!ERRORLEVEL!"
  for /f %%C in ('findstr /C:"error TS" "..\_tc_verify.log" ^| find /c /v ""') do set "TC_COUNT=%%C"
  echo [INFO] type-check exit !TC_EXIT!; error TS lines: !TC_COUNT! ^(not treated as a green gate yet^)
)
popd

echo ------------------------------------------------------------
echo Repository hygiene
git status --porcelain
git ls-files | findstr /I /R "_evidence/ _ui_evidence/ codearts-flow.drawio" >nul
if not errorlevel 1 (
  echo [FAIL] generated evidence files are still tracked by git
  set "FAIL=1"
)

if "%FAIL%"=="0" (
  echo [PASS] OpenStudy quality verification finished with no blocking failures.
  exit /b 0
)
echo [FAIL] OpenStudy quality verification has blocking failures.
exit /b 1
