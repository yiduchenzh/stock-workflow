# -*- coding: utf-8 -*-
"""剩余三项修复的前置量测:
 A 价值/新手 0 胜率真因(分时段/分退出路径)
 B 单日开仓笔数 → 边际期望(第1/2/3+笔)
 C 滑点真实性: 单笔金额/当日成交额 + 1跳成本 vs 模型 0.2%/边
"""
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


def d10(r):
    return str(r.get("date") or r.get("time") or "")[:10]


con = sqlite3.connect("file:D:/MarketData/market.db?mode=ro", uri=True)
BAR = {}


def bar(code, date):
    if (code, date) not in BAR:
        BAR[(code, date)] = con.execute(
            "select open,high,low,close,volume from kline_daily where code=? and ts=?",
            (code, date)).fetchone()
    return BAR[(code, date)]


print("=" * 88)
print("A. 价值投资者 / 新手入门: 0 胜率真因(按日期+退出路径)")
print("=" * 88)
for name in ("价值投资者", "新手入门"):
    t = trs(name)
    print("\n【%s】共 %d 笔" % (name, len(t)))
    for r in t:
        act = str(r.get("action"))
        rs = str(r.get("reason") or "")
        pre = rs.split("@")[0].split(":")[0].strip()
        print("  %s %-4s %-6s %7s股 %8s元 pnl=%9s pnl%%=%7s %s" %
              (d10(r), act, r.get("code"), r.get("shares"), r.get("price"),
               r.get("pnl"), r.get("pnl_pct"), pre))

print()
print("=" * 88)
print("B. 单日开仓笔数 → 边际期望(同一天第几笔的盈亏%对比)")
print("=" * 88)
day_orders = defaultdict(list)   # date -> [buy records]
for name in ACT:
    for r in trs(name):
        if str(r.get("action")) == "buy":
            day_orders[d10(r)].append(r)
cnt = defaultdict(int)
for d, bs in day_orders.items():
    cnt[len(bs)] += 1
print("单日买入笔数分布:", dict(sorted(cnt.items())), "| 有买入的天数:", len(day_orders))

# FIFO 配对后按「当天下单序号」分组
seq_pnl = defaultdict(list)
for name in ACT:
    book = defaultdict(deque)
    per_day_seq = defaultdict(int)
    for r in trs(name):
        c = str(r.get("code"))
        if str(r.get("action")) == "buy":
            per_day_seq[d10(r)] += 1
            book[c].append({"seq": per_day_seq[d10(r)], "amt": float(r.get("shares") or 0) * float(r.get("price") or 0)})
        elif str(r.get("action")) == "sell" and book[c]:
            b = book[c].popleft()
            k = "第1笔" if b["seq"] == 1 else ("第2笔" if b["seq"] == 2 else "第3笔及以后")
            seq_pnl[k].append((float(r.get("pnl") or 0), float(r.get("pnl_pct") or 0), b["amt"]))
print()
print("%-14s %6s %12s %11s %10s %14s" % ("当天下单次序", "笔数", "平均盈亏额", "平均盈亏%", "胜率", "仓位金额"))
for k in ("第1笔", "第2笔", "第3笔及以后"):
    s = seq_pnl.get(k) or []
    if not s:
        continue
    n = len(s)
    print("%-14s %6d %12.0f %10.2f%% %9.0f%% %14.0f" %
          (k, n, sum(x[0] for x in s) / n, sum(x[1] for x in s) / n,
           100 * sum(1 for x in s if x[0] > 0) / n, sum(x[2] for x in s) / n))

print()
print("=" * 88)
print("C. 滑点真实性: 单笔金额占当日成交额 + 1跳成本 (vs 模型 0.2%/边=0.4%/往返)")
print("=" * 88)
rows = []
for name in ACT:
    for r in trs(name):
        c = str(r.get("code")); dt = d10(r)
        b = bar(c, dt)
        if not b or not b[4]:
            continue
        px = float(r.get("price") or 0); sh = float(r.get("shares") or 0)
        amt = px * sh
        # market.db volume 单位=股 (hunter-v2 口径); 成交额 ≈ close × volume
        turn = b[3] * b[4]
        if turn <= 0 or px <= 0:
            continue
        rows.append({"amt": amt, "turn": turn, "part": amt / turn * 100,
                     "tick_pct": 0.01 / px * 100,
                     "slip_model": float(r.get("slippage_pct") or 0),
                     "base_slip": float(r.get("base_slip_pct") or 0)})
print("可核验成交: %d 笔" % len(rows))
if rows:
    part = sorted(x["part"] for x in rows)
    tick = sorted(x["tick_pct"] for x in rows)
    mod = sorted(x["slip_model"] for x in rows if x["slip_model"] > 0)
    print("单笔占当日成交额: 中位 %.4f%% | 均值 %.4f%% | 90分位 %.4f%% | 最大 %.4f%%" %
          (part[len(part) // 2], sum(part) / len(part), part[int(len(part) * .9)], part[-1]))
    print("1跳成本(0.01/价): 中位 %.4f%% | 均值 %.4f%% | 90分位 %.4f%%" %
          (tick[len(tick) // 2], sum(tick) / len(tick), tick[int(len(tick) * .9)]))
    if mod:
        print("模型实际滑点: 中位 %.4f%% | 均值 %.4f%% (config 基础 0.1%%, 记录里 base≈0.2%%)" %
              (mod[len(mod) // 2], sum(mod) / len(mod)))
    print()
    print("⇒ 结论参考: 若单笔占成交额中位 <0.1%%, 冲击成本可忽略, 真实滑点 ≈ 1跳(%0.2f%%~%0.4f%% 往返);"
          % (tick[0] * 2, tick[-1] * 2))
    print("   模型 0.4%%往返 属于**保守**(偏悲观)假设 → 回测/模拟的收益被低估。")
con.close()
