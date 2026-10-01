# -*- coding: utf-8 -*-
"""追高闸阈值量测: 分桶的 %期望 / 金额期望 / 存活笔数 → 选一个「不掐断信号源」的阈值"""
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
PC = {}


def prev_close(code, date):
    if (code, date) not in PC:
        r = con.execute("select close from kline_daily where code=? and ts<? order by ts desc limit 1",
                        (code, date)).fetchone()
        PC[(code, date)] = r[0] if r else None
    return PC[(code, date)]


pairs = []
for acct in ACT:
    book = defaultdict(deque)
    for r in trs(acct):
        c = str(r.get("code"))
        if str(r.get("action")) == "buy":
            pc = prev_close(c, str(r.get("date") or r.get("time"))[:10])
            px = float(r.get("price") or 0)
            sh = float(r.get("shares") or 0)
            book[c].append({"chg": ((px / pc - 1) * 100) if pc else None, "amt": sh * px, "sh": sh})
        elif str(r.get("action")) == "sell" and book[c]:
            b = book[c].popleft()
            if b["chg"] is None:
                continue
            pairs.append({"chg": b["chg"], "amt": b["amt"], "sh": b["sh"],
                          "pnl": float(r.get("pnl") or 0), "pct": float(r.get("pnl_pct") or 0)})

print("样本 %d 笔" % len(pairs))
print()
print("%-14s %6s %11s %11s %9s %13s" % ("追高区间", "笔数", "平均盈亏%", "平均盈亏额", "胜率", "仓位金额均值"))
bins = [(-99, 0), (0, 2), (2, 4), (4, 6), (6, 8), (8, 10), (10, 12), (12, 99)]
for lo, hi in bins:
    sel = [p for p in pairs if lo <= p["chg"] < hi]
    if not sel:
        continue
    n = len(sel)
    print("%-14s %6d %10.2f%% %11.0f %8.0f%% %13.0f" %
          ("%+d~%+d%%" % (lo, hi), n, sum(p["pct"] for p in sel) / n,
           sum(p["pnl"] for p in sel) / n,
           100 * sum(1 for p in sel if p["pnl"] > 0) / n,
           sum(p["amt"] for p in sel) / n))

print()
print("=== 阈值模拟（假设 >阈值 的买入被拒绝）===")
print("%-12s %8s %10s %14s %16s" % ("追高上限", "存活笔", "存活率", "存活组平均盈亏%", "被拒组平均盈亏%"))
for cap in (3, 4, 5, 6, 7, 8, 10):
    keep = [p for p in pairs if p["chg"] <= cap]
    drop = [p for p in pairs if p["chg"] > cap]
    kp = sum(p["pct"] for p in keep) / len(keep) if keep else 0
    dp = sum(p["pct"] for p in drop) / len(drop) if drop else 0
    print("%-12s %8d %9.0f%% %13.2f%% %15.2f%%" %
          ("≤+%d%%" % cap, len(keep), 100 * len(keep) / len(pairs), kp, dp))

print()
print("=== 仓位压缩方案（信号保留, 仓位按追高幅度递减）===")
print("%-12s %14s %16s" % ("方案", "压缩后金额E", "对比现状金额E"))
base = sum(p["pnl"] for p in pairs) / len(pairs)
print("%-12s %14.0f %16s" % ("现状(无压缩)", base, "-"))
for k in (1.0, 0.7, 0.5, 0.3):
    tot = 0.0
    for p in pairs:
        f = 1.0 if p["chg"] <= 3 else (max(k, 1.0 - (p["chg"] - 3) * 0.1) if p["chg"] <= 10 else k)
        f = min(1.0, max(k, f))
        tot += p["pnl"] * f
    print("%-12s %14.0f %16s" % ("最低系数%.1f" % k, tot / len(pairs), "%+.0f" % (tot / len(pairs) - base)))
con.close()
