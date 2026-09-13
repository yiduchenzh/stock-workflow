# -*- coding: utf-8 -*-
"""本周(08-10~08-14)全自动交易全量统计"""
import sys, json
sys.path.insert(0, '.')
from pathlib import Path
from collections import defaultdict

ROOT = Path(r"D:\Hermes Agent CN Desktop\stock-workflow\data")
WEEK = ("2026-08-10", "2026-08-14")

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

def in_week(ts):
    d = str(ts)[:10]
    return WEEK[0] <= d <= WEEK[1]

all_trades = []
for agent in ["上班族中短线", "短线狙击手", "趋势跟踪者", "新手入门", "价值投资者"]:
    for t in load(agent):
        t["agent"] = agent
        if in_week(t.get("time", "")):
            all_trades.append(t)
sim = json.loads((ROOT / "sim_trades.json").read_bytes().decode("utf-8", errors="replace"))
for t in sim:
    t["agent"] = "主账户"
    if in_week(t.get("time", "")):
        all_trades.append(t)

print(f"=== 本周 {WEEK[0]} ~ {WEEK[1]} 交易总览 ===")
print(f"总记录: {len(all_trades)} 笔 (buy={sum(1 for t in all_trades if t['action']=='buy')}, "
      f"sell={sum(1 for t in all_trades if t['action']=='sell')})")
print()

# 按日统计
by_day = defaultdict(list)
for t in all_trades:
    by_day[str(t.get("time", ""))[:10]].append(t)
for d in sorted(by_day):
    buys = [t for t in by_day[d] if t["action"] == "buy"]
    sells = [t for t in by_day[d] if t["action"] == "sell"]
    pnl = sum(t.get("pnl", 0) for t in sells)
    print(f"  {d}: 买{len(buys)} 卖{len(sells)} 卖出盈亏{pnl:+,.0f}")

print()
print("=== 已了结(卖出)按策略 ===")
by_strat = defaultdict(list)
for t in all_trades:
    if t["action"] != "sell" or "pnl" not in t:
        continue
    strat = t.get("buy_context", {}).get("strategy") or t.get("reason", "?")
    if "prev_close" in strat or "昨收" in t.get("reason", ""):
        key = "昨收战法"
    elif strat == "momentum_breakout":
        key = "动量突破"
    elif "trailing" in t.get("reason", ""):
        key = "移动止盈"
    elif "mtf_close" in t.get("reason", ""):
        key = "MTF信号"
    elif "chan" in strat:
        key = "缠论"
    else:
        key = f"其他({strat})"
    by_strat[key].append(t)

print(f"{'策略':<12}{'笔数':>4}{'胜':>4}{'胜率':>7}{'平均%':>8}{'累计盈亏':>10}")
for k, trades in sorted(by_strat.items(), key=lambda x: -sum(t["pnl"] for t in x[1])):
    wins = sum(1 for t in trades if t["pnl"] > 0)
    avg = sum(t["pnl_pct"] for t in trades) / len(trades)
    total = sum(t["pnl"] for t in trades)
    print(f"{k:<12}{len(trades):>4}{wins:>4}{wins/len(trades)*100:>6.0f}%{avg:>8.2f}{total:>10.0f}")

print()
print("=== 卖出明细 (按时间) ===")
for t in sorted([x for x in all_trades if x["action"] == "sell" and "pnl" in x], key=lambda x: x.get("time", "")):
    strat = t.get("buy_context", {}).get("strategy", t.get("reason", "?"))
    print(f"  {t.get('time','')[:16]} {t['agent']:<8} {t['code']} {strat[:22]:<24} "
          f"{t.get('pnl_pct',0):+.2f}% ({t.get('pnl',0):+,.0f}) {t.get('reason','')[:28]}")

print()
print("=== 当前持仓 (agent state 汇总) ===")
for agent in ["上班族中短线", "短线狙击手", "趋势跟踪者", "新手入门", "价值投资者"]:
    sp = ROOT / f"agent_{agent}" / "state.json"
    if sp.exists():
        try:
            d = json.loads(sp.read_bytes().decode("utf-8", errors="replace"))
            pos = d.get("positions", {})
            cash = d.get("cash", 0)
            tv = d.get("total_value", 0)
            codes = ",".join(pos.keys()) if pos else "空仓"
            print(f"  {agent}: 总资产{tv:,.0f} 现金{cash:,.0f} [{codes}]")
        except Exception as e:
            print(f"  {agent}: 读取失败 {e}")

# 主账户
try:
    sd = json.loads((ROOT / "sim_state.json").read_bytes().decode("utf-8", errors="replace"))
    pos = sd.get("positions", {})
    print(f"  主账户: 总资产{sd.get('total_value',0):,.0f} 现金{sd.get('cash',0):,.0f} [{','.join(pos.keys()) if pos else '空仓'}]")
except Exception as e:
    print(f"  主账户: 读取失败 {e}")

# 保存全量明细供分析
with open("data/week_analysis.json", "w", encoding="utf-8") as f:
    json.dump([{k: t.get(k) for k in ["time", "agent", "action", "code", "shares", "price", "pnl", "pnl_pct", "reason", "holding_days", "fee"]} for t in all_trades], f, ensure_ascii=False, indent=1)
print(f"\n明细已存 data/week_analysis.json")
