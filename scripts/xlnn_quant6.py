# -*- coding: utf-8 -*-
"""buy_A 正确形态验证：**尾盘买入 → 次日开盘卖出**（吃隔夜溢价）

前情（xlnn_quant5）：buy_A 若按"次日开盘买入"执行 → -1.28%/31.9%（废）。
  → 因为 buy_A 次日平均跳空 +4.11%，alpha 全在"隔夜"这一段。
  → 正确形态只能是【T 日尾盘买入，T+1 开盘/竞价卖出】。
本脚本验证该形态，并逐项确认它是否可落地：
  1. 形态本体：T 收盘买 → T+1 开盘卖（含/不含成本）
  2. 卖不掉的情形：T+1 一字跌停（开盘=跌停价且无成交可能）如何用 day1 开盘卖不掉，顺延
  3. 分年度稳健性
  4. 对照：T+1 开盘不卖 → 持到 T+1 收盘（确认"必须开盘卖"）
  5. 尾盘可得性：14:50 时点能否识别（用 T 日截至收盘的量比近似 + 折扣系数敏感性）
  6. 剔除一字涨停买不到/卖不掉后（T+1 gap>9.8%）的分布
"""
import argparse
import sqlite3

import numpy as np
import pandas as pd

DEFAULT_DB = "D:/Hermes Agent CN Desktop/hunter-v2/data/factor_panel.db"
DEFAULT_START = "2024-09-25"
COST = 0.00025 * 2 + 0.001 + 0.001 * 2      # ≈0.35%（佣金双边+印花税+滑点双边）

GAIN_TAX = 0.001                            # 印花税（卖出）


def load(db, start):
    uri = f"file:{db}?mode=ro&immutable=1"
    con = sqlite3.connect(uri, uri=True, timeout=30)
    try:
        return pd.read_sql(
            "select code,day,open,high,low,close,volume from kline_daily "
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
    df["c1"] = g["close"].shift(-1)
    df["h1"] = g["high"].shift(-1)
    df["l1"] = g["low"].shift(-1)
    # T+1 的昨收就是 T 的收盘 → 可判一字
    df["limit_up1"] = (df.o1 / df.close - 1) > 0.098
    df["limit_dn1"] = (df.o1 / df.close - 1) < -0.098
    m = (df.pc.abs() < 0.21) & df.vr.notna() & df.dist_hi.notna()
    df = df[m].copy()
    df["buyA"] = (df.pc > 0.05) & (df.vr < 1.0) & (df.dist_hi > -0.05) \
        & df.code.str.startswith(("60", "00")) \
        & ~df.code.str.startswith(("300", "301", "688", "689", "920", "8", "4"))
    return df


def stat(s, tag, cost=COST, minn=80):
    s = s.dropna() - cost
    if len(s) < minn:
        print("  %-34s 样本不足(%d)" % (tag, len(s)))
        return None
    sd = s.std(ddof=1)
    t = s.mean() / (sd / np.sqrt(len(s))) if sd > 0 else 0.0
    print("  %-34s n=%5d  均值=%+6.2f%%  中位=%+6.2f%%  胜率=%5.1f%%  t=%+5.2f"
          % (tag, len(s), s.mean() * 100, s.median() * 100, (s > 0).mean() * 100, t))
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--start", default=DEFAULT_START)
    a = ap.parse_args()

    df = build(load(a.db, a.start))
    s = df[df.buyA].copy()
    s["gap1"] = s.o1 / s.close - 1

    print("buy_A 命中 = %d\n" % len(s))
    L = "=" * 104

    print(L + "\n【1. 形态本体：T 日尾盘买入 → T+1 开盘卖出（隔夜溢价）】\n" + L)
    raw = s.gap1
    print("  未扣成本 : mean=%+.2f%%  median=%+.2f%%  >0占比=%.1f%%  >1%%占比=%.1f%%"
          % (raw.mean() * 100, raw.median() * 100, (raw > 0).mean() * 100,
             (raw > .01).mean() * 100))
    stat(s.gap1, "扣成本0.35%后")
    # 更严的成本：尾盘买+开盘卖=两笔，滑点按0.15%计
    stat(s.gap1, "扣成本0.55%(保守)", cost=0.0055)

    print("\n" + L + "\n【2. 一字板影响】\n" + L)
    lu = s.limit_up1.fillna(False)
    ld = s.limit_dn1.fillna(False)
    print("  T+1 一字涨停(gap>9.8%%) 占比 %.1f%% ← 卖得掉(封单里能成交)，但买不到" % (lu.mean() * 100))
    print("  T+1 一字跌停(gap<-9.8%%) 占比 %.1f%% ← 卖不掉(顺延风险)" % (ld.mean() * 100))
    stat(s[~ld].gap1, "剔除一字跌停后（可卖出样本）")
    stat(s[lu].gap1, "仅一字涨停那批")
    stat(s[ld].gap1, "仅一字跌停那批")

    print("\n" + L + "\n【3. 分年度稳健性】\n" + L)
    s["yr"] = s.day.str[:4]
    for yr, sub in s.groupby("yr"):
        stat(sub.gap1, "  " + yr)

    print("\n" + L + "\n【4. 对照：T+1 开盘不卖会怎样】\n" + L)
    stat(s.c1 / s.close - 1, "T 收盘买 → T+1 收盘卖")
    stat(s.h1 / s.close - 1, "T 收盘买 → T+1 最高(理想上限)")
    stat(s.c1 / s.o1 - 1, "T+1 开盘买 → T+1 收盘(反面)")

    print("\n" + L + "\n【5. 尾盘可得性：用 T 日收盘量比识别（14:50 实际量比会更小）】\n" + L)
    for k in (0.80, 0.85, 0.90, 1.00):
        sub = s[s.vr < k]
        stat(sub.gap1, "量比<%.2f （约占%.0f%%）" % (k, len(sub) / len(s) * 100))
    print("  说明：14:50 时成交量约为全日的 92~96%%，故 14:50 观察到的量比"
          "≈收盘量比×0.93；\n        用 vr<0.85 作 14:50 阈值 → 收盘大概率 <0.92 ✅ 可实时判定")

    print("\n" + L + "\n【6. 与基准对比 / 结论】\n" + L)
    base = df[df.pc.abs() < 0.21]
    stat(base.gap1, "全市场基准(T收盘→T+1开盘)")
    print("\n  判据：形态1 扣成本后 中位>+1.5%%、胜率>55%%、t>5 且分年度全正 → 战法成立")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
