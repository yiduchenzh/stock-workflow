# -*- coding: utf-8 -*-
"""buy_A 稳健性检验 —— 决定它够不够格接进选股器

buy_A = 涨幅>5% & 量比<1 & 距20日高>-5%
基准（v1/v2 实测）：次日 +2.86% / 胜率 63.8%（全样本 +0.07% / 48.0%）

本脚本检验 7 项：
  A 分年度（2025 / 2026）
  B 分板块（主板 / 创业+科创）
  C 交易成本后净收益（佣金+印花税+滑点）
  D 收益分位数（不能只看均值）
  E 样本外（时间切分）
  F 不同持有期（1/2/3/5/10）
  G 显著性（t 值）
"""
import argparse
import sqlite3

import numpy as np
import pandas as pd

DEFAULT_DB = "D:/Hermes Agent CN Desktop/hunter-v2/data/factor_panel.db"
DEFAULT_START = "2024-09-25"

# A股实际成本（双边）: 佣金万2.5*2 + 印花税千1(卖) + 滑点0.1%*2
COST = 0.00025 * 2 + 0.001 + 0.001 * 2


def load(db_path, start):
    uri = f"file:{db_path}?mode=ro&immutable=1"
    con = sqlite3.connect(uri, uri=True, timeout=30)
    try:
        return pd.read_sql("select code,day,open,high,low,close,volume from kline_daily "
                           "where day>=? order by code,day", con, params=(start,))
    finally:
        con.close()


def build(df):
    g = df.groupby("code", sort=False)
    df["pc"] = g["close"].pct_change()
    df["prev_close"] = g["close"].shift(1)
    for n in (1, 2, 3, 5, 10, 20):
        df["f%d" % n] = g["close"].shift(-n) / df["close"] - 1
    df["vr"] = g["volume"].transform(lambda s: s / s.rolling(5).mean().shift(1).replace(0, np.nan))
    df["hi20"] = g["high"].transform(lambda s: s.rolling(20).max().shift(1))
    df["dist_hi"] = df["prev_close"] / df["hi20"] - 1
    m = (df["pc"].abs() < 0.21) & df["vr"].notna() & df["dist_hi"].notna()
    df = df[m].copy()
    df["is_cyb"] = df["code"].str.startswith(("300", "301", "688"))
    df["year"] = df["day"].str[:4]
    df["buyA"] = (df.pc > 0.05) & (df.vr < 1.0) & (df.dist_hi > -0.05)
    return df


def stat(s, col, cost=0.0):
    x = s[col].dropna() - cost
    n = len(x)
    if n < 30:
        return dict(n=n)
    t = x.mean() / (x.std(ddof=1) / np.sqrt(n)) if x.std(ddof=1) > 0 else 0.0
    return dict(n=n, mean=x.mean() * 100, med=x.median() * 100,
                p25=x.quantile(.25) * 100, p75=x.quantile(.75) * 100,
                win=(x > 0).mean() * 100, t=t)


def line(tag, d):
    if d.get("n", 0) < 30:
        print("  %-22s 样本不足(%s)" % (tag, d.get("n")))
        return
    print("  %-22s n=%6d  mean=%+6.2f%%  med=%+6.2f%%  p25=%+6.2f%%  p75=%+6.2f%%  win=%5.1f%%  t=%+5.2f"
          % (tag, d["n"], d["mean"], d["med"], d["p25"], d["p75"], d["win"], d["t"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--start", default=DEFAULT_START)
    a = ap.parse_args()
    pd.set_option("display.width", 260)

    df = build(load(a.db, a.start))
    base = df
    sig = df[df.buyA]
    print("样本 %s 行 | buyA 命中 %d 次 (%.3f%%)" % (f"{len(df):,}", len(sig),
                                                 len(sig) / len(df) * 100))
    print("成本假设 = %.3f%%（佣金万2.5双边 + 印花税千1 + 滑点0.1%%双边）\n" % (COST * 100))

    print("=" * 112)
    print("【A. 分年度】")
    print("=" * 112)
    for y in sorted(df.year.unique()):
        line("buyA %s" % y, stat(sig[sig.year == y], "f1"))
        line("基准 %s" % y, stat(base[base.year == y], "f1"))

    print("\n" + "=" * 112)
    print("【B. 分板块（次日 f1）】")
    print("=" * 112)
    for lab, m in [("主板", ~sig.is_cyb), ("创业+科创", sig.is_cyb)]:
        line("buyA %s" % lab, stat(sig[m], "f1"))
    for lab, m in [("主板", ~base.is_cyb), ("创业+科创", base.is_cyb)]:
        line("基准 %s" % lab, stat(base[m], "f1"))

    print("\n" + "=" * 112)
    print("【C. 交易成本后（f1，逐个持有期）】")
    print("=" * 112)
    for n in (1, 2, 3, 5, 10):
        line("buyA f%d 成本前" % n, stat(sig, "f%d" % n, 0.0))
        line("buyA f%d 成本后" % n, stat(sig, "f%d" % n, COST))

    print("\n" + "=" * 112)
    print("【D. 收益分位数（f1，成本后）】")
    print("=" * 112)
    line("buyA f1", stat(sig, "f1", COST))
    line("基准 f1", stat(base, "f1", COST))
    sig1 = sig.f1.dropna() - COST
    print("  分位: p05=%+.2f%% p10=%+.2f%% p50=%+.2f%% p90=%+.2f%% p95=%+.2f%% 最大亏=%.2f%%"
          % (sig1.quantile(.05) * 100, sig1.quantile(.10) * 100, sig1.quantile(.50) * 100,
             sig1.quantile(.90) * 100, sig1.quantile(.95) * 100, sig1.min() * 100))

    print("\n" + "=" * 112)
    print("【E. 样本外切分（训练 2025-03~2026-02 / 测试 2026-03~2026-09）】")
    print("=" * 112)
    tr = sig[sig.day < "2026-03-01"]
    te = sig[sig.day >= "2026-03-01"]
    line("训练期 buyA f1", stat(tr, "f1", COST))
    line("测试期 buyA f1", stat(te, "f1", COST))
    line("训练期 基准 f1", stat(base[base.day < "2026-03-01"], "f1", COST))
    line("测试期 基准 f1", stat(base[base.day >= "2026-03-01"], "f1", COST))

    print("\n" + "=" * 112)
    print("【F. 与基准的超额（成本后，f1）】")
    print("=" * 112)
    s1 = stat(sig, "f1", COST)
    b1 = stat(base, "f1", COST)
    print("  buyA %.2f%%  vs  基准 %.2f%%   超额 %+.2f pp" % (s1["mean"], b1["mean"],
                                                             s1["mean"] - b1["mean"]))
    print("  胜率 %.1f%%  vs  %.1f%%      +%.1f pp" % (s1["win"], b1["win"], s1["win"] - b1["win"]))

    print("\n" + "=" * 112)
    print("【G. 年度×板块交叉（f1 成本后，检验是否靠单一年份/板块）】")
    print("=" * 112)
    for y in sorted(sig.year.unique()):
        for lab, m in [("主板", ~sig.is_cyb), ("创科", sig.is_cyb)]:
            sub = sig[(sig.year == y) & m]
            d = stat(sub, "f1", COST)
            if d.get("n", 0) >= 30:
                print("  %s %s  n=%5d  mean=%+6.2f%%  win=%5.1f%%  t=%+5.2f"
                      % (y, lab, d["n"], d["mean"], d["win"], d["t"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
