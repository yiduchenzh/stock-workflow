# -*- coding: utf-8 -*-
"""补: 卖出成交记录也带 slip_mode(可观测性/审计对称)"""
import io
import os
import py_compile
import shutil
from datetime import datetime

ROOT = r"D:\Hermes Agent CN Desktop\stock-workflow"
p = os.path.join(ROOT, "executor", "sim_account.py")
_BK = os.path.join(ROOT, "_restore", "fix4_20261001_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
os.makedirs(_BK, exist_ok=True)
shutil.copy2(p, os.path.join(_BK, "sim_account.py"))
raw = io.open(p, encoding="utf-8", newline="").read()
nl = "\r\n" if "\r\n" in raw else "\n"
src = raw.replace("\r\n", "\n")

OLD = '''        trade = {
            "action": "sell", "code": code, "shares": shares,
            "price": round(fill_price, 2),
            "slippage_pct": round(slippage*100, 4),
            "base_slip_pct": round(ms.get("base_slippage", 0)*100, 4),'''
NEW = '''        trade = {
            "action": "sell", "code": code, "shares": shares,
            "price": round(fill_price, 2),
            "slippage_pct": round(slippage*100, 4),
            "slip_mode": ms.get("slip_mode", "?"),        # 2026-10-01: 与买入对称留痕
            "base_slip_pct": round(ms.get("base_slippage", 0)*100, 4),'''
if '"slip_mode"' in src and src.count('"slip_mode"') >= 2:
    print("[SKIP] 已有")
else:
    assert src.count(OLD) == 1, "锚点 count=%d" % src.count(OLD)
    src = src.replace(OLD, NEW, 1)
    out = src.replace("\n", nl) if nl == "\r\n" else src
    tmp = p + ".chk.py"
    io.open(tmp, "w", encoding="utf-8", newline="").write(out)
    py_compile.compile(tmp, doraise=True)
    os.remove(tmp)
    io.open(p, "w", encoding="utf-8", newline="").write(out)
    print("[OK] 卖出记录已加 slip_mode | 文件中 slip_mode 出现 %d 次" % out.count('"slip_mode"'))
