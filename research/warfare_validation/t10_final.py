# -*- coding: utf-8 -*-
"""最终候选: 涨停隔夜(打板) 可成交子集 + 大盘/情绪门控 —— 真实净值与分年度
口径: 涨停日以涨停价买入, 次日开盘卖出, 双边成本0.15%
限定"非一字板"(盘中打开过 = 有成交机会), 并剔除买不到的一字板
"""
import numpy as np
import pandas as pd
from ev import load

P = load()
C, O, H, L, V = P["close"], P["open"], P["high"], P["low"], P["volume"]
islim, streak, newstk = P["is_limit"], P["limit_streak"], P["new_stock"]
ma20, ma60, vma5 = P["ma20"], P["ma60"], P["vma5"]
hi60, lo60 = P["hi60"], P["lo60"]
ind, ipct, ilc = P["code_ind_idx"], P["ind_pct"], P["ind_lim_count"]
days = pd.DatetimeIndex(P["days"])
n, k = C.shape
ok = (~newstk) & np.isfinite(ma20)
pos60 = np.where(hi60 > lo60, (C - lo60) / (hi60 - lo60), np.nan)
ilc_c = ilc[:, np.maximum(ind, 0)]
vr = np.where(vma5 > 0, V / vma5, np.nan)
mkt = P["mkt_pct"]
idx_eq = np.cumprod(1 + np.nan_to_num(mkt) / 100.0)
idx_ma20 = np.full_like(idx_eq, np.nan)
for i in range(20, len(idx_eq)):
    idx_ma20[i] = idx_eq[i - 20:i].mean()
above = idx_eq > idx_ma20
tot_lim = np.nansum(islim, axis=1)
COST = 0.0015
oneword = islim & (O == H) & (H == L)

FULL = {
    "① 全部涨停(含一字板, 不可全成交)": islim & ok,
    "② 非一字涨停(有成交机会)": islim & (~oneword) & ok,
    "③ 非一字 + 首板": islim & (~oneword) & (streak == 1) & ok,
    "④ 非一字 + 首板 + 量不过大(<3x)": islim & (~oneword) & (streak == 1) & (vr < 3) & ok,
    "⑤ ④ + 板块有联动(≥2只涨停)": islim & (~oneword) & (streak == 1) & (vr < 3) & (ilc_c >= 2) & ok,
    "⑥ ④ + 大盘在MA20上方": islim & (~oneword) & (streak == 1) & (vr < 3) & ok,
}
GATES = {
    "⑥": above,
    "⑥+情绪(涨停家数30~110)": above & (tot_lim >= 30) & (tot_lim <= 110),
}


def sim(mask, gate=None):
    eq = [1.0]; ns = []
    for t in range(60, n - 1):
        if gate is not None and not gate[t]:
            eq.append(eq[-1]); ns.append(0); continue
        m = mask[t] & np.isfinite(P["nxt_open"][t])
        idxs = np.where(m)[0]
        if len(idxs) == 0:
            eq.append(eq[-1]); ns.append(0); continue
        r = np.nanmean(P["nxt_open"][t, idxs] / C[t, idxs] - 1) - COST
        eq.append(eq[-1] * (1 + r)); ns.append(len(idxs))
    eq = np.array(eq); r = np.diff(eq) / eq[:-1]
    peak = np.maximum.accumulate(eq)
    yrs = len(r) / 244
    return dict(total=(eq[-1] - 1) * 100, cagr=(eq[-1] ** (1 / max(yrs, 1e-9)) - 1) * 100,
                mdd=np.min((eq - peak) / peak) * 100, win=np.mean(r > 0) * 100,
                avg=np.mean(r) * 100, ns=np.mean(ns)), eq


print("=" * 108)
print("【最终候选·涨停隔夜】买=当日收盘(涨停价), 卖=次日开盘, 成本0.15%, 全期逐日, 等权全部信号")
print("=" * 108)
print("| 方案 | 累计收益 | 年化 | 最大回撤 | 日胜率% | 日均单笔% | 平均买入只数/日 |")
print("|---|---|---|---|---|---|---|")
curves = {}
for name, mask in FULL.items():
    m, eq = sim(mask)
    curves[name] = eq
    print(f"| {name} | {m['total']:+.0f}% | {m['cagr']:+.0f}% | {m['mdd']:.1f}% | {m['win']:.1f} | {m['avg']:+.2f} | {m['ns']:.1f} |")
for gn, gate in GATES.items():
    m, eq = sim(FULL["④ 非一字 + 首板 + 量不过大(<3x)"], gate=gate)
    curves["④+" + gn] = eq
    print(f"| ④ + 择时[{gn}] | {m['total']:+.0f}% | {m['cagr']:+.0f}% | {m['mdd']:.1f}% | {m['win']:.1f} | {m['avg']:+.2f} | {m['ns']:.1f} |")

print("\n【分年度】同一口径, 逐年累计收益% (括号=最大回撤%)")
print("| 方案 | 2025 | 2026 |")
print("|---|---|---|")
yr = days.year.to_numpy()
for name in ["② 非一字涨停(有成交机会)", "③ 非一字 + 首板", "④ 非一字 + 首板 + 量不过大(<3x)"]:
    cells = []
    for y in (2025, 2026):
        i = np.where(yr == y)[0]
        eq = [1.0]
        for t in range(max(60, i[0]), i[-1] - 1):
            mm = FULL[name][t] & np.isfinite(P["nxt_open"][t])
            idxs = np.where(mm)[0]
            r = (np.nanmean(P["nxt_open"][t, idxs] / C[t, idxs] - 1) - COST) if len(idxs) else 0.0
            eq.append(eq[-1] * (1 + r))
        eq = np.array(eq); peak = np.maximum.accumulate(eq)
        cells.append(f"{(eq[-1]-1)*100:+.0f}%({np.min((eq-peak)/peak)*100:.0f}%)")
    print(f"| {name} | {cells[0]} | {cells[1]} |")

print("\n【现实约束量化】")
mm = islim & ok & np.isfinite(P["nxt_open"])
print(f"  全部涨停样本 {mm.sum():,}; 其中一字板(买不到) {np.sum(mm & oneword):,} "
      f"({np.sum(mm & oneword)/mm.sum()*100:.1f}%)")
print(f"  非一字(有成交机会)占比 {np.sum(mm & ~oneword)/mm.sum()*100:.1f}%")
f_bad = (~islim) & (P['pct'] >= 7) & (P['pct'] < 9.5) & ok
print(f"  参考: 收盘涨7~9.5%但未封板的(含打板失败/炸板的近似)次日跳空均值 "
      f"{np.nanmean((P['nxt_open'][f_bad]/C[f_bad]-1)*100):+.2f}%,  n={f_bad.sum():,}")
print(f"  若假设 30% 打板日最终炸板(按上述口径), 期望值 ≈ "
      f"{0.7*np.nanmean((P['nxt_open'][islim&~oneword&ok]/C[islim&~oneword&ok]-1)*100) + 0.3*np.nanmean((P['nxt_open'][f_bad]/C[f_bad]-1)*100) - COST*100:+.2f}%/笔")
