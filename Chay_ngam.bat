@echo off
cd /d "%~dp0"
rem Chay AutoContentGemini ngam: khong mo trinh duyet, khong git pull, log vao logs\server.log
netstat -ano | findstr ":5002 " | findstr LISTENING >nul && exit /b 0
set AUTOGEMINI_DEBUG=0
set PYTHONUTF8=1
if not exist logs mkdir logs
call .venv\Scripts\activate
python app.py >> logs\server.log 2>&1
