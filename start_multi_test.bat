@echo off
chcp 65001 >nul
cd /d "D:\Hermes Agent CN Desktop\stock-workflow"
echo ════════════════════════════════════════
echo   Aurora 6AI交易员 · 全自动模拟开盘
echo   时间: %date% %time%
echo ════════════════════════════════════════
echo.

:: 1. 清除旧数据 → 6账户各100万重新开始
echo [1/3] 清除旧数据 ...
call .venv\Scripts\python.exe -c "from multi_agent.coordinator import MultiAgentCoordinator;c=MultiAgentCoordinator();n=c.clear_all_data();print('已清除',n,'个文件')"
echo.

:: 2. 运行晨盘(每个Agent独立运行)
echo [2/3] 运行6个AI交易员 ...
call .venv\Scripts\python.exe -c "from multi_agent.coordinator import MultiAgentCoordinator;c=MultiAgentCoordinator();r=c.run_all_morning();c.push_aggregate_report();print('晨盘完成')"
echo.

:: 3. 显示初始状态
echo [3/3] 当前状态:
call .venv\Scripts\python.exe -c "from multi_agent.coordinator import MultiAgentCoordinator;c=MultiAgentCoordinator();import json;r=c.get_aggregate_report();print(r['summary'])"
echo.
echo ════════════════════════════════════════
echo   6个AI交易员已启动运行
echo   查看微信 → 接收推送报告
echo   全自动无人值守
echo ════════════════════════════════════════
echo [完成] 全自动无人值守模式
