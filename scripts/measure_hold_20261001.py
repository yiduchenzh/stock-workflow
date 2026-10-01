# -*- coding: utf-8 -*-
"""持仓保护(实测: 1-2天被卖出的仓位, 之后 1/2 日价格走向) → 判定 min_hold_days 该不该生效"""
import io
import json
import os
import sqlite3
from collections import defaultdict, deque

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACT = ["上班族中短线", "价值投资者", "新手入门", "短线狙击手", "趋势跟踪者", "主sim"]


def load(p, d=None):
    try:
        return json.load(io.open(os.path.join(ROOT, p), encoding="utf-8"))
    except Exception:
        return d


def trs(name):
    f = "data/sim_trades.json" if name == "主sim" else "data/agent_%s/trades.json" % name
    t = load(f, [])
    return t.get("trades", []) if isinstance(t, dict) else t


con = sqlite3.connect("file:D:/MarketData/market.db?mode=ro", uri=True)


def closes_after(code, date, n=3):
    return [r[0] for r in con.execute(
        "select close from kline_daily where code=? and ts>? order by ts limit ?", (code, date, n))]


short_exits, ok_exits = [], []
holds = []
for acct in ACT:
    book = defaultdict(deque)
    for r in trs(acct):
        c = str(r.get("code"))
        d = str(r.get("date") or r.get("time"))[:10]
        if str(r.get("action")) == "buy":
            book[c].append(d)
        elif str(r.get("action")) == "sell" and book[c]:
            bd = book[c].popleft()
            import datetime
            try:
                hd = (datetime.date(*map(int, d.split("-"))) - datetime.date(*map(int, bd.split("-")))).days
            except Exception:
                continue
            rec = {"acct": acct, "code": c, "buy": bd, "sell": d, "held": hd,
                   "px": float(r.get("price") or 0), "pnl_pct": float(r.get("pnl_pct") or 0),
                   "reason": str(r.get("reason") or "")[:12]}
            holds.append(rec)
            nxt = closes_after(c, d, 2)
            if not nxt:
                continue
            rec["after1"] = (nxt[0] / rec["px"] - 1) * 100 if len(nxt) > 0 else None
            rec["after2"] = (nxt[1] / rec["px"] - 1) * 100 if len(nxt) > 1 else None
            (short_exits if hd < 3 else ok_exits).append(rec)

print("配对样本 %d 笔 | 其中持仓 <3 天被卖: %d 笔 (%.0f%%)" %
      (len(holds), len(short_exits), 100 * len(short_exits) / len(holds) if holds else 0))
print()
for lab, grp in (("持仓<3天被卖", short_exits), ("持仓≥3天被卖", ok_exits)):
    a1 = [g["after1"] for g in grp if g.get("after1") is not None]
    a2 = [g["after2"] for g in grp if g.get("after2") is not None]
    if not a1:
        continue
    print("【%s】%d 笔" % (lab, len(grp)))
    print("   卖出后 1 日: 均值 %+.2f%% | 继续跌占 %.0f%% | 反弹占 %.0f%%" %
          (sum(a1) / len(a1), 100 * sum(1 for x in a1 if x < 0) / len(a1), 100 * sum(1 for x in a1 if x > 0) / len(a1)))
    if a2:
        print("   卖出后 2 日: 均值 %+.2f%% | 继续跌占 %.0f%%" %
              (sum(a2) / len(a2), 100 * sum(1 for x in a2 if x < 0) / len(a2)))
print()
print("=== 判定 ===")
a1 = [g["after1"] for g in short_exits if g.get("after1") is not None]
if a1:
    m = sum(a1) / len(a1)
    if m < 0:
        print("  持仓<3天卖出后 1 日均值 %+.2f%% (继续跌) ⇒ **卖得对** ⇒ 强行 min_hold=3 会让浮亏继续扩大" % m)
    else:
        print("  持仓<3天卖出后 1 日均值 %+.2f%% (反弹) ⇒ 卖早了 ⇒ min_hold 生效有利" % m)
print()
print("按卖出原因分布(<3天组):")
rc = defaultdict(lambda: [0, 0.0])
for g in short_exits:
    k = g["reason"].split("@")[0].split(":")[0].strip()
    rc[k][0] += 1
    rc[k][1] += g.get("after1") or 0
for k, (n, s) in sorted(rc.items(), key=lambda x: -x[1][0]):
    print("   %-14s %3d 笔 | 之后1日均值 %+.2f%%" % (k, n, s / n if n else 0))
con.close()
