@echo off
title Khoi dong AutoContentGemini
echo ===================================================
echo Kiem tra va cap nhat phien ban moi nhat (Auto-Update)...
echo ===================================================

:: Di chuyen den thu muc chua file .bat
cd /d "%~dp0"

:: 1. Tu dong keo code moi nhat tu Github ve
git pull origin main

:: 2. Kiem tra xem co thu muc .venv chua, neu chua thi tao
if not exist .venv (
    echo Lan dau tien chay - Dang cai dat moi truong...
    uv venv
)

:: 3. Kich hoat moi truong ao
call .venv\Scripts\activate

:: 4. Tu dong cai dat/cap nhat thu vien
uv pip install -r requirements.txt
playwright install

echo.
echo Dang khoi dong AutoContentGemini (AI Dich Thuat va Sang Tao)...
echo Vui long doi trong giay lat...

:: Mo san trinh duyet
start http://localhost:5002

:: Chay ung dung
python app.py
pause
