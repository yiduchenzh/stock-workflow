# -*- coding: utf-8 -*-
"""小龙女方法论 · 补充验证 v2

v1 发现：
  ✅ 缩量大阳 (+1.36%/55.5%) 远优于放量大阳 (+0.14%/44.3%)
  ✅ 暴跌日缩量 (+0.69%/51.5%)
  ✅ 逆势放量红 -0.65%/39.6%（避坑成立）
  ❌ 高位缩量横盘 反了（+0.78%/53.7%）
  ❌ 低位缩量横盘 不成立
  ⚠️ 涨停后缩量阴 n=203 太小，且缺"位"条件（她说的是"缩量不破"，我只测了"缩量"）

v2 补：
  A. 缩量大阳按位置分层（找最优区间）
  B. 涨停后阴线补"位"条件：收在 MA5 上方(=不破) vs 下方(=破)
  C. 真突破（T-1 收盘 > T-2 的 20 日高）是否比"贴着20日高"更有效
"""
import argparse
import sqlite3

import numpy as np
import pandas as pd

DEFAULT_DB = "D:/Hermes Agent CN Desktop/hunter-v2/data/factor_panel.db"
DEFAULT_START = "2024-09-25"


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
    for n in (1, 3, 5, 10):
        df["f%d" % n] = g["close"].shift(-n) / df["close"] - 1
    df["vr"] = g["volume"].transform(lambda s: s / s.rolling(5).mean().shift(1).replace(0, np.nan))
    df["ma5"] = g["close"].transform(lambda s: s.rolling(5).mean())
    df["ma5_prev"] = g["close"].transform(lambda s: s.rolling(5).mean().shift(1))
    df["hi20"] = g["high"].transform(lambda s: s.rolling(20).max().shift(1))
    df["hi20_2"] = g["high"].transform(lambda s: s.rolling(20).max().shift(2))
    df["dist_hi"] = df["prev_close"] / df["hi20"] - 1
    df["amp1"] = (df["high"] - df["low"]) / df["prev_close"]
    df["amp5"] = g["amp1"].transform(lambda s: s.rolling(5).mean().shift(1))
    lim = np.where(df["code"].str.startswith(("300", "301", "688")), 0.195, 0.095)
    df["is_zt"] = df["pc"] > lim
    df["prev_zt"] = g["is_zt"].shift(1)
    mkt = df.groupby("day")["pc"].median().rename("mkt")
    df = df.join(mkt, on="day")
    m = (df["pc"].abs() < 0.21) & df["vr"].notna()
    return df[m].copy()


def rep(df, name, mask, minn=100):
    s = df[mask.fillna(False)]
    if len(s) < minn:
        print("  %-26s 样本不足(%d)" % (name, len(s)))
        return None
    cells = []
    for n in (1, 3, 5, 10):
        c = "f%d" % n
        cells.append("f%d=%+.2f%%/w%4.1f%%" % (n, s[c].mean() * 100, (s[c] > 0).mean() * 100))
    print("  %-26s n=%7d  %s" % (name, len(s), "  ".join(cells)))
    return name, len(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--start", default=DEFAULT_START)
    a = ap.parse_args()
    pd.set_option("display.width", 260, "display.max_columns", 40)
    df = build(load(a.db, a.start))
    print("样本 %s 行 / %d 只 / %s ~ %s" % (f"{len(df):,}", df.code.nunique(), df.day.min(), df.day.max()))
    print("基准: " + "  ".join("f%d=%+.2f%%/w%.1f%%" % (n, df["f%d" % n].mean() * 100,
                                                        (df["f%d" % n] > 0).mean() * 100)
                               for n in (1, 3, 5, 10)))

    print("\n=== A. 缩量大阳(pc>5% & 量比<1) 按位置分层 ===")
    base = (df.pc > 0.05) & (df.vr < 1)
    rep(df, "A0 缩量大阳(全部)", base)
    rep(df, "A1  其中 贴20日高<5%", base & (df.dist_hi > -0.05))
    rep(df, "A2  其中 距高5-20%", base & (df.dist_hi <= -0.05) & (df.dist_hi > -0.20))
    rep(df, "A3  其中 深跌>20%", base & (df.dist_hi <= -0.20))
    print("  --- 对照：放量大阳(pc>5% & 量比>2) 同分层 ---")
    basep = (df.pc > 0.05) & (df.vr > 2)
    rep(df, "A0p 放量大阳(全部)", basep)
    rep(df, "A1p  其中 贴20日高<5%", basep & (df.dist_hi > -0.05))

    print("\n=== B. 涨停后阴线：补上'位'条件（她说的'缩量不破'）===")
    pz = df.prev_zt.fillna(False)
    rep(df, "B0 涨停后阴线(全部)", pz & (df.pc < 0))
    rep(df, "B1 缩量(vr<0.8)", pz & (df.pc < 0) & (df.vr < 0.8))
    rep(df, "B2 放量(vr>2)", pz & (df.pc < 0) & (df.vr > 2))
    rep(df, "B3 缩量 + 收在MA5上方(不破)", pz & (df.pc < 0) & (df.vr < 0.8) & (df.close > df.ma5_prev))
    rep(df, "B4 缩量 + 跌破MA5(破位)", pz & (df.pc < 0) & (df.vr < 0.8) & (df.close < df.ma5_prev))
    rep(df, "B5 放量 + 跌破MA5", pz & (df.pc < 0) & (df.vr > 2) & (df.close < df.ma5_prev))

    print("\n=== C. 突破 vs 贴高 ===")
    rep(df, "C1 真突破(T-1收>T-2的20日高)", (df.prev_close > df.hi20_2))
    rep(df, "C2 真突破 + 缩量(vr<1)", (df.prev_close > df.hi20_2) & (df.vr < 1))
    rep(df, "C3 真突破 + 放量(vr>2)", (df.prev_close > df.hi20_2) & (df.vr > 2))
    rep(df, "C4 贴20日高(未突破)", (df.dist_hi > -0.02) & (df.dist_hi <= 0))

    print("\n=== D. 核心主线复核：量比分档（全部样本）===")
    d = df.dropna(subset=["vr"]).copy()
    d["vb"] = pd.cut(d.vr, [0, 0.5, 0.8, 1.0, 1.5, 2.5, 5, 999],
                     labels=["<0.5", "0.5-0.8", "0.8-1.0", "1.0-1.5", "1.5-2.5", "2.5-5", ">5"])
    r = d.groupby("vb", observed=True).agg(n=("f5", "size"), f5=("f5", "mean"), w5=("f5", lambda s: (s > 0).mean()))
    r["f5%"] = (r.f5 * 100).round(2)
    r["w5%"] = (r.w5 * 100).round(1)
    r["f1%"] = (d.groupby("vb", observed=True)["f1"].mean() * 100).round(2)
    print(r[["n", "f1%", "f5%", "w5%"]].to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
