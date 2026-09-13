@echo off
chcp 65001 >nul
cd /d "D:\Hermes Agent CN Desktop\stock-workflow"
echo Aurora 集合竞价分析 · %date% %time%
.venv\Scripts\python.exe daily_run.py --phase auction
echo [完成] %date% %time%
