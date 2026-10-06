# -*- coding: utf-8 -*-
"""阶段2 修复①: 画像差异化复位(P0-1) + 趋势跟踪者激活(P0-2)

确定性行替换(按技能铁律: 本仓 CRLF+中文, patch 模糊匹配会吞相邻行 → 用 read/assert/replace/compile/read-back)
"""
import io
import py_compile
import re

P = r"D:\Hermes Agent CN Desktop\stock-workflow\profiling\trader_types.py"
src = io.open(P, encoding="utf-8").read()
lines = src.split("\n")

orig = list(lines)
edits = []


def edit_lineno(lineno, old_sub, new_sub, tag):
    """按行号替换行内子串(1-based), 断言命中"""
    global lines
    i = lineno - 1
    cur = lines[i]
    assert old_sub in cur, f"[{tag}] 第{lineno}行未命中!\n  期望含: {old_sub}\n  实际:   {cur}"
    lines[i] = cur.replace(old_sub, new_sub, 1)
    edits.append((tag, lineno, cur.strip()[:90], lines[i].strip()[:90]))


# ── P0-1/②: 价值投资者 — B型降权(1.0 = 低于单信号确认门槛2.0), 保留 A 型挖坑低吸(2.0) ──
# strategy_weights(第66行) + signal_prefer(第142行)
edit_lineno(66, '"prev_close_A": 2.0, "prev_close_B": 2.0}', '"prev_close_A": 3.0, "prev_close_B": 1.0}',
            "价值.strategy_weights B型降权")
edit_lineno(142, '"prev_close_A": 2.0, "prev_close_B": 2.0}', '"prev_close_A": 3.0, "prev_close_B": 1.0}',
            "价值.signal_prefer B型降权")

# ── P0-2/②: 趋势跟踪者激活 — 主战法=缠论一买/均线突破/波点(趋势类) + A型回调, 不给B型(追涨与画像不符) ──
# strategy_weights(第38行) + signal_prefer(第114行)
edit_lineno(38,
            '"strategy_weights": {"momentum_breakout": 2.0, "wave_point": 1.0, "sector_rotation": 0.5, "mean_reversion": 0.0},',
            '"strategy_weights": {"chan_buy1": 2.0, "ma_breakout": 2.0, "wave_point": 2.0, "prev_close_A": 2.0, '
            '"momentum_breakout": 0.0, "sector_rotation": 0.5, "mean_reversion": 0.0},',
            "趋势.strategy_weights 换趋势类主战法")
edit_lineno(114,
            '"signal_prefer": {"momentum_breakout": 2.0, "ma_breakout": 1.5, "wave_point": 1.5, "chan_buy1": 1.0, "chan_buy3": 1.0},',
            '"signal_prefer": {"chan_buy1": 2.0, "ma_breakout": 2.0, "wave_point": 2.0, "prev_close_A": 2.0, '
            '"chan_buy3": 1.0, "momentum_breakout": 0.0},',
            "趋势.signal_prefer 同步")

# ── P0-1: 上班族中短线 — 让 wave_point 也能单信号确认(2.0), 与纯B型画像区分 ──
edit_lineno(87, '"signal_prefer": {"momentum_breakout": 2.0, "wave_point": 1.5,',
            '"signal_prefer": {"wave_point": 2.0, "momentum_breakout": 2.0,',
            "上班族.signal_prefer 波点升为可单信号确认")

out = "\n".join(lines)
assert out != src, "无改动!"
io.open(P, "w", encoding="utf-8", newline="").write(out)
py_compile.compile(P, doraise=True)
print("✅ py_compile 通过")

print("\n=== 改动清单 ===")
for tag, ln, old, new in edits:
    print(f"\n[{tag}] L{ln}")
    print(f"   - {old}")
    print(f"   + {new}")

print("\n=== 回读复核(改动区) ===")
back = io.open(P, encoding="utf-8").read().split("\n")
for tag, ln, _o, _n in edits:
    for k in range(max(0, ln - 3), min(len(back), ln + 1)):
        print(f"   {k+1}: {back[k].strip()[:120]}")
    print("   ---")

print("\n=== 5 画像 strategy_weights / signal_prefer 终值 ===")
import importlib.util
spec = importlib.util.spec_from_file_location("tt", P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
for nm, prof in m.TRADER_PROFILES.items():
    print(f"\n  {nm}")
    print("    strategy_weights:", prof["strategy_weights"])
for nm, cfg in m.SCREENING_CONFIGS.items():
    print(f"\n  {nm} signal_prefer:", cfg.get("signal_prefer"))
