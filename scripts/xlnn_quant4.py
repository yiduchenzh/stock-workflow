# -*- coding: utf-8 -*-
"""小龙女方法论 · 第二批量化验证（炸板 + 次新）

A. 炸板分辨（第11期）：她说"被动卖=洗盘(后面有拉升机会) / 主动卖=出货(危险)"
   日K可量化近似：T 日 high 触及涨停价 且 close 未封（炸板）
     · 缩量炸板(vr<0.8)  → 对应"被动卖/洗盘"     预期：后续较好
     · 放量炸板(vr>2)    → 对应"主动卖/出货"     预期：后续较差
   对照：封住涨停（close≈涨停价）

B. 次新摘C（第4期）：她说"前5天涨跌幅不受限，第6天恢复，机构才被允许进场"
   ⚠️ 数据限制：factor_panel.db 起始 2025-03，无法获得真实上市日；
      本脚本用"库内首根K线"近似上市日 → 只对 2025-03 之后入库的新股有效，
      样本有偏，结论仅作方向参考。
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
    df["prev_close"] = g["close"].shift(1)
    df["pc"] = df["close"] / df["prev_close"] - 1
    for n in (1, 2, 3, 5):
        df["f%d" % n] = g["close"].shift(-n) / df["close"] - 1
    df["gap1"] = g["open"].shift(-1) / df["close"] - 1          # 次日开盘跳空
    df["vr"] = g["volume"].transform(lambda s: s / s.rolling(5).mean().shift(1).replace(0, np.nan))
    df["bar_i"] = g.cumcount()                                   # 库内第几根（近似上市天数）
    # 涨停价（按板块，四舍五入到分）
    lim = np.where(df["code"].str.startswith(("300", "301", "688")), 0.20, 0.10)
    df["lim"] = lim
    df["zt_price"] = (df["prev_close"] * (1 + df["lim"])).round(2)
    df["touch_zt"] = df["high"] >= df["zt_price"] - 1e-6
    df["close_zt"] = df["close"] >= df["zt_price"] - 1e-6
    m = (df["pc"].abs() < 0.25) & df["vr"].notna() & df["prev_close"].notna()
    return df[m].copy()


def rep(df, name, mask, minn=100):
    s = df[mask.fillna(False)]
    if len(s) < minn:
        print("  %-24s 样本不足(%d)" % (name, len(s)))
        return
    cells = []
    for n in (1, 2, 3, 5):
        c = "f%d" % n
        cells.append("f%d=%+6.2f%%/w%5.1f%%" % (n, s[c].mean() * 100, (s[c] > 0).mean() * 100))
    print("  %-24s n=%6d  gap1=%+5.2f%%  %s" % (name, len(s), s.gap1.mean() * 100, "  ".join(cells)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--start", default=DEFAULT_START)
    a = ap.parse_args()
    pd.set_option("display.width", 260)

    df = build(load(a.db, a.start))
    print("样本 %s 行 / %d 只 / %s ~ %s" % (f"{len(df):,}", df.code.nunique(),
                                           df.day.min(), df.day.max()))
    print("基准: " + "  ".join("f%d=%+.2f%%/w%.1f%%" % (n, df["f%d" % n].mean() * 100,
                                                       (df["f%d" % n] > 0).mean() * 100)
                               for n in (1, 2, 3, 5)))

    print("\n" + "=" * 116)
    print("【A. 炸板分辨】炸板 = 当日触及涨停价但收盘未封住")
    print("=" * 116)
    brd = df[df.touch_zt & ~df.close_zt]
    print("  炸板总数 = %d（占涨停触及 %.1f%%）\n" % (len(brd),
                                                len(brd) / max(1, df.touch_zt.sum()) * 100))
    rep(df, "A0 炸板(全部)", df.touch_zt & ~df.close_zt)
    rep(df, "A1 缩量炸板 vr<0.8", df.touch_zt & ~df.close_zt & (df.vr < 0.8))
    rep(df, "A2 中性 vr0.8-2", df.touch_zt & ~df.close_zt & (df.vr >= 0.8) & (df.vr <= 2))
    rep(df, "A3 放量炸板 vr>2", df.touch_zt & ~df.close_zt & (df.vr > 2))
    rep(df, "A4 巨量炸板 vr>5", df.touch_zt & ~df.close_zt & (df.vr > 5))
    print("  --- 对照：封住涨停 ---")
    rep(df, "A5 封住涨停(全部)", df.close_zt)
    rep(df, "A6 缩量封板 vr<0.8", df.close_zt & (df.vr < 0.8))
    rep(df, "A7 放量封板 vr>2", df.close_zt & (df.vr > 2))

    print("\n" + "=" * 116)
    print("【B. 次新（库内天数近似，样本有偏 — 见模块 docstring）】")
    print("=" * 116)
    for lo, hi, lab in [(1, 5, "B1 上市后 1-5 日(无涨跌幅限制)"),
                        (6, 20, "B2 上市后 6-20 日(她说机构进场窗口)"),
                        (21, 60, "B3 上市后 21-60 日"),
                        (61, 250, "B4 上市后 61-250 日")]:
        rep(df, lab, (df.bar_i >= lo) & (df.bar_i <= hi), minn=50)

    print("\n  --- 次新 6-20 日 分层：不破线/缩量住/放量站 ---")
    nn = (df.bar_i >= 6) & (df.bar_i <= 20)
    rep(df, "B2a 缩量(vr<0.8)", nn & (df.vr < 0.8))
    rep(df, "B2b 放量(vr>2)", nn & (df.vr > 2))
    rep(df, "B2c 缩量且收阳", nn & (df.vr < 0.8) & (df.pc > 0))
    rep(df, "B2d 放量且收阳", nn & (df.vr > 2) & (df.pc > 0))
    print("\n  --- 次新 21-60 日 分层 ---")
    nm = (df.bar_i >= 21) & (df.bar_i <= 60)
    rep(df, "B3a 缩量(vr<0.8)", nm & (df.vr < 0.8))
    rep(df, "B3b 放量(vr>2)", nm & (df.vr > 2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
