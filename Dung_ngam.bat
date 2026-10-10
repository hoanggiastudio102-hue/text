@echo off
rem Dung AutoContentGemini dang chay ngam (cong 5002)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5002 " ^| findstr LISTENING') do taskkill /PID %%p /F /T
echo Da dung. Mo lai bang Chay_ngam.vbs hoac Khoi_dong.bat.
pause
