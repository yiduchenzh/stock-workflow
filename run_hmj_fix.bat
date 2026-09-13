@echo off
cd /d D:\Hermes Agent CN Desktop\stock-workflow
".venv\Scripts\python.exe" -c "p=r'tests\test_hmj_backtest.py'; s=open(p,encoding='utf-8-sig').read(); open(p,'w',encoding='utf-8',newline='\n').write(s); print('BOM removed')"
".venv\Scripts\python.exe" tests\test_hmj_backtest.py
