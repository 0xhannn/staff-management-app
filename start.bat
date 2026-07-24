@echo off
cd /d "%~dp0"
if not exist .venv (
  echo Run install.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
if not exist .env copy .env.example .env
if not exist data mkdir data

REM Force PORT=8081 if missing/old 8080 in .env (Workflow Planner uses 8080)
findstr /B /C:"PORT=" .env >nul 2>&1
if errorlevel 1 (
  echo PORT=8081>>.env
) else (
  powershell -NoProfile -Command "(Get-Content .env) -replace '^PORT=.*','PORT=8081' | Set-Content .env"
)
set PORT=8081

set "OPENED=0"
:loop
if exist .restart del /f /q .restart >nul 2>&1
if "%OPENED%"=="0" (
  echo Starting Staff Management on http://127.0.0.1:%PORT%
  start "" http://127.0.0.1:%PORT%
  set "OPENED=1"
)
python server.py
set "EC=%ERRORLEVEL%"
if exist .restart (
  echo.
  echo === Update applied — restarting app ===
  timeout /t 2 /nobreak >nul
  goto loop
)
if "%EC%"=="0" goto end
echo.
echo App exited with code %EC%.
pause
:end
