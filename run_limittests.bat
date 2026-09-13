@echo off
cd /d D:\Hermes Agent CN Desktop\stock-workflow
".venv\Scripts\python.exe" -m pytest tests\test_limitup_tail_stable.py tests\test_limit_gene_gate.py tests\test_limitup_2w_research.py -q
