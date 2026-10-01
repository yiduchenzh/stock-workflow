# -*- coding: utf-8 -*-
"""FIFO 配对: 买入时的追高幅度 → 该笔最终盈亏 (全账户)"""
import io
import json
import os
import sqlite3
from collections import defaultdict, deque

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS = ["上班族中短线", "价值投资者", "新手入门", "短线狙击手", "趋势跟踪者"]
ACT = AGENTS + ["主sim"]


def load(p, d=None):
    try:
        return json.load(io.open(os.path.join(ROOT, p), encoding="utf-8"))
    except Exception:
        return d


def trs(name):
    f = "data/sim_trades.json" if name == "主sim" else "data/agent_%s/trades.json" % name
    t = load(f, [])
    return t.get("trades", []) if isinstance(t, dict) else t


def d10(r):
    return str(r.get("date") or r.get("time") or "")[:10]


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
            pc = prev_close(c, d10(r))
            px = float(r.get("price") or 0)
            book[c].append({"date": d10(r), "px": px,
                            "chg": ((px / pc - 1) * 100) if pc else None,
                            "sh": float(r.get("shares") or 0)})
        elif str(r.get("action")) == "sell" and book[c]:
            b = book[c].popleft()
            if b["chg"] is None:
                continue
            pairs.append({"acct": acct, "code": c, "chg": b["chg"],
                          "pnl": float(r.get("pnl") or 0),
                          "pct": float(r.get("pnl_pct") or 0),
                          "sh": b["sh"], "px": b["px"]})

print("FIFO 配对成功: %d 笔（买→卖）" % len(pairs))
print()
print("%-16s %6s %12s %11s %10s %12s" % ("买入追高分组", "笔数", "平均盈亏额", "平均盈亏%", "胜率", "金额期望/笔"))
for lo, hi, lab in ((-99, 0, "跌时买 (<0%)"), (0, 3, "0~+3%"), (3, 5, "+3~+5%"), (5, 99, "+5% 以上")):
    sel = [p for p in pairs if lo <= p["chg"] < hi]
    if not sel:
        continue
    n = len(sel)
    avg = sum(p["pnl"] for p in sel) / n
    avgp = sum(p["pct"] for p in sel) / n
    wr = 100 * sum(1 for p in sel if p["pnl"] > 0) / n
    print("%-16s %6d %12.0f %10.2f%% %9.0f%% %12.0f" % (lab, n, avg, avgp, wr, avg))
print()
allp = pairs
print("全体: %d 笔 | 平均盈亏额 %.0f | 平均盈亏%% %.2f%% | 胜率 %.0f%%" %
      (len(allp), sum(p["pnl"] for p in allp) / len(allp),
       sum(p["pct"] for p in allp) / len(allp),
       100 * sum(1 for p in allp if p["pnl"] > 0) / len(allp)))
print()
print("分账户（FIFO 配对笔数 / 平均追高 / 平均盈亏%）:")
by = defaultdict(list)
for p in pairs:
    by[p["acct"]].append(p)
for a in ACT:
    s = by.get(a) or []
    if s:
        print("  %-14s %3d 笔 | 追高均值 %+6.2f%% | 盈亏均值 %+6.2f%% | 胜率 %3.0f%%" %
              (a, len(s), sum(x["chg"] for x in s) / len(s),
               sum(x["pct"] for x in s) / len(s),
               100 * sum(1 for x in s if x["pnl"] > 0) / len(s)))
print()
print("追高幅度与结果的相关性:")
if len(pairs) > 5:
    xs = [p["chg"] for p in pairs]; ys = [p["pct"] for p in pairs]
    mx = sum(xs) / len(xs); my = sum(ys) / len(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    print("  皮尔逊相关 r = %+.3f  (n=%d)" % (cov / (sx * sy) if sx * sy else 0, len(pairs)))
con.close()
