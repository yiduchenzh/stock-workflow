@echo off
chcp 65001 >nul
echo 停止 Aurora 实时流守护进程...
taskkill /FI "WINDOWTITLE eq aurora_daemon*" /F 2>nul
if %ERRORLEVEL% EQU 0 (
    echo 守护进程已停止
) else (
    echo 没有运行中的守护进程
)
