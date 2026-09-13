@echo off
cd /d "D:\Hermes Agent CN Desktop\stock-workflow"
echo ========================================
echo   Aurora 6AI交易员 · 多Agent模拟系统
echo   每个AI独立画像+独立账户+全自动交易
echo ========================================
echo.
if "%1"=="--clear" goto clear
if "%1"=="--intraday" goto intraday
if "%1"=="--status" goto status

:full
echo [模式] 清除旧数据 + 启动所有Agent
call .venv\Scripts\python.exe -c "from multi_agent.coordinator import run_multi_pipeline;run_multi_pipeline()"
echo.
echo 6个AI交易员已启动,查看微信推送报告
echo 运行 --intraday 进行盘中增量扫描
pause
goto end

:clear
echo [模式] 仅清除旧数据
call .venv\Scripts\python.exe -c "from multi_agent.coordinator import MultiAgentCoordinator;c=MultiAgentCoordinator();c.clear_all_data();print('已清除')"
pause
goto end

:intraday
echo [模式] 盘中增量扫描
call .venv\Scripts\python.exe -c "from multi_agent.coordinator import MultiAgentCoordinator;c=MultiAgentCoordinator();c.run_all_intraday();c.push_aggregate_report();print('增量扫描完成')"
pause
goto end

:status
echo [模式] 查看所有Agent状态
call .venv\Scripts\python.exe -c "from multi_agent.coordinator import MultiAgentCoordinator;c=MultiAgentCoordinator();import json;print(json.dumps(c.get_aggregate_report(),ensure_ascii=False,indent=2))"
pause
goto end

:end
