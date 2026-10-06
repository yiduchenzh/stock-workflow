# -*- coding: utf-8 -*-
"""buy_A 执行口径补测 —— 决定全自动战法"怎么买"

背景：原实证口径 = T 日**收盘**买入 → 次日 +2.86%/胜率63.8%。
但全自动系统的真实链路是「T 日收盘选股 → **T+1 开盘买入**」→ 开盘可能跳空，成本更高。
不补这一步就写战法 = 拿错误口径上线。

本脚本测（全部只用 T 日及以前信息选股，无未来函数）：
  A. T+1 开盘买入 → T+1 收盘
  B. T+1 开盘买入 → T+2 收盘
  C. T+1 开盘买入 → T+5 收盘
  D. 次日跳空分布 gap1（开盘溢价有多少）
  E. 跳空过滤：gap1>2% / >3% / >5% 时放弃 → 剩余收益
  F. 加止损：-5% / -7% / -10%（用 T+1 日内最低价判断是否触及）
"""
import argparse
import sqlite3

import numpy as np
import pandas as pd

DEFAULT_DB = "D:/Hermes Agent CN Desktop/hunter-v2/data/factor_panel.db"
DEFAULT_START = "2024-09-25"
COST = 0.00025 * 2 + 0.001 + 0.001 * 2      # 佣金双边+印花税+滑点双边 ≈ 0.35%


def load(db, start):
    uri = f"file:{db}?mode=ro&immutable=1"
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
    df["vr"] = g["volume"].transform(lambda s: s / s.rolling(5).mean().shift(1).replace(0, np.nan))
    df["hi20"] = g["high"].transform(lambda s: s.rolling(20).max().shift(1))
    df["dist_hi"] = df["prev_close"] / df["hi20"] - 1
    # 未来（T+1/T+2/T+5）
    df["o1"] = g["open"].shift(-1)
    df["c1"] = g["close"].shift(-1)
    df["l1"] = g["low"].shift(-1)
    df["h1"] = g["high"].shift(-1)
    df["c2"] = g["close"].shift(-2)
    df["c5"] = g["close"].shift(-5)
    m = (df.pc.abs() < 0.21) & df.vr.notna() & df.dist_hi.notna()
    df = df[m].copy()
    df["buyA"] = (df.pc > 0.05) & (df.vr < 1.0) & (df.dist_hi > -0.05) \
        & df.code.str.startswith(("60", "00")) \
        & ~df.code.str.startswith(("300", "301", "688", "689", "920", "8", "4"))
    return df


def rep(df, tag, col, cost=COST, minn=100):
    s = df[col].dropna() - cost
    if len(s) < minn:
        print("  %-30s 样本不足(%d)" % (tag, len(s)))
        return
    t = s.mean() / (s.std(ddof=1) / np.sqrt(len(s))) if s.std(ddof=1) > 0 else 0
    print("  %-30s n=%5d  均值=%+6.2f%%  中位=%+6.2f%%  胜率=%5.1f%%  t=%+5.2f"
          % (tag, len(s), s.mean() * 100, s.median() * 100, (s > 0).mean() * 100, t))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--start", default=DEFAULT_START)
    a = ap.parse_args()
    pd.set_option("display.width", 260)

    df = build(load(a.db, a.start))
    s = df[df.buyA].copy()
    s["gap1"] = s.o1 / s.close - 1                       # 次日跳空
    s["r_o1c1"] = s.c1 / s.o1 - 1                        # T+1 开盘→T+1 收盘
    s["r_o1c2"] = s.c2 / s.o1 - 1                        # T+1 开盘→T+2 收盘
    s["r_o1c5"] = s.c5 / s.o1 - 1                        # T+1 开盘→T+5 收盘
    s["r_c0c1"] = s.c1 / s.close - 1                     # 原口径：T 收盘→T+1 收盘
    print("buy_A 命中 = %d 次（主板限定）\n" % len(s))

    print("=" * 108)
    print("【D. 次日跳空分布（决定开盘买入的成本溢价）】")
    print("=" * 108)
    g = s.gap1.dropna()
    print("  n=%d  mean=%+.2f%%  median=%+.2f%%  p25=%+.2f%%  p75=%+.2f%%  p90=%+.2f%%"
          % (len(g), g.mean() * 100, g.median() * 100, g.quantile(.25) * 100,
             g.quantile(.75) * 100, g.quantile(.90) * 100))
    print("  跳空>0 占比 %.1f%% ｜ >2%% 占比 %.1f%% ｜ >5%% 占比 %.1f%% ｜ >9%%(一字) 占比 %.1f%%"
          % ((g > 0).mean() * 100, (g > .02).mean() * 100, (g > .05).mean() * 100,
             (g > .09).mean() * 100))

    print("\n" + "=" * 108)
    print("【A/B/C. 各执行口径（已扣 %.2f%% 成本）】" % (COST * 100))
    print("=" * 108)
    rep(s, "原口径: T收盘买→T+1收盘", "r_c0c1")
    rep(s, "口径A: T+1开盘买→T+1收盘", "r_o1c1")
    rep(s, "口径B: T+1开盘买→T+2收盘", "r_o1c2")
    rep(s, "口径C: T+1开盘买→T+5收盘", "r_o1c5")

    print("\n" + "=" * 108)
    print("【E. 跳空过滤（T+1 开盘跳空过大时放弃）】")
    print("=" * 108)
    for thr in (0.02, 0.03, 0.05, 0.07):
        sub = s[(s.gap1 <= thr) & s.gap1.notna()]
        keep = len(sub) / len(s) * 100
        rep(sub, "跳空<=%.0f%% 才买 (留%.0f%%)" % (thr * 100, keep), "r_o1c1")

    print("\n" + "=" * 108)
    print("【F. 加止损（T+1 日内最低触及即止损，按止损价成交）】")
    print("=" * 108)
    for stop in (0.05, 0.07, 0.10):
        # 买入价 = o1；若 l1 <= o1*(1-stop) → 止损
        hit = s.l1 <= s.o1 * (1 - stop)
        r = s.r_o1c1.copy()
        r[hit] = -stop                                   # 被止损
        r2 = s.r_o1c2.copy()
        r2[hit] = -stop
        tmp = s.copy(); tmp["_r"] = r - COST
        rep(tmp, "止损%.0f%% → T+1收盘" % (stop * 100), "_r")
        tmp2 = s.copy(); tmp2["_r2"] = r2 - COST
        rep(tmp2, "止损%.0f%% → T+2收盘" % (stop * 100), "_r2")

    print("\n" + "=" * 108)
    print("【结论判据】口径A（T+1开盘买→T+1收盘）若明显低于原口径 → 战法必须加跳空过滤")
    print("=" * 108)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
