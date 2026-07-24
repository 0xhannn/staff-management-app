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

set "OPENED=0"
:loop
if exist .restart del /f /q .restart >nul 2>&1
if "%OPENED%"=="0" (
  start "" http://127.0.0.1:8080
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
