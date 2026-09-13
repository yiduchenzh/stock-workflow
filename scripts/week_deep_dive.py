# -*- coding: utf-8 -*-
"""深挖本周问题: 603232 巨亏 + 08-13 清仓日背景 + prev_close_B 追高"""
import sys, json
sys.path.insert(0, '.')
import warnings
warnings.filterwarnings('ignore')
from pathlib import Path
from collections import defaultdict

ROOT = Path(r"D:\Hermes Agent CN Desktop\stock-workflow\data")

print("=== 1. 603232 完整交易链 (短线狙击手) ===")
trades = json.loads((ROOT / "agent_短线狙击手" / "trades.json").read_bytes().decode("utf-8", errors="replace"))
for t in trades:
    if t.get("code") == "603232":
        print(f"  {t.get('time','')[:16]} {t['action']} {t.get('shares')}股 @{t.get('price')} "
              f"pnl={t.get('pnl_pct',0):+.2f}% pnl={t.get('pnl',0):+,.0f}")
        print(f"    reason={t.get('reason','')}")
        ctx = t.get("context") or t.get("buy_context") or {}
        if ctx:
            print(f"    ctx={json.dumps(ctx, ensure_ascii=False)[:200]}")

print()
print("=== 2. 短线狙击手 08-12 买入时的仓位/风控字段 ===")
for t in trades:
    if t.get("action") == "buy" and str(t.get("time",""))[:10] in ("2026-08-12", "2026-08-14"):
        ctx = t.get("context") or {}
        print(f"  {t.get('time','')[:16]} {t['code']} {t.get('shares')}股 @{t.get('price')} "
              f"strategy={ctx.get('strategy')} score={ctx.get('score')}")

print()
print("=== 3. 各 Agent 当前 state (08-14 收盘) ===")
for agent in ["上班族中短线", "短线狙击手", "趋势跟踪者", "新手入门", "价值投资者"]:
    sp = ROOT / f"agent_{agent}" / "state.json"
    if sp.exists():
        d = json.loads(sp.read_bytes().decode("utf-8", errors="replace"))
        print(f"  {agent}: 现金{d.get('cash',0):,.0f} 持仓={list(d.get('positions',{}).keys())}")
        for code, pos in d.get("positions", {}).items():
            print(f"    {code}: {pos.get('shares')}股 成本{pos.get('avg_cost')} 现价{pos.get('current_price')}")

print()
print("=== 4. 08-13 清仓日: 当时大盘背景 (从 state 或日志推断) ===")
# 检查 08-13 是否有日志
import os
for logf in ["logs/aurora.log", "logs/daemon.log"]:
    p = ROOT.parent / logf
    if p.exists():
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        day_lines = [l for l in lines if "2026-08-13" in l and ("Step0" in l or "market" in l.lower() or "大盘" in l)]
        for l in day_lines[-8:]:
            print(f"  {l[:120]}")
        break

print()
print("=== 5. 08-12/08-14 prev_close_B 买入的 strong_grade (强势池护栏是否拦截) ===")
# 从 engine 候选/评分找 strong_grade  — 看 002532/600595 是不是 B 级放行的
for code in ["002532", "600595", "603232", "002400", "002437", "300634", "002353", "603115", "002179"]:
    try:
        from data.sources import get_kline
        k = get_kline(code, 60)
        print(f"  {code}: K线{len(k)}根 OK")
    except Exception as e:
        print(f"  {code}: {e}")
