# -*- coding: utf-8 -*-
"""滑点校准保守化: 1跳 → 可配的 slippage_ticks(默认2 = 1跳价差 + 1跳逆向选择)"""
import io
import os
import py_compile
import shutil
from datetime import datetime

ROOT = r"D:\Hermes Agent CN Desktop\stock-workflow"
p = os.path.join(ROOT, "executor", "sim_account.py")
raw = io.open(p, encoding="utf-8", newline="").read()
nl = "\r\n" if "\r\n" in raw else "\n"
src = raw.replace("\r\n", "\n")

OLD = '''        tick = 0.01 / price
        turn = float((self._stock_micro_cache.get(code) or {}).get("avg_daily_turnover") or 5e8)
        part_pct = (shares * price) / turn * 100.0        # 参与度 %
        impact = 0.1 * (part_pct ** 0.5) / 100.0          # 平方根冲击律(1% 参与度 → 0.1%)
        slip = max(tick, min(0.001, impact))'''
NEW = '''        # ⚠️ 保守化: 单取 1 跳会偏乐观(真实还含逆向选择) → 默认 2 跳(1跳价差 + 1跳逆向选择)
        #   实测参照: 1跳 中位 0.047%/边; 旧口径 0.272%/边 ⇒ 2跳(≈0.094%)仍比旧口径保守 ~2.9 倍
        try:
            _ticks = int(c.get("slippage_ticks")
                         if c.get("slippage_ticks") is not None
                         else (c.get("execution") or {}).get("slippage_ticks", 2))
        except Exception:
            _ticks = 2
        _ticks = max(1, _ticks)
        tick = 0.01 / price * _ticks
        turn = float((self._stock_micro_cache.get(code) or {}).get("avg_daily_turnover") or 5e8)
        part_pct = (shares * price) / turn * 100.0        # 参与度 %
        impact = 0.1 * (part_pct ** 0.5) / 100.0          # 平方根冲击律(1% 参与度 → 0.1%)
        slip = max(tick, min(0.001, impact))'''

if NEW in src:
    print("[SKIP] 已应用")
else:
    assert src.count(OLD) == 1, "锚点 count=%d" % src.count(OLD)
    bk = os.path.join(ROOT, "_restore", "fix6_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(bk, exist_ok=True)
    shutil.copy2(p, os.path.join(bk, "sim_account.py"))
    src = src.replace(OLD, NEW, 1)
    out = src.replace("\n", nl) if nl == "\r\n" else src
    tmp = p + ".chk.py"
    io.open(tmp, "w", encoding="utf-8", newline="").write(out)
    py_compile.compile(tmp, doraise=True)
    os.remove(tmp)
    io.open(p, "w", encoding="utf-8", newline="").write(out)
    print("[OK] 滑点改为可配 ticks(默认2) (备份 %s)" % bk)

# config: 加 slippage_ticks
def add_knob(path):
    s = io.open(path, encoding="utf-8", newline="").read()
    n2 = "\r\n" if "\r\n" in s else "\n"
    t = s.replace("\r\n", "\n")
    if "slippage_ticks" in t:
        print("  [SKIP] %s" % path); return
    a = "  slippage_mode: tick"
    if a not in t:
        print("  [WARN] %s 无 slippage_mode 锚点" % path); return
    t = t.replace(a, a + "\n  # 校准跳数: 1跳=价差, +1跳=逆向选择(保守) → 默认 2\n  slippage_ticks: 2", 1)
    io.open(path, "w", encoding="utf-8", newline="").write(t.replace("\n", n2) if n2 == "\r\n" else t)
    print("  [OK] %s 加 slippage_ticks: 2" % path)

add_knob(os.path.join(ROOT, "config.yaml"))
add_knob(os.path.join(ROOT, "config.example.yaml"))
