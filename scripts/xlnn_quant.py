# -*- coding: utf-8 -*-
"""金融街小龙女「操盘手方法论」可量化规则 · 全市场实证

她的内容全是定性经验（"静悄悄""不像要涨"），本脚本把 7 条可量化的翻译成因子，
用 hunter-v2/data/factor_panel.db（5,545 只 / 179 万行 qfq 日K）验证：
哪些真有 alpha，哪些是零 alpha 的"正确废话"。

规则与口径（全部只用 T 日及以前信息，无未来函数）：
  R1 缩量上涨        pc>0 且 量比<1（真拉升"越涨越缩量"）
  R2 放量大阳        pc>5% 且 量比>2（"普通投资者最爱追放量大阳线，最容易被套"）
  R3 高位放量滞涨    dist20hi>-5% 且 量比>2 且 |pc|<1%（出货三征兆"高、放、滞"）
  R4 低位缩量横盘    dist20hi<-20% 且 量比<0.7 且 5日振幅<3%（"低位缩量横盘可留"）
  R5 暴跌日缩量     大盘跌>1% 且 个股跌 且 量比<0.7（"暴跌日找缩量最狠的"）
  R6 逆势放量红     大盘跌>1% 且 个股涨>2% 且 量比>2（"避开逆势放量大红"）
  R7 涨停后缩量阴   前日涨停 且 今日收阴 且 量比<0.8（"涨停后阴线：缩量不破"）

对照基准 = 全样本同期均值/胜率。收益从 T 日收盘算起（T+1 可买入）。
"""
import argparse
import sqlite3
import sys

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
    df["pc"] = g["close"].pct_change()                       # T 日涨跌幅
    df["prev_close"] = g["close"].shift(1)
    # 后续收益（T 日收盘买入 → T+n 收盘）
    for n in (1, 3, 5, 10):
        df["f%d" % n] = g["close"].shift(-n) / df["close"] - 1

    # 量比 = T 日量 / 前 5 日均量（组内、不含 T 日）
    df["vr"] = g["volume"].transform(
        lambda s: s / s.rolling(5).mean().shift(1).replace(0, np.nan))

    # 位置：T-1 收盘 距 20 日最高（用 T-1 及以前）
    df["hi20"] = g["high"].transform(lambda s: s.rolling(20).max().shift(1))
    df["dist_hi"] = df["prev_close"] / df["hi20"] - 1

    # 5 日振幅均值（相对前收）
    df["amp1"] = (df["high"] - df["low"]) / df["prev_close"]
    df["amp5"] = g["amp1"].transform(lambda s: s.rolling(5).mean().shift(1))

    # 涨停（按板块阈值）
    lim = np.where(df["code"].str.startswith(("300", "301", "688")), 0.195, 0.095)
    df["is_zt"] = df["pc"] > lim
    df["prev_zt"] = g["is_zt"].shift(1)

    # 大盘代理 = 当日全市场涨跌幅中位数
    mkt = df.groupby("day")["pc"].median().rename("mkt")
    df = df.join(mkt, on="day")

    # 清洗
    m = (df["pc"].abs() < 0.21) & df["vr"].notna()
    return df[m].copy()


def report(df, name, mask):
    s = df[mask]
    base = df
    if len(s) < 200:
        print("  %-18s 样本不足(%d)" % (name, len(s)))
        return None
    row = {"rule": name, "n": len(s), "占比%": len(s) / len(base) * 100}
    for n in (1, 3, 5, 10):
        col = "f%d" % n
        row["f%d%%" % n] = s[col].mean() * 100
        row["w%d%%" % n] = (s[col] > 0).mean() * 100
    print("  %-18s n=%7d (%4.1f%%)  " % (name, len(s), row["占比%"])
          + "  ".join("f%d=%+.2f%%/w%.0f%%" % (n, row["f%d%%" % n], row["w%d%%" % n])
                      for n in (1, 3, 5, 10)))
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--start", default=DEFAULT_START)
    a = ap.parse_args()
    pd.set_option("display.width", 240, "display.max_columns", 40)

    raw = load(a.db, a.start)
    print("原始 %s 行 / %d 只" % (f"{len(raw):,}", raw.code.nunique()))
    df = build(raw)
    print("清洗后 %s 行 / %d 只 / %s ~ %s\n" % (f"{len(df):,}", df.code.nunique(),
                                               df.day.min(), df.day.max()))

    print("=" * 118)
    print("【基准】全样本（T 收盘买入，持有 n 日）")
    print("=" * 118)
    base = {"rule": "全样本基准", "n": len(df)}
    print("  %-18s n=%7d          " % ("全样本基准", len(df))
          + "  ".join("f%d=%+.2f%%/w%.0f%%" % (n, df["f%d" % n].mean() * 100,
                                               (df["f%d" % n] > 0).mean() * 100)
                      for n in (1, 3, 5, 10)))

    print("\n" + "=" * 118)
    print("【规则验证】")
    print("=" * 118)
    rows = []
    checks = [
        ("R1 缩量上涨", (df.pc > 0) & (df.vr < 1)),
        ("R1b 放量上涨(对照)", (df.pc > 0) & (df.vr > 2)),
        ("R2 放量大阳", (df.pc > 0.05) & (df.vr > 2)),
        ("R2b 缩量大阳(对照)", (df.pc > 0.05) & (df.vr < 1)),
        ("R3 高位放量滞涨", (df.dist_hi > -0.05) & (df.vr > 2) & (df.pc.abs() < 0.01)),
        ("R4 低位缩量横盘", (df.dist_hi < -0.20) & (df.vr < 0.7) & (df.amp5 < 0.03)),
        ("R5 暴跌日缩量", (df.mkt < -0.01) & (df.pc < 0) & (df.vr < 0.7)),
        ("R5b 暴跌日放量(对照)", (df.mkt < -0.01) & (df.pc < 0) & (df.vr > 2)),
        ("R6 逆势放量红", (df.mkt < -0.01) & (df.pc > 0.02) & (df.vr > 2)),
        ("R7 涨停后缩量阴", df.prev_zt.fillna(False) & (df.pc < 0) & (df.vr < 0.8)),
        ("R7b 涨停后放量阴(对照)", df.prev_zt.fillna(False) & (df.pc < 0) & (df.vr > 2)),
        ("R8 突破20日高+缩量", (df.prev_close > df.hi20) & (df.vr < 1)),
        ("R9 高位缩量横盘", (df.dist_hi > -0.05) & (df.vr < 0.7) & (df.amp5 < 0.03)),
    ]
    for name, mask in checks:
        r = report(df, name, mask.fillna(False))
        if r:
            rows.append(r)

    out = pd.DataFrame(rows)
    print("\n" + "=" * 118)
    print("【汇总表】")
    print("=" * 118)
    print(out.round(2).to_string(index=False))
    out.to_csv("data/xlnn_quant_result.csv", index=False, encoding="utf-8-sig")
    print("\n已存 data/xlnn_quant_result.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
