@echo off
chcp 65001 >nul
cd /d d:\Aurora
echo [%date% %time%] FastMonitor 5min ...
.venv\Scripts\python.exe fast_monitor.py
