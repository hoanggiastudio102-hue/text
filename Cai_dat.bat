@echo off
title Cai dat AutoContentGemini (chay 1 lan)
cd /d "%~dp0"

echo ===================================================
echo  CAI DAT LAN DAU: uv + Python 3.12 + thu vien
echo ===================================================

echo.
echo [1/3] Kiem tra uv...
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul
if errorlevel 1 (
    echo Chua co uv - dang tai tu https://astral.sh/uv ...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
)
where uv >nul 2>nul
if errorlevel 1 (
    echo [LOI] Khong cai duoc uv. Kiem tra mang roi chay lai file nay.
    pause
    exit /b 1
)

echo.
echo [2/3] Tao moi truong ao .venv voi Python 3.12...
if not exist ".venv\Scripts\python.exe" (
    uv venv --python 3.12 .venv
)
if not exist ".venv\Scripts\python.exe" (
    echo [LOI] Khong tao duoc moi truong ao .venv.
    pause
    exit /b 1
)

echo.
echo [3/3] Cai thu vien tu requirements.txt...
uv pip install --python ".venv\Scripts\python.exe" -r requirements.txt
if errorlevel 1 (
    echo [LOI] Cai thu vien that bai. Xem thong bao phia tren.
    pause
    exit /b 1
)

echo.
echo ===================================================
echo  CAI DAT XONG - dang chay Khoi_dong.bat ...
echo ===================================================
call "%~dp0Khoi_dong.bat"
