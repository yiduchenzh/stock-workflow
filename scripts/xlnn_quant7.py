# -*- coding: utf-8 -*-
"""buy_A 真实性检验：**当日涨停的票尾盘买得到吗？**

问题：前几轮实证都用"T 日收盘价"成交，但 buy_A 里很多是当日**涨停**的票——
      涨停封板的票，尾盘 14:50 根本挂不进（封单排队），实盘无法成交。
      若不剔除，回测收益就是"空中楼阁"。

本脚本分层测（T 日收盘买 → T+1 开盘卖）：
  A. 按当日涨幅分层：5~7% / 7~9.5% / >=9.5%(涨停) / 一字涨停(open=high=low=close)
  B. 剔除"封板"票后的隔夜收益（可实际成交的样本）
  C. 剔除后用 vr<0.85 子集的表现
  D. 分年度复核
  E. 若改成"涨5~9.5%"（即买不到涨停就不追）是否仍显著
"""
import argparse
import sqlite3

import numpy as np
import pandas as pd

DEFAULT_DB = "D:/Hermes Agent CN Desktop/hunter-v2/data/factor_panel.db"
DEFAULT_START = "2024-09-25"
COST = 0.00025 * 2 + 0.001 + 0.001 * 2      # ≈0.35%


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
    df["pre_close"] = g["close"].shift(1)
    df["vr"] = g["volume"].transform(
        lambda s: s / s.rolling(5).mean().shift(1).replace(0, np.nan))
    df["hi20"] = g["high"].transform(lambda s: s.rolling(20).max().shift(1))
    df["dist_hi"] = df["pre_close"] / df["hi20"] - 1
    df["o1"] = g["open"].shift(-1)
    df["gap1"] = df["o1"] / df["close"] - 1
    # 当日是否"封板"：收盘≈最高价(收盘在涨停/最高) → 尾盘挂单难度大
    df["close_is_high"] = (df["close"] >= df["high"] * 0.999)
    # 一字（开盘=收盘=最高）当日
    df["yz_today"] = (df["open"] >= df["high"] * 0.999) & (df["close"] >= df["high"] * 0.999)
    m = (df.pc.abs() < 0.21) & df.vr.notna() & df.dist_hi.notna()
    df = df[m].copy()
    df["buyA"] = (df.pc > 0.05) & (df.vr < 1.0) & (df.dist_hi > -0.05) \
        & df.code.str.startswith(("60", "00")) \
        & ~df.code.str.startswith(("300", "301", "688", "689", "920", "8", "4"))
    return df


def stat(s, tag, col="gap1", cost=COST, minn=60):
    x = s[col].dropna() - cost
    if len(x) < minn:
        print("  %-40s 样本不足(%d)" % (tag, len(x)))
        return
    sd = x.std(ddof=1)
    t = x.mean() / (sd / np.sqrt(len(x))) if sd > 0 else 0.0
    print("  %-40s n=%5d  均值=%+6.2f%%  中位=%+6.2f%%  胜率=%5.1f%%  t=%+5.2f"
          % (tag, len(x), x.mean() * 100, x.median() * 100, (x > 0).mean() * 100, t))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--start", default=DEFAULT_START)
    a = ap.parse_args()
    df = build(load(a.db, a.start))
    s = df[df.buyA].copy()
    L = "=" * 112
    print("buy_A 命中 = %d\n" % len(s))

    print(L + "\n【A. 按当日涨幅分层（尾盘可成交性差异）】\n" + L)
    for lo, hi, tag in ((0.05, 0.07, "涨幅 5~7%"),
                        (0.07, 0.095, "涨幅 7~9.5%"),
                        (0.095, 0.21, "涨幅 >=9.5%（涨停/准涨停）")):
        stat(s[(s.pc >= lo) & (s.pc < hi)], tag)
    stat(s[s.yz_today], "其中：当日一字板(买不到)")

    print("\n" + L + "\n【B. 成交可得性分层】\n" + L)
    print("  当日收盘=最高价(封板形态) 占比 %.1f%% ← 尾盘挂单难成交" % (s.close_is_high.mean() * 100))
    print("  当日一字板 占比 %.1f%% ← 完全买不到" % (s.yz_today.mean() * 100))
    stat(s[~s.yz_today], "剔除一字板（可挂单样本）")
    stat(s[~s.close_is_high], "剔除封板形态（收盘<最高，更易成交）")

    print("\n" + L + "\n【C. 可成交样本 × vr<0.85】\n" + L)
    tradable = s[~s.yz_today]
    stat(tradable, "可成交（剔一字）全量")
    stat(tradable[tradable.vr < 0.85], "可成交 × vr<0.85")
    stat(tradable[tradable.vr < 0.80], "可成交 × vr<0.80")
    stat(tradable[tradable.pc < 0.095], "可成交 × 非涨停(涨5~9.5%)")
    stat(tradable[(tradable.pc < 0.095) & (tradable.vr < 0.85)], "可成交 × 非涨停 × vr<0.85")

    print("\n" + L + "\n【D. 分年度复核（剔除一字板后）】\n" + L)
    tradable = tradable.copy()
    tradable["yr"] = tradable.day.str[:4]
    for yr, sub in tradable.groupby("yr"):
        stat(sub, "  " + yr + " 可成交")
        stat(sub[sub.vr < 0.85], "  " + yr + " 可成交×vr<0.85")

    print("\n" + L + "\n【E. 全市场基准对照】\n" + L)
    base = df.copy()
    stat(base, "全市场基准(T收盘→T+1开盘)")

    print("\n" + L)
    print("  判据：剔除一字板后 中位>+1.5%、胜率>55%、t>5 且分年度全正 → 战法在现实中可执行")
    print(L)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
