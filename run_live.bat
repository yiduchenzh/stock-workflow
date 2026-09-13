@echo off
cd /d "D:\Hermes Agent CN Desktop\stock-workflow"
echo ========================================
echo   Aurora 半自动实盘 v1.0
echo   引擎生成计划 -> 推送微信 -> 手动执行
echo ========================================
echo.
if "%1"=="--monitor" goto monitor
if "%1"=="--review" goto review
echo [晨盘] 市场扫描 + 交易计划
call .venv\Scripts\python.exe run_live.py
echo.
echo 请查看微信消息 -> 在涨乐财富通操作
pause
goto end

:monitor
echo [监控] 盘中监控 (Ctrl+C停止)
.venv\Scripts\python.exe -c "from core.engine_live import start_live_engine;start_live_engine(60)"
goto end

:review
echo [复盘] 盘后总结
call .venv\Scripts\python.exe -c "from run_live import phase_morning;phase_morning()"
pause
:end