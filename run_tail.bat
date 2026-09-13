@echo off
chcp 65001 >nul
cd /d "D:\Hermes Agent CN Desktop\stock-workflow"
echo ════════════════════════════════════════
echo   Aurora 尾盘开仓 · 收盘前精选+过夜策略
echo   时间: %date% %time%
echo ════════════════════════════════════════
echo.
.venv\Scripts\python.exe daily_run.py --phase monitor
echo.
echo [完成] %date% %time%
