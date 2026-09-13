@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [Aurora Trading] 启动中...
.venv\Scripts\python daily_run.py %*
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 运行失败，错误码=%ERRORLEVEL%
    pause
)