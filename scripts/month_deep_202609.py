# -*- coding: utf-8 -*-
"""全周期深度分析: 成本拖累 / 规模不对称 / 买点追高 / 持仓周期 / 预算闸实态"""
import io
import json
import os
import sqlite3
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS = ["上班族中短线", "价值投资者", "新手入门", "短线狙击手", "趋势跟踪者"]


def load(p, default=None):
    try:
        return json.load(io.open(os.path.join(ROOT, p), encoding="utf-8"))
    except Exception:
        return default


def trs(name):
    f = "data/sim_trades.json" if name == "主sim" else "data/agent_%s/trades.json" % name
    t = load(f, [])
    if isinstance(t, dict):
        t = t.get("trades", [])
    return t


def d10(r):
    return str(r.get("date") or r.get("time") or "")[:10]


print("=" * 90)
print("A. 预算闸实态（risk_budget*.json）— 决定回撤保护是否真的在工作")
print("=" * 90)
print("%-30s %10s %9s %11s %9s %s" % ("文件", "peak", "current", "drawdown%", "weekly_pnl", "daily末3日"))
import glob
for f in sorted(glob.glob(os.path.join(ROOT, "data", "risk_budget*.json"))):
    d = load("data/" + os.path.basename(f), {}) or {}
    dl = d.get("daily") or {}
    ks = sorted(dl)[-3:] if isinstance(dl, dict) else []
    print("%-30s %10s %9.0f %10s%% %11s %s" %
          (os.path.basename(f), d.get("peak_value"), float(d.get("current_value") or 0),
           round(float(d.get("drawdown_pct") or 0) * 100, 2) if d.get("drawdown_pct") is not None else "-",
           ("%.6f" % float(d.get("weekly_pnl") or 0)), {k: round(float(dl[k]), 6) for k in ks}))

print()
print("=" * 90)
print("B. 交易成本拖累（可见窗口内: 佣金+印花税+过户费+滑点）")
print("=" * 90)
tot_fee = tot_turnover = 0.0
print("%-14s %10s %14s %12s %10s" % ("账户", "笔数", "成交额合计", "费用合计", "费用/成交"))
for name in AGENTS + ["主sim"]:
    t = trs(name)
    fee = turn = 0.0
    for r in t:
        sh = float(r.get("shares") or 0); px = float(r.get("price") or 0)
        amt = sh * px
        turn += amt
        c = (r.get("cost_detail") or {}).get("total")
        fee += float(c) if c is not None else float(r.get("commission") or 0)
        # 滑点成本
        sl = r.get("slippage_pct")
        if sl is not None:
            fee += amt * float(sl) / 100.0
    if not t:
        continue
    tot_fee += fee; tot_turnover += turn
    print("%-14s %10d %14.0f %12.0f %9.3f%%" % (name, len(t), turn, fee, 100 * fee / turn if turn else 0))
print("-" * 90)
print("可见窗口合计: 成交额 %.0f 元 | 成本 %.0f 元 (占成交额 %.3f%%) | 占本金(6账户) %.3f%%" %
      (tot_turnover, tot_fee, 100 * tot_fee / tot_turnover if tot_turnover else 0, 100 * tot_fee / 6_000_000))

print()
print("=" * 90)
print("C. 规模不对称（金额期望 vs 百分比期望；赚的笔是否比亏的笔小）")
print("=" * 90)
print("%-14s %8s %12s %12s %12s %12s %10s" % ("账户", "卖笔", "金额E/笔", "百分比E", "平均盈额", "平均亏额", "盈/亏额比"))
for name in AGENTS + ["主sim"]:
    t = [r for r in trs(name) if str(r.get("action")) == "sell"]
    if not t:
        continue
    amts = []
    pcts = []
    for r in t:
        sh = float(r.get("shares") or 0); px = float(r.get("price") or 0)
        p = float(r.get("pnl") or 0)
        amts.append(p)
        pp = r.get("pnl_pct")
        if pp is None and sh * px:
            pp = p / (sh * px) * 100
        pcts.append(float(pp or 0))
    w = [a for a in amts if a > 0]; l = [a for a in amts if a <= 0]
    ea = sum(amts) / len(amts); ep = sum(pcts) / len(pcts)
    aw = sum(w) / len(w) if w else 0; al = sum(l) / len(l) if l else 0
    print("%-14s %8d %12.0f %11.2f%% %12.0f %12.0f %10s" %
          (name, len(t), ea, ep, aw, al, ("%.2f" % (aw / abs(al))) if al else "-"))

