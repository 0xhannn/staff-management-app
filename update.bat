@echo off
cd /d "%~dp0"
echo === Staff Management update ===
echo Keeps: .env   data\
echo.

if exist .venv\Scripts\activate.bat (
  call .venv\Scripts\activate.bat
) else (
  echo WARN: .venv not found — run install.bat if pip fails.
)

git remote set-url origin https://github.com/0xhannn/staff-management-app.git
echo Fetching GitHub...
git fetch origin --tags --prune
if errorlevel 1 (
  echo FAIL: git fetch. Cek internet / Git.
  pause
  exit /b 1
)

echo Syncing main...
git checkout -B main origin/main
if errorlevel 1 git reset --hard origin/main
if errorlevel 1 (
  echo FAIL: git sync.
  pause
  exit /b 1
)

echo Installing deps...
python -m pip install -r requirements.txt
if errorlevel 1 pip install -r requirements.txt

REM Ensure PORT=8081 (Workflow Planner uses 8080)
if not exist .env copy .env.example .env
findstr /B /C:"PORT=" .env >nul 2>&1
if errorlevel 1 (
  echo PORT=8081>>.env
) else (
  powershell -NoProfile -Command "(Get-Content .env) -replace '^PORT=.*','PORT=8081' | Set-Content .env"
)
echo PORT forced to 8081 in .env

echo.
echo ==============================
echo  UPDATE OK
git describe --tags --always 2>nul
echo  Next: stop app, then start.bat
echo  Open http://127.0.0.1:8081  (Ctrl+F5)
echo ==============================
pause
