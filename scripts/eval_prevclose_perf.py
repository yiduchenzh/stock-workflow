# -*- coding: utf-8 -*-
"""按策略统计股票工作流 08-10~08-12 交易绩效"""
import json
from pathlib import Path
from collections import defaultdict

ROOT = Path(r"D:\Hermes Agent CN Desktop\stock-workflow\data")

def load(name):
    p = ROOT / f"agent_{name}" / "trades.json"
    if not p.exists():
        return []
    raw = p.read_bytes()
    for enc in ("utf-8", "gbk", "utf-8-sig"):
        try:
            return json.loads(raw.decode(enc))
        except Exception:
            continue
    return json.loads(raw.decode("utf-8", errors="replace"))

all_trades = []
for agent in ["上班族中短线", "短线狙击手", "趋势跟踪者", "新手入门", "价值投资者"]:
    for t in load(agent):
        t["agent"] = agent
        all_trades.append(t)
# 主账户
sim = json.loads((ROOT / "sim_trades.json").read_bytes().decode("utf-8", errors="replace"))
for t in sim:
    t["agent"] = "主账户"
    all_trades.append(t)

print(f"总交易记录: {len(all_trades)} 笔 (buy={sum(1 for t in all_trades if t['action']=='buy')}, "
      f"sell={sum(1 for t in all_trades if t['action']=='sell')})")

# 按策略分组统计已了结交易 (sell 带 pnl)
by_strat = defaultdict(list)
for t in all_trades:
    if t["action"] != "sell" or "pnl" not in t:
        continue
    strat = t.get("buy_context", {}).get("strategy") or t.get("reason", "?")
    # 归因: prev_close 系
    if "prev_close" in strat or "昨收" in t.get("reason", ""):
        key = "昨收战法(prev_close)"
    elif strat == "momentum_breakout":
        key = "动量突破(momentum)"
    elif t.get("reason_category") == "risk_trail" or "trailing" in t.get("reason", ""):
        key = "老仓移动止盈(08-06)"
    elif "mtf_close" in t.get("reason", ""):
        key = "老仓MTF信号退出"
    elif "chan" in strat:
        key = "缠论"
    else:
        key = f"其他({strat})"
    by_strat[key].append(t)

print()
print("=== 已了结交易按策略统计 ===")
print(f"{'策略':<28}{'笔数':>4}{'胜':>4}{'负':>4}{'胜率':>7}{'平均%':>8}{'累计盈亏':>10}")
for k, trades in sorted(by_strat.items(), key=lambda x: -sum(t["pnl"] for t in x[1])):
    wins = sum(1 for t in trades if t["pnl"] > 0)
    avg = sum(t["pnl_pct"] for t in trades) / len(trades)
    total = sum(t["pnl"] for t in trades)
    print(f"{k:<28}{len(trades):>4}{wins:>4}{len(trades)-wins:>4}{wins/len(trades)*100:>6.0f}%{avg:>8.2f}{total:>10.0f}")

print()
print("=== 昨收战法明细 ===")
for t in [x for x in all_trades if x["action"] == "sell"]:
    strat = t.get("buy_context", {}).get("strategy", "")
    if "prev_close" in strat or "昨收" in t.get("reason", ""):
        print(f"  {t['agent']:<8} {t['code']} {t.get('reason','')[:38]:<40} pnl={t['pnl_pct']:+.2f}% 持有{t['holding_days']}天")

print()
print("=== 持仓中(未了结)按策略 ===")
pos_buy = [t for t in all_trades if t["action"] == "buy"]
for t in pos_buy:
    strat = t.get("context", {}).get("strategy", t.get("reason", "?"))
    print(f"  {t['agent']:<8} {t['code']} {strat[:38]:<40} @{t['price']} {t['time'][:10]}")
