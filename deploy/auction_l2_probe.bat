@echo off
rem Auction L2 field-semantics probe (pure ASCII - cmd parses .bat as ANSI/GBK)
set "PY=D:\Hermes Agent CN Desktop\stock-workflow\.venv\Scripts\python.exe"
set "SCRIPT=C:\Users\User871619\AppData\Roaming\cn.org.hermesagent.desktop\runtime\hermes-home\skills\trading\a-share-auction-analysis\scripts\auction_l2_probe.py"
set "OUT=D:\Hermes Agent CN Desktop\stock-workflow\data\auction_l2_probe.jsonl"

if not exist "%PY%" exit /b 1
if not exist "%SCRIPT%" exit /b 2

"%PY%" "%SCRIPT%" --codes "300319,600519,000063,002594,300750" --until "09:25:30" --interval 20 --out "%OUT%"
exit /b %ERRORLEVEL%
