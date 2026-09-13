@echo off
chcp 65001 >nul
cd /d "D:\Hermes Agent CN Desktop\stock-workflow"
echo === Aurora 实时流守护进程 ===

:: 检查是否已在运行
tasklist /FI "WINDOWTITLE eq aurora_daemon*" 2>nul | findstr /C:"python" >nul
if %ERRORLEVEL% EQU 0 (
    echo [WARN] 守护进程已在运行!
    pause
    exit /b 1
)

:: 后台启动守护Python脚本
echo [1/2] 启动实时流引擎...
start "aurora_daemon" /B /MIN .venv\Scripts\python.exe scripts\daemon_launcher.py

:: 等待启动确认
timeout /t 3 /nobreak >nul

tasklist /FI "WINDOWTITLE eq aurora_daemon*" 2>nul | findstr /C:"python" >nul
if %ERRORLEVEL% EQU 0 (
    echo [2/2] 守护进程运行中
) else (
    echo [2/2] 后台进程启动中, 查看日志: type logs\daemon.log
)
echo === 守护进程已启动 ===
echo 查看状态: tasklist /FI "WINDOWTITLE eq aurora_daemon*"
echo 查看日志: type logs\daemon.log
echo 停止:     stop_daemon.bat
