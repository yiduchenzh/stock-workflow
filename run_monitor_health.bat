@echo off
chcp 65001 >NUL
cd /d "D:\Hermes Agent CN Desktop\stock-workflow"
".venv\Scripts\python.exe" scripts\monitor_health.py
