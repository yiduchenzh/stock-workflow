@echo off
chcp 65001 >nul
cd /d "D:\Hermes Agent CN Desktop\stock-workflow"
echo === Aurora 晨盘自动启动 ===
echo [%date% %time%]

:: 检查是否是交易日(引擎内部判断)
echo [1/2] 启动晨盘引擎...
call .venv\Scripts\python.exe daily_run.py --phase morning
if %ERRORLEVEL% NEQ 0 (
    echo [WARN] 晨盘引擎异常,退出码:%ERRORLEVEL%
)

echo [2/2] 晨盘完成
echo === 晨盘结束 ===
