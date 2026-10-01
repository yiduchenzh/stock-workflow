# -*- coding: utf-8 -*-
"""对账: (1) 主sim 权威日盈亏全史  (2) 各画像现金回放 vs state.cash → 判定 trades 是否被截断"""
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS = ["上班族中短线", "价值投资者", "新手入门", "短线狙击手", "趋势跟踪者"]


def load(p, default=None):
    try:
        return json.load(io.open(os.path.join(ROOT, p), encoding="utf-8"))
    except Exception:
        return default


print("=" * 86)
print("A. 主 sim 权威曲线（pnl_tracker.json — created %s）" % (load("data/pnl_tracker.json", {}) or {}).get("created", "?"))
print("=" * 86)
pt = load("data/pnl_tracker.json", {}) or {}
daily = pt.get("daily") or []
print("日记录数: %d | capital: %s | 记录区间: %s ~ %s" %
      (len(daily), pt.get("capital"), daily[0]["date"] if daily else "-", daily[-1]["date"] if daily else "-"))
print("%-12s %11s %9s %9s %10s" % ("日期", "总资产", "当日%", "累计%", "仓位"))
for d in daily:
    if d["date"] >= "2026-08-10":
        print("%-12s %11.0f %9s %9s %10s" % (d["date"], d["total"], d.get("pnl_pct"), d.get("cum_pct"), d.get("positions")))
    elif d["date"] in ("2026-07-04", "2026-07-31"):
        print("%-12s %11.0f %9s %9s %10s  ←" % (d["date"], d["total"], d.get("pnl_pct"), d.get("cum_pct"), d.get("positions")))
print("\n月末快照:")
for m in ("2026-07", "2026-08", "2026-09"):
    ms = [d for d in daily if d["date"].startswith(m)]
    if ms:
        print("  %s: 末 %s 总资产 %.0f 累计 %s%% | 月内最高 %.0f 最低 %.0f" %
              (m, ms[-1]["date"], ms[-1]["total"], ms[-1].get("cum_pct"),
               max(x["total"] for x in ms), min(x["total"] for x in ms)))

print()
print("=" * 86)
print("B. 现金回放对账（本金 1,000,000 → 逐笔复算 cash，与 state.cash 比对）")
print("=" * 86)
print("%-14s %6s %14s %14s %14s %10s" % ("账户", "笔数", "回放后cash", "state.cash", "差额", "判定"))
for name in AGENTS:
    tr = load("data/agent_%s/trades.json" % name) or []
    if isinstance(tr, dict):
        tr = tr.get("trades", [])
    st = load("data/agent_%s/state.json" % name) or {}
    cash = 1_000_000.0
    nb = ns = 0
    for r in tr:
        a = str(r.get("action"))
        sh = float(r.get("shares") or 0)
        px = float(r.get("price") or 0)
        if a == "buy":
            fee = float((r.get("cost_detail") or {}).get("total") or 0) or float(r.get("commission") or 0)
            cash -= sh * px + fee
            nb += 1
        elif a == "sell":
            net = r.get("net")
            cash += float(net) if net is not None else sh * px
            ns += 1
    st_cash = float(st.get("cash") or 0)
    diff = cash - st_cash
    verdict = "✅ 一致" if abs(diff) < 5 else ("⚠️ 差 %.0f(疑截断/漏笔)" % diff)
    print("%-14s %6d %14.0f %14.0f %14.0f %10s" % (name, len(tr), cash, st_cash, diff, verdict))
    print("        └ 买 %d / 卖 %d | 持仓 %d | Σ持仓市值 %.0f | Σ持仓成本 %.0f" %
          (nb, ns, len(st.get("positions") or {}),
           sum(float(v.get("shares") or 0) * float(v.get("current_price") or 0) for v in (st.get("positions") or {}).values()),
           sum(float(v.get("shares") or 0) * float(v.get("avg_cost") or 0) for v in (st.get("positions") or {}).values())))

print()
print("C. 主 sim 同样对账（sim_trades.json vs sim_state.json）")
tr = load("data/sim_trades.json") or []
if isinstance(tr, dict):
    tr = tr.get("trades", [])
st = load("data/sim_state.json") or {}
cash = 1_000_000.0
nb = ns = 0
for r in tr:
    a = str(r.get("action"))
    sh = float(r.get("shares") or 0); px = float(r.get("price") or 0)
    if a == "buy":
        fee = float((r.get("cost_detail") or {}).get("total") or 0) or float(r.get("commission") or 0)
        cash -= sh * px + fee; nb += 1
    elif a == "sell":
        net = r.get("net"); cash += float(net) if net is not None else sh * px; ns += 1
print("  笔数 %d (买%d/卖%d) | 回放cash %.0f | state.cash %.0f | 差 %.0f" %
      (len(tr), nb, ns, cash, float(st.get("cash") or 0), cash - float(st.get("cash") or 0)))
print("  state: capital=%s total=%s close_total=%s date=%s" %
      (st.get("capital"), st.get("total"), st.get("close_total"), st.get("date")))
print("  ⚠️ sim_trades 最早一笔 %s | pnl_tracker created %s → 若早于前者, 说明 trades 被截断" %
      (min((str(r.get("date") or r.get("time"))[:10] for r in tr), default="-"), pt.get("created", "?")[:10]))
