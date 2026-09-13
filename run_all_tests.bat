@echo off
cd /d D:\Hermes Agent CN Desktop\stock-workflow
".venv\Scripts\python.exe" -m pytest tests -q --tb=line
