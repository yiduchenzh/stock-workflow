@echo off
chcp 65001 >nul
cd /d "D:\Hermes Agent CN Desktop\stock-workflow"
echo ════════════════════════════════════════
echo   Aurora 收盘复盘 · 交易总结+策略自进化
echo   时间: %date% %time%
echo ════════════════════════════════════════
echo.
.venv\Scripts\python.exe daily_run.py --phase review
echo.
echo [完成] %date% %time%
