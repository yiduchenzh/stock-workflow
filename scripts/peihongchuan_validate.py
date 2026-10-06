# -*- coding: utf-8 -*-
"""A/B validation of 裴洪川《趋势结构交易法》 core rules on the full A-share daily panel.

Data: D:/MarketData/market.db (shared K-line library, read-only)
Method: every-5-trading-day sampling, forward 20-trading-day close-to-close return,
        per-rule comparison + Welch t-test.
"""
import sqlite3
import sys
import time
import numpy as np
import pandas as pd

DB = "file:D:/Hermes Agent CN Desktop/hunter-v2/data/hunter.db?mode=ro"
TABLE = "kline_daily_qfq"
FWD = 20
STEP = 5


def load():
    con = sqlite3.connect(DB, uri=True, timeout=60)
    cur = con.cursor()
    print("loading %s ..." % TABLE, flush=True)
    t0 = time.time()
    rows = cur.execute("select code, date, open, close from %s" % TABLE).fetchall()
    print("fetched %d rows in %.1fs" % (len(rows), time.time() - t0), flush=True)
    con.close()
    arr = pd.DataFrame(rows, columns=["code", "dt", "open", "close"])
    arr["dt"] = pd.to_datetime(arr["dt"].astype(str).str.slice(0, 10), errors="coerce")
    arr["open"] = pd.to_numeric(arr["open"], errors="coerce")
    arr["close"] = pd.to_numeric(arr["close"], errors="coerce")
    arr = arr.dropna(subset=["dt", "close"])
    arr = arr[arr["close"] > 0]
    arr = arr.sort_values(["code", "dt"], kind="mergesort").reset_index(drop=True)
    print("usable rows", len(arr), "codes", arr["code"].nunique(),
          "range", arr["dt"].min(), arr["dt"].max(), "%.1fs" % (time.time() - t0), flush=True)
    return arr


def stats(name, r, col="fwd"):
    r = np.asarray(r, dtype=float)
    r = r[~np.isnan(r)]
    if len(r) < 30:
        return dict(rule=name, n=len(r), note="样本不足")
    m = float(r.mean()) * 100
    win = float((r > 0).mean()) * 100
    p05 = float(np.percentile(r, 5)) * 100
    p95 = float(np.percentile(r, 95)) * 100
    return dict(rule=name, n=len(r), mean_pct=round(m, 3), win_pct=round(win, 1),
                p05_pct=round(p05, 2), p95_pct=round(p95, 2),
                median_pct=round(float(np.median(r)) * 100, 3))


