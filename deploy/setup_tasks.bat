@echo off
chcp 65001 >nul
set "PROJ=d:\Hermes Agent CN Desktop\stock-workflow"
set "PY=%PROJ%\.venv\Scripts\python.exe"
set "CFG=%PROJ%\config.yaml"

echo === Aurora Trading 自动交易 — 定时任务注册 ===
echo 项目: %PROJ%
echo Python: %PY%

:: 读取.env中的WZ_TOKEN
if exist "%PROJ%\.env" (
    for /f "tokens=2 delims==" %%a in ('findstr "WZ_TOKEN" "%PROJ%\.env"') do set "WZ_TOKEN=%%a"
)

:: 删除旧任务
schtasks /delete /tn "Aurora_Morning" /f 2>nul
schtasks /delete /tn "Aurora_Monitor" /f 2>nul
schtasks /delete /tn "Aurora_Review" /f 2>nul

:: 创建任务 — 每天
:: 09:25 集合竞价选股+晨报
schtasks /create /tn "Aurora_Morning" /tr "\"%PY%\" \"%PROJ%\daily_run.py\" --phase morning" /sc daily /st 09:25 /ru SYSTEM /f

:: 09:35-15:00 每5分钟盘中监控 (交易日)
schtasks /create /tn "Aurora_Monitor" /tr "\"%PY%\" \"%PROJ%\daily_run.py\" --phase monitor" /sc minute /mo 10 /st 09:35 /et 15:00 /d MON,TUE,WED,THU,FRI /ru SYSTEM /f

:: 15:05 收盘复盘+报告生成
schtasks /create /tn "Aurora_Review" /tr "\"%PY%\" \"%PROJ%\daily_run.py\" --phase review" /sc daily /st 15:05 /ru SYSTEM /f

echo.
echo === 任务列表 ===
schtasks /query /tn "Aurora_*" 2>nul
echo.
echo 完成! 按任意键关闭...
pause >nul