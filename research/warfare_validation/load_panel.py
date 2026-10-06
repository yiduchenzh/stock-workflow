# -*- coding: utf-8 -*-
"""
战法文章验证 — 面板数据构建 (真实数据, 无未来函数)
数据源: hunter-v2/data/factor_panel.db (tx_qfq 日K, 5539只, 2025-03-06 ~ 2026-09-14)
输出: panel.pkl  (dict of wide matrices: index=day, columns=code)
"""
import sqlite3, json, pickle, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

HUNTER = Path(r"D:/Hermes Agent CN Desktop/hunter-v2")
DB = HUNTER / "data" / "factor_panel.db"
SECTOR = HUNTER / "cache" / "sector_map.json"
OUT = Path(__file__).parent / "panel.pkl"


def main():
    t0 = time.time()
    con = sqlite3.connect(DB)
    df = pd.read_sql(
        "select code,day,open,high,low,close,volume from kline_daily order by day,code", con)
    con.close()
    df["day"] = pd.to_datetime(df["day"])
    print(f"[load] {len(df)} rows, {df.code.nunique()} codes, {df.day.min().date()}~{df.day.max().date()} "
          f"({time.time()-t0:.1f}s)")

    def wide(col):
        return df.pivot(index="day", columns="code", values=col).sort_index()

    O, H, L, C, V = (wide(c).astype("float64") for c in ["open", "high", "low", "close", "volume"])
    idx, codes = C.index, C.columns
    n = len(idx)
    print(f"[pivot] {n} days x {len(codes)} codes  ({time.time()-t0:.1f}s)")

    P = {}
    P["open"], P["high"], P["low"], P["close"], P["volume"] = (
        O.to_numpy(), H.to_numpy(), L.to_numpy(), C.to_numpy(), V.to_numpy())
    P["days"] = idx.to_numpy()
    P["codes"] = codes.to_numpy()
    P["industry"] = np.array([json.load(open(SECTOR, encoding="utf-8")).get(c, "") if False else ""
                              for c in codes])  # placeholder, filled below

    sm = json.load(open(SECTOR, encoding="utf-8"))
    P["industry"] = np.array([sm.get(c, "") for c in codes], dtype=object)

    # ---------- 基础特征 (全部仅用 t 及之前数据) ----------
    cl = C
    P["prev_close"] = cl.shift(1).to_numpy()
    P["pct"] = (cl / cl.shift(1) - 1).to_numpy() * 100.0                  # 涨跌幅 %
    P["ma5"] = cl.rolling(5).mean().to_numpy()
    P["ma10"] = cl.rolling(10).mean().to_numpy()
    P["ma20"] = cl.rolling(20).mean().to_numpy()
    P["ma60"] = cl.rolling(60).mean().to_numpy()
    P["ma60_prev5"] = cl.rolling(60).mean().shift(5).to_numpy()
    P["vma5"] = V.rolling(5).mean().to_numpy()
    P["vma20"] = V.rolling(20).mean().to_numpy()
    P["vol_ratio"] = (V / V.rolling(5).mean()).to_numpy()                # 量比(对5日均量)
    P["hi20"] = H.rolling(20).max().to_numpy()
    P["lo20"] = L.rolling(20).min().to_numpy()
    P["hi60"] = H.rolling(60).max().to_numpy()
    P["lo60"] = L.rolling(60).min().to_numpy()
    P["bar_pos"] = ((cl - L) / (H - L).replace(0, np.nan)).to_numpy()     # 收盘在当日振幅位置 0~1
    P["gap"] = (O / cl.shift(1) - 1).to_numpy() * 100.0                   # 竞价高开 %
    P["new_stock"] = cl.notna().cumsum().le(60).to_numpy()                # 上市<60日

    # 涨停判定: 主板10%(60/00) 创业板/科创20%(30/68)
    code_s = pd.Series(codes, index=codes)
    lim = code_s.str.startswith(("30", "68")).map({True: 19.5, False: 9.5}).to_numpy()
    P["limit_thr"] = lim
    pct = P["pct"]
    P["is_limit"] = (pct >= lim[None, :]) & (cl.notna().to_numpy())
    # 连板数 (截至当日连续涨停数, 纯numpy逐日递推)
    islim = P["is_limit"]
    streak = np.zeros(islim.shape, dtype=np.int16)
    run = np.zeros(islim.shape[1], dtype=np.int16)
    for t in range(n):
        run = np.where(islim[t], run + 1, 0)
        streak[t] = run
    P["limit_streak"] = streak

    # ---------- 未来收益 (仅用于评估, 不参与信号) ----------
    for h in (1, 2, 3, 5, 10, 20):
        P[f"fwd{h}"] = (cl.shift(-h) / cl - 1).to_numpy() * 100.0          # 今收→h日后收
    P["nxt_open"] = O.shift(-1).to_numpy()
    P["nxt_close"] = cl.shift(-1).to_numpy()
    P["nxt_high"] = H.shift(-1).to_numpy()
    P["nxt_low"] = L.shift(-1).to_numpy()
    P["t1_oc"] = (cl.shift(-1) / O.shift(-1) - 1).to_numpy() * 100.0        # 次日 开→收
    P["t1_oc2"] = (cl.shift(-2) / O.shift(-1) - 1).to_numpy() * 100.0       # 次日开→第3日收
    P["hi_next5"] = (H.shift(-1).rolling(5).max() / cl - 1).to_numpy() * 100.0
    P["hi_next10"] = (H.shift(-1).rolling(10).max() / cl - 1).to_numpy() * 100.0
    P["lo_next5"] = (L.shift(-1).rolling(5).min() / cl - 1).to_numpy() * 100.0

    # 市场环境 (等权全市场当日涨跌, 作为"大盘"代理)
    P["mkt_pct"] = np.nanmean(np.where(np.isfinite(pct), pct, np.nan), axis=1)

    # 板块: 每日行业涨停家数 / 行业平均涨幅 / 行业成员数
    ind = P["industry"]
    inds = sorted({i for i in ind if i})
    lim_count = np.full((n, len(inds)), np.nan)
    ind_pct = np.full((n, len(inds)), np.nan)
    limf = P["is_limit"] * 1.0
    for j, name in enumerate(inds):
        m = ind == name
        lim_count[:, j] = np.nansum(limf[:, m], axis=1)
        ind_pct[:, j] = np.nanmean(pct[:, m], axis=1)
    P["ind_names"] = np.array(inds, dtype=object)
    P["ind_lim_count"] = lim_count
    P["ind_pct"] = ind_pct
    name2j = {n: j for j, n in enumerate(inds)}
    P["code_ind_idx"] = np.array([name2j.get(sm.get(c, ""), -1) for c in codes])

    with open(OUT, "wb") as f:
        pickle.dump({k: v for k, v in P.items()}, f, protocol=4)
    print(f"[done] {OUT}  ({OUT.stat().st_size/1e6:.1f} MB, {time.time()-t0:.1f}s)")
    print("行业中位数覆盖:", np.mean([1 if x else 0 for x in ind]))


if __name__ == "__main__":
    main()
