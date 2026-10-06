# -*- coding: utf-8 -*-
"""数据可信度审计: 打板隔夜的超额收益是"涨停次日溢价"还是"买不到的样本偏差"?
检查: (1) 涨跌幅分布异常   (2) 一字板(不可成交) vs 打开过的板(可成交)   (3) 中位数 vs 均值   (4) 独立数据源交叉验证
"""
import numpy as np
import pandas as pd
from ev import load

P = load()
C, O, H, L, V = P["close"], P["open"], P["high"], P["low"], P["volume"]
pct, islim, streak, newstk = P["is_limit"], P["limit_streak"], P["new_stock"], P["pct"]
days = pd.DatetimeIndex(P["days"])
n, k = C.shape
codes = P["codes"]
gap = np.full_like(C, np.nan); gap[:-1] = (P["nxt_open"][:-1] / C[:-1] - 1) * 100

print("【审计1】涨跌幅分布是否正常 (主板代码应为 ≤10% 左右, 前复权可能有噪声)")
main = np.array([c.startswith(("60", "00")) for c in codes])
big = pct > 11.0
print(f"  主板样本 {main.sum()} 只; 主板中出现涨幅>11%的观测: {np.sum(big[:, main]):,} "
      f"({np.sum(big[:, main])/np.sum(np.isfinite(pct[:, main]))*100:.3f}%)")
rows = np.where(big[:, main].any(axis=1))[0]
print(f"  涉及交易日: {len(rows)} 天, 例: {[str(days[i].date()) for i in rows[:5]]}")
if len(rows):
    i = rows[0]; j = np.where(big[i, main])[0][:3]
    for jj in j:
        print("    ", codes[np.where(main)[0][jj]], str(days[i].date()), "pct=", round(pct[i][np.where(main)[0][jj]], 2))

print("\n【审计2】一字板 vs 打开过的板 (决定'能不能买到')")
oneword = islim & (O == H) & (H == L) & (H == C)
opened = islim & (~oneword)
print("| 类型 | 样本 | 次日跳空均值% | 跳空中位% | 跳空>0概率% | 次日收盘均值% |")
print("|---|---|---|---|---|---|")
d1c = np.full_like(C, np.nan); d1c[:-1] = (C[1:] / C[:-1] - 1) * 100
for nm, m in [("一字板(开盘即封, 大概率买不到)", oneword),
              ("非一字(盘中打开过, 可成交)", opened),
              ("  其中: 盘中大幅打开(振幅>3%)", opened & (C > 0) & ((H - L) / C > 0.03))]:
    mm = m & np.isfinite(gap) & np.isfinite(d1c)
    if mm.sum() == 0:
        continue
    print(f"| {nm} | {mm.sum():,} | {np.nanmean(gap[mm]):+.2f} | {np.nanmedian(gap[mm]):+.2f} | "
          f"{np.nanmean(gap[mm] > 0)*100:.1f} | {np.nanmean(d1c[mm]):+.2f} |")

print("\n【审计3】均值 vs 中位数 (右尾是否由不可买的强势板贡献)")
for nm, m in [("全部涨停", islim), ("首板", islim & (streak == 1)), ("≥3连板", islim & (streak >= 3))]:
    mm = m & np.isfinite(gap)
    q = np.nanpercentile(gap[mm], [5, 25, 50, 75, 90, 99])
    print(f"  {nm}: 均值{np.nanmean(gap[mm]):+.2f}% 中位{np.nanmedian(gap[mm]):+.2f}% "
          f"分位[5/25/50/75/90/99]=" + "/".join(f"{x:+.1f}" for x in q))

print("\n【审计4】独立数据源交叉验证 (hunter.db 30分钟K, 抽10个涨停样本核对跳空)")
import sqlite3
con = sqlite3.connect(r"D:/Hermes Agent CN Desktop/hunter-v2/data/hunter.db")
rng = np.random.default_rng(7)
cand = np.where(islim & (streak == 1) & np.isfinite(gap))
pick = rng.choice(len(cand[0]), 10, replace=False)
print("| 代码 | 涨停日 | 面板收盘(qfq) | 面板次日开盘(qfq) | 面板跳空% | 30min首根开盘 | 30min前日最后收 | 30min跳空% |")
print("|---|---|---|---|---|---|---|---|")
ok_cnt = 0
for p in pick:
    t, j = cand[0][p], cand[1][p]
    code, d = codes[j], pd.Timestamp(days[t])
    if t + 1 >= n:
        continue
    d2 = pd.Timestamp(days[t + 1])
    rows_ = con.execute("select date,open,close from kline_30min where code=? and date>=? and date<=? order by date",
                        (code, str(d.date()) + " 09:00", str(d2.date()) + " 16:00")).fetchall()
    if not rows_:
        continue
    prev_close = None; next_open = None
    for r_ in rows_:
        if r_[0].startswith(str(d.date())):
            prev_close = r_[2]
        elif r_[0].startswith(str(d2.date())) and next_open is None:
            next_open = r_[1]
    if prev_close is None or next_open is None:
        continue
    g_panel = (P["nxt_open"][t, j] / C[t, j] - 1) * 100
    g_30 = (next_open / prev_close - 1) * 100
    ok_cnt += 1
    print(f"| {code} | {d.date()} | {C[t,j]:.2f} | {P['nxt_open'][t,j]:.2f} | {g_panel:+.2f} | {next_open:.2f} | {prev_close:.2f} | {g_30:+.2f} |")
print(f"  核对样本数: {ok_cnt}")
con.close()