print()
print("=" * 90)
print("D. 买点追高核验（买入价 vs 该股前收盘 / 当日开盘）— market.db 实算")
print("=" * 90)
con = sqlite3.connect("file:D:/MarketData/market.db?mode=ro", uri=True)
prev_cache = {}


def prev_close(code, date):
    k = (code, date)
    if k in prev_cache:
        return prev_cache[k]
    r = con.execute("select close from kline_daily where code=? and ts<? order by ts desc limit 1",
                    (code, date)).fetchone()
    prev_cache[k] = r[0] if r else None
    return prev_cache[k]


def day_bar(code, date):
    return con.execute("select open,close,high from kline_daily where code=? and ts=?",
                       (code, date)).fetchone()


rows = []
for name in AGENTS + ["主sim"]:
    for r in trs(name):
        if str(r.get("action")) != "buy":
            continue
        c = str(r.get("code")); dt = d10(r); px = float(r.get("price") or 0)
        pc = prev_close(c, dt); bar = day_bar(c, dt)
        if not pc or px <= 0:
            continue
        rows.append({"acct": name, "code": c, "date": dt, "px": px,
                     "chg": (px / pc - 1) * 100,
                     "day_chg": ((bar[1] / pc - 1) * 100) if bar and bar[1] else None,
                     "intraday_pos": ((px - bar[0]) / (bar[2] - bar[0]) * 100) if bar and bar[2] > bar[0] else None})
print("可核验买入笔数: %d / %d" % (len(rows), sum(1 for n in AGENTS + ["主sim"] for r in trs(n) if str(r.get("action")) == "buy")))
if rows:
    ch = [x["chg"] for x in rows]
    print("买入价相对前收涨幅: 均值 %+.2f%% | 中位 %+.2f%% | 最大 %+.2f%% | 最小 %+.2f%%" %
          (sum(ch) / len(ch), sorted(ch)[len(ch) // 2], max(ch), min(ch)))
    for lo, hi, lab in ((3, 99, "追高 >+3%"), (5, 99, "追高 >+5%"), (-99, 0, "逢跌买 <0%")):
        n = sum(1 for x in ch if lo <= x < hi)
        print("  %-14s %4d 笔 (%.0f%%)" % (lab, n, 100 * n / len(ch)))
    print("\n  按住处分组（买价相对前收）的后续表现:")
    print("  %-14s %6s %10s %10s" % ("分组", "笔数", "已实现均值", "胜率"))
    for lo, hi, lab in ((3, 99, "追高>+3%"), (0, 3, "0~+3%"), (-99, 0, "跌时买")):
        sel = [x for x in rows if lo <= x["chg"] < hi]
        if not sel:
            continue
        pnls = []
        for x in sel:
            for r in trs(x["acct"]):
                if str(r.get("action")) == "sell" and str(r.get("code")) == x["code"] and d10(r) >= x["date"]:
                    pnls.append(float(r.get("pnl") or 0)); break
        if pnls:
            print("  %-14s %6d %10.0f %9.0f%%" % (lab, len(pnls), sum(pnls) / len(pnls),
                                                  100 * sum(1 for p in pnls if p > 0) / len(pnls)))

print()
print("=" * 90)
print("E. 持仓周期（买→卖 交易日间隔，用日期差近似）")
print("=" * 90)
import datetime
holds = defaultdict(list)
for name in AGENTS + ["主sim"]:
    t = trs(name)
    last_buy = {}
    for r in t:
        d = d10(r)
        if str(r.get("action")) == "buy":
            last_buy[str(r.get("code"))] = d
        elif str(r.get("action")) == "sell" and str(r.get("code")) in last_buy:
            try:
                a = datetime.date(*map(int, last_buy[str(r.get("code"))].split("-")))
                b = datetime.date(*map(int, d.split("-")))
                holds[name].append((b - a).days)
            except Exception:
                pass
            last_buy.pop(str(r.get("code")), None)
for name in AGENTS + ["主sim"]:
    h = holds.get(name) or []
    if h:
        print("  %-14s 平均 %4.1f 天 | 中位 %2d | 1天内 %d 笔 | ≤3天 %d 笔 / 共 %d" %
              (name, sum(h) / len(h), sorted(h)[len(h) // 2], sum(1 for x in h if x <= 1),
               sum(1 for x in h if x <= 3), len(h)))
con.close()
