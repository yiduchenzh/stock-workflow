@echo off
REM ============================================================
REM  Aurora daily close  (2026-09-24 weekly-review P0-1 fix)
REM  1) main-sim engine.step_close(): refresh close prices + budgets
REM  2) 6 agent profiles close_day(): valuation + day baseline
REM  NOTE: this file must stay PURE ASCII.
REM        cmd.exe reads .bat as GBK/ANSI - UTF-8 Chinese makes it
REM        split into garbage commands and the task exits non-zero.
REM ============================================================
cd /d "D:\Hermes Agent CN Desktop\stock-workflow"
if not exist logs mkdir logs
echo ==== %date% %time% ==== >> logs\close_report.log
".venv\Scripts\python.exe" daily_run.py --phase close >> logs\close_report.log 2>&1
echo exit=%errorlevel% >> logs\close_report.log