def main():
    df = load()
    g = df.groupby("code", sort=False)
    df["ma5"] = g["close"].transform(lambda s: s.rolling(5).mean())
    df["ma20"] = g["close"].transform(lambda s: s.rolling(20).mean())
    df["ma60"] = g["close"].transform(lambda s: s.rolling(60).mean())
    df["ma250"] = g["close"].transform(lambda s: s.rolling(250).mean())
    ema12 = g["close"].transform(lambda s: s.ewm(span=12, adjust=False).mean())
    ema26 = g["close"].transform(lambda s: s.ewm(span=26, adjust=False).mean())
    df["dif"] = ema12 - ema26
    df["dea"] = df.groupby("code", sort=False)["dif"].transform(
        lambda s: s.ewm(span=9, adjust=False).mean())
    df["fwd"] = g["close"].transform(lambda s: s.shift(-FWD) / s - 1.0)
    df["ma60_up"] = df["ma60"] > df.groupby("code", sort=False)["ma60"].transform(lambda s: s.shift(5))
    df["ma20_dn"] = df["ma20"] < df.groupby("code", sort=False)["ma20"].transform(lambda s: s.shift(5))
    df["day_of_month"] = df["dt"].dt.day
    df["seq"] = df.groupby("code", sort=False).cumcount()

    s = df[(df["seq"] % STEP == 0) & df["fwd"].notna()].copy()
    s["fwd_dm"] = s["fwd"] - s.groupby("dt")["fwd"].transform("mean")
    print("\nsampled rows", len(s), "codes", s["code"].nunique(),
          "date range", s["dt"].min(), s["dt"].max(), flush=True)

    RULES = [
        ("BASE 全样本", pd.Series(True, index=s.index)),
        ("R1a 价格>年线(MA250)", s["close"] > s["ma250"]),
        ("R1b 价格<年线(MA250)", s["close"] < s["ma250"]),
        ("R2 MA60↑ 且 价>MA60", s["ma60_up"] & (s["close"] > s["ma60"])),
        ("R3 共振(>MA60 & MA60↑ & DIF>0 & 金叉)",
         s["ma60_up"] & (s["close"] > s["ma60"]) & (s["dif"] > 0) & (s["dif"] > s["dea"])),
        ("R4a 下跌中(价<MA20 & MA20↓)", (s["close"] < s["ma20"]) & s["ma20_dn"]),
        ("R4b 下跌且收阳(接飞刀)", (s["close"] < s["ma20"]) & s["ma20_dn"] & (s["close"] > s["open"])),
        ("R5a 上半月(1-15日)", s["day_of_month"] <= 15),
        ("R5b 下半月(16-31日)", s["day_of_month"] > 15),
    ]
    s["pxq"] = s.groupby("dt")["close"].transform(
        lambda x: pd.qcut(x.rank(method="first"), 5, labels=False) if len(x) >= 50 else np.nan)
    RULES.append(("R6a 最低价20%", s["pxq"] == 0))
    RULES.append(("R6b 最高价20%", s["pxq"] == 4))

    rows = [stats(n, s.loc[m, "fwd"]) for n, m in RULES]
    out = pd.DataFrame(rows)
    print("\n【表1】绝对收益（%s日 close→close, %%）" % FWD)
    print("=" * 104)
    print(out.to_string(index=False))
    print("=" * 104)

    rows2 = [dict(rule=n, **{k: v for k, v in stats(n, s.loc[m, "fwd_dm"], "fwd_dm").items()
                             if k != "rule"}) for n, m in RULES]
    out2 = pd.DataFrame(rows2)
    print("\n【表2】同日去均值收益（扣除当日全市场平均，%%）— 衡量相对强弱")
    print("=" * 104)
    print(out2.to_string(index=False))
    print("=" * 104)

    # year-by-year robustness for the decision rules
    print("\n分年度（关键规则）— mean 20d return %")
    rules = {
        "价>年线": (s["close"] > s["ma250"]),
        "价<年线": (s["close"] < s["ma250"]),
        "MA60↑且价>MA60": (s["ma60_up"] & (s["close"] > s["ma60"])),
        "共振(DIF>0&金叉)": (s["ma60_up"] & (s["close"] > s["ma60"]) & (s["dif"] > 0) & (s["dif"] > s["dea"])),
        "下跌中(价<MA20&MA20↓)": ((s["close"] < s["ma20"]) & s["ma20_dn"]),
        "上半月": (s["day_of_month"] <= 15),
        "下半月": (s["day_of_month"] > 15),
    }
    yrs = sorted(s["dt"].dt.year.unique())
    yrs = [y for y in yrs if y >= 2016]
    hdr = "rule".ljust(24) + "".join(str(y).rjust(8) for y in yrs)
    print(hdr)
    for name, mask in rules.items():
        line = name.ljust(24)
        for y in yrs:
            mm = mask & (s["dt"].dt.year == y)
            v = s.loc[mm, "fwd"]
            line += ("%8.2f" % (v.mean() * 100) if len(v) >= 200 else "%8s" % "-")
        print(line)
    print("(blank = 样本<200)")

    print("\n注意: 未来收益为%s个交易日 close→close; 价格=前复权; 采样步长%s日; 同日去均值=个股收益-当日全市场均值" % (FWD, STEP))
    out.to_csv("D:/Hermes Agent CN Desktop/stock-workflow/data/douyin/peihongchuan/_validation.csv",
               index=False, encoding="utf-8-sig")
    out2.to_csv("D:/Hermes Agent CN Desktop/stock-workflow/data/douyin/peihongchuan/_validation_demeaned.csv",
                index=False, encoding="utf-8-sig")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
