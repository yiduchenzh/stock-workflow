# -*- coding: utf-8 -*-
"""【涨停隔夜溢价】专项: 数据支持的唯一显著规律 + 真实可交易性检验
口径: 涨停日以涨停价(收盘价)买入 → 次日卖出。买入成交率是现实约束(见报告)。
"""
import numpy as np
import pandas as pd
from ev import load

P = load()
C, O, H, L, V = P["close"], P["open"], P["high"], P["low"], P["volume"]
pct, islim, streak, newstk = P["pct"], P["is_limit"], P["limit_streak"], P["new_stock"]
ma20, ma60, vma5 = P["ma20"], P["ma60"], P["vma5"]
hi60, lo60 = P["hi60"], P["lo60"]
ind, ipct, ilc = P["code_ind_idx"], P["ind_pct"], P["ind_lim_count"]
days = pd.DatetimeIndex(P["days"])
n, k = C.shape
ok = (~newstk) & np.isfinite(ma20)
pos60 = np.where(hi60 > lo60, (C - lo60) / (hi60 - lo60), np.nan)
ilc_c = ilc[:, np.maximum(ind, 0)]; ipct_c = ipct[:, np.maximum(ind, 0)]
vr = np.where(vma5 > 0, V / vma5, np.nan)

gap = np.full_like(C, np.nan); gap[:-1] = (P["nxt_open"][:-1] / C[:-1] - 1) * 100
d1c = np.full_like(C, np.nan); d1c[:-1] = (P["nxt_close"][:-1] / C[:-1] - 1) * 100
d1h = np.full_like(C, np.nan); d1h[:-1] = (P["nxt_high"][:-1] / C[:-1] - 1) * 100


def rep(name, m):
    m = m & ok & np.isfinite(gap)
    if m.sum() == 0:
        return f"| {name} | 0 | - | - | - | - |"
    return (f"| {name} | {m.sum():,} | {np.nanmean(gap[m]):+.2f} | {np.nanmean(d1h[m]):+.2f} | "
            f"{np.nanmean(d1c[m]):+.2f} | {np.nanmean(gap[m] > 0)*100:.1f} |")


print("=" * 100)
print("【打板隔夜】涨停日买入(涨停价=收盘价) → 次日卖出  (n=涨停样本数)")
print("=" * 100)
print("| 分层 | 样本 | 次日跳空均值% | 次日最高均值% | 次日收盘均值% | 跳空>0概率% |")
print("|---|---|---|---|---|---|")
print(rep("全部涨停", islim))
print(rep("首板", islim & (streak == 1)))
print(rep("2连板", islim & (streak == 2)))
print(rep("3连板", islim & (streak == 3)))
print(rep("≥4连板", islim & (streak >= 4)))
print(rep("首板+低位(分位<0.35)", islim & (streak == 1) & (pos60 < 0.35)))
print(rep("首板+中位", islim & (streak == 1) & (pos60 >= 0.35) & (pos60 <= 0.7)))
print(rep("首板+高位(>0.7)", islim & (streak == 1) & (pos60 > 0.7)))
print(rep("首板+早盘即封(振幅小)", islim & (streak == 1) & ((H - L) / np.where(C > 0, C, 1) < 0.03)))
print(rep("首板+巨量(>3x5日均量)", islim & (streak == 1) & (vr > 3)))
print(rep("首板+温和量(1~2x)", islim & (streak == 1) & (vr >= 1) & (vr <= 2)))
print(rep("首板+板块≥3只涨停", islim & (streak == 1) & (ilc_c >= 3)))
print(rep("首板+板块仅1只涨停", islim & (streak == 1) & (ilc_c <= 1)))
print(rep("非涨停涨7~9.5%(未封板)", (pct >= 7) & (pct < 9.5) & (~islim) & (V > vma5)))

print("\n【打板隔夜 组合模拟】每日买入当日全部标的, 次日开盘卖出, 双边成本0.15%")
COST = 0.0015
for name, mask in [("全部涨停", islim), ("首板", islim & (streak == 1)),
                   ("首板+低位(<0.35)", islim & (streak == 1) & (pos60 < 0.35)),
                   ("首板+板块≥3只涨停", islim & (streak == 1) & (ilc_c >= 3)),
                   ("2连板", islim & (streak == 2))]:
    eq = [1.0]; ns = []
    for t in range(60, n - 1):
        m = mask[t] & ok[t] & np.isfinite(P["nxt_open"][t])
        idxs = np.where(m)[0]
        if len(idxs) == 0:
            eq.append(eq[-1]); ns.append(0); continue
        r = np.nanmean(P["nxt_open"][t, idxs] / C[t, idxs] - 1) - COST
        eq.append(eq[-1] * (1 + r)); ns.append(len(idxs))
    eq = np.array(eq); r = np.diff(eq) / eq[:-1]
    peak = np.maximum.accumulate(eq)
    yrs = len(r) / 244
    print(f"  {name}: 累计{(eq[-1]-1)*100:+.1f}% 年化{(eq[-1]**(1/yrs)-1)*100:+.1f}% "
          f"最大回撤{np.min((eq-peak)/peak)*100:.1f}% 日胜率{np.mean(r>0)*100:.1f}% 平均{np.mean(ns):.1f}只/日")

print("\n【分年度 打板隔夜 平均收益】")
yr = days.year.to_numpy()
for y in (2025, 2026):
    m = islim & ok & np.isfinite(gap) & (yr[:, None] == y)
    print(f"  {y}: 跳空均值{np.nanmean(gap[m]):+.2f}%  n={m.sum():,}")
    m2 = islim & (streak == 1) & ok & np.isfinite(gap) & (yr[:, None] == y)
    print(f"       首板: {np.nanmean(gap[m2]):+.2f}%  n={m2.sum():,}")

print("\n【涨停家数(情绪) 与 打板隔夜收益 的关系】")
tot_lim = np.nansum(islim, axis=1)
for lo, hi, nm in [(0, 30, "<30家(冰点)"), (30, 60, "30-60家"), (60, 90, "60-90家"), (90, 1e9, ">90家(亢奋)")]:
    m = islim & ok & np.isfinite(gap) & (tot_lim[:, None] >= lo) & (tot_lim[:, None] < hi)
    if m.sum() == 0:
        continue
    print(f"  {nm}: 跳空均值{np.nanmean(gap[m]):+.2f}%  次日收盘{np.nanmean(d1c[m]):+.2f}%  n={m.sum():,}")
