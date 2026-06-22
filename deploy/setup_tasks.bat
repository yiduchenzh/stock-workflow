@echo off
chcp 65001 >nul
set "PROJ=d:\Hermes Agent CN Desktop\aurora-trading"
set "PY=%PROJ%\.venv\Scripts\python.exe"
echo === Aurora Trading 定时任务注册 ===
schtasks /delete /tn "Aurora_Daily" /f 2>nul
schtasks /delete /tn "Aurora_Monitor" /f 2>nul
schtasks /create /tn "Aurora_Daily" /tr "\"%PY%\" \"%PROJ%\daily_run.py\"" /sc weekly /d MON,TUE,WED,THU,FRI /st 08:30 /ru SYSTEM /f
schtasks /create /tn "Aurora_Monitor" /tr "\"%PY%\" \"%PROJ%\daily_run.py\"" /sc minute /mo 5 /st 09:30 /et 15:00 /d MON,TUE,WED,THU,FRI /ru SYSTEM /f
echo 完成! schtasks /query /tn Aurora_*
pause
