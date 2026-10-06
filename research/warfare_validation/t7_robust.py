# -*- coding: utf-8 -*-
"""稳健性检查: (1) 采样网格敏感性 step=3/5/7/10  (2) 分年度  (3) 逐笔全样本超额
结论口径: 若某战法在不同采样网格/不同年份下方向一致 → 稳健; 否则=噪声/拟合
"""
import numpy as np
import pandas as pd
from ev import load

P = load()
C, O, H, L, V = P["close"], P["open"], P["high"], P["low"], P["volume"]
pct, islim, newstk, streak = P["pct"], P["is_limit"], P["new_stock"], P["limit_streak"]
ma5, ma10, ma20, ma60, vma5, vma20 = P["ma5"], P["ma10"], P["ma20"], P["ma60"], P["vma5"], P["vma20"]
hi20, hi60, lo60, bar_pos = P["hi20"], P["hi60"], P["lo60"], P["bar_pos"]
ind, ipct, ilc = P["code_ind_idx"], P["ind_pct"], P["ind_lim_count"]
days = pd.DatetimeIndex(P["days"])
n, k = C.shape
years = days.year.to_numpy()
ok = (~newstk) & np.isfinite(ma20) & np.isfinite(ma60)
vr = np.where(vma5 > 0, V / vma5, np.nan)
pos60 = np.where(hi60 > lo60, (C - lo60) / (hi60 - lo60), np.nan)
ret20 = np.full_like(C, np.nan); ret20[20:] = (C[20:] / C[:-20] - 1) * 100
ipct_c = ipct[:, np.maximum(ind, 0)]; ilc_c = ilc[:, np.maximum(ind, 0)]
hi20_prev = np.full_like(H, np.nan); hi20_prev[1:] = hi20[:-1]
mkt = P["mkt_pct"]
idx_eq = np.cumprod(1 + np.nan_to_num(mkt) / 100.0)
idx_ma20 = np.full_like(idx_eq, np.nan)
for i in range(20, len(idx_eq)):
    idx_ma20[i] = idx_eq[i - 20:i].mean()
above = idx_eq > idx_ma20
COST = 0.0015

S = {
    "全市场等权": ok,
    "三招合一(文章G)": ok & (C > ma60) & (ma60 > np.nan_to_num(np.roll(ma60, 5, axis=0))) & (ma20 > ma60) & (ma5 > ma20) & (C > O) & (V > vma5),
    "裸突破20日高+量1.5x": ok & (C > hi20_prev) & (V > vma5 * 1.5),
    "突破+不追高(分位<0.7)": ok & (C > hi20_prev) & (V > vma5 * 1.5) & (pos60 < 0.7),
    "突破+板块共振": ok & (C > hi20_prev) & (V > vma5 * 1.5) & (ilc_c >= 1) & (ipct_c > 1),
    "突破+3条均线之上": ok & (C > hi20_prev) & (V > vma5 * 1.5) & (C > ma5) & (C > ma20) & (C > ma60),
    "尾盘战法全条件(文章H)": ok & (pct >= 2) & (pct <= 5) & (vr >= 1.2) & (C > ma5) & (C > ma10) & (C > ma20) & (bar_pos >= 0.7) & (pos60 < 0.8) & (ilc_c >= 1) & (ipct_c > 1),
    "首板(涨停)": ok & islim & (streak == 1),
    "低位首板": ok & islim & (streak == 1) & (pos60 < 0.35),
    "强势未封板7~9.5%": ok & (pct >= 7) & (pct < 9.5) & (V > vma5),
    "回调缩量(文章B)": ok & (ret20 >= 15) & (pct < 5) & (V < vma20 * 0.8) & (C > ma20) & (C > ma60) & (ma20 > ma60),
}


def sim(mask, step, lo=60, hi=None, gate=None):
    hi = hi or n - step - 1
    eq = [1.0]; per = []
    for t0 in range(lo, hi, step):
        if gate is not None and not gate[t0]:
            per.append(0.0); eq.append(eq[-1]); continue
        m = mask[t0] & np.isfinite(O[t0 + 1]) & np.isfinite(C[t0 + step])
        idxs = np.where(m)[0]
        if len(idxs) == 0:
            per.append(0.0); eq.append(eq[-1]); continue
        r = np.nanmean(C[t0 + step, idxs] / O[t0 + 1, idxs] - 1) - COST
        per.append(r); eq.append(eq[-1] * (1 + r))
    return np.array(eq), np.array(per)


def key(eq):
    r = np.diff(eq) / eq[:-1]
    peak = np.maximum.accumulate(eq)
    return (eq[-1] - 1) * 100, np.min((eq - peak) / peak) * 100, np.mean(r > 0) * 100


print("=" * 118)
print("【稳健性1】采样网格敏感性: 每N交易日调仓一次, 同一战法在不同N下的累计收益%(括号=最大回撤%)")
print("=" * 118)
print("| 战法 | N=3 | N=5 | N=7 | N=10 | 全期逐笔超额% |")
print("|---|---|---|---|---|---|")
# 逐笔超额 (全样本, 次日开→持5日)
r5o = np.full_like(C, np.nan); r5o[:-6] = (C[6:] / O[1:-5] - 1) * 100
dm = np.nanmean(np.where(np.isfinite(r5o), r5o, np.nan), axis=1)
for name, mask in S.items():
    cells = []
    for step in (3, 5, 7, 10):
        eq, per = sim(mask, step)
        tot, mdd, win = key(eq)
        cells.append(f"{tot:+.0f}%({mdd:.0f}%)")
    m = np.roll(mask, 1, axis=0) & ok & np.isfinite(r5o)
    exc = np.nanmean(r5o[m] - dm[np.where(m)[0]]) if m.sum() else np.nan
    print(f"| {name} | " + " | ".join(cells) + f" | {exc:+.2f} |")

print("\n【稳健性2】分年度 (每5交易日调仓, 累计收益%)")
print("| 战法 | 2025(6月起) | 2026 | 加择时(大盘MA20上方才做) 全期 |")
print("|---|---|---|---|")
for name, mask in S.items():
    i25 = np.where(years == 2025)[0]
    i26 = np.where(years == 2026)[0]
    eq25, _ = sim(mask, 5, lo=max(60, i25[0]), hi=i25[-1] - 6)
    eq26, _ = sim(mask, 5, lo=i26[0], hi=i26[-1] - 6)
    eqg, _ = sim(mask, 5, gate=above)
    t25, m25, _ = key(eq25); t26, m26, _ = key(eq26); tg, mg, wg = key(eqg)
    print(f"| {name} | {t25:+.1f}% | {t26:+.1f}% | {tg:+.1f}% (回撤{mg:.1f}%, 期胜率{wg:.0f}%) |")

print("\n【稳健性3】最优候选的年度明细: 裸突破20日高+量1.5x + 大盘MA20择时")
mask = S["裸突破20日高+量1.5x"]
for y in (2025, 2026):
    idx = np.where(years == y)[0]
    eq, per = sim(mask, 5, lo=max(60, idx[0]), hi=idx[-1] - 6)
    tot, mdd, win = key(eq)
    eq2 = [1.0]
    for i, t0 in enumerate(range(max(60, idx[0]), idx[-1] - 6, 5)):
        eq2.append(eq2[-1] * (1 + (per[i] if above[t0] else 0.0)))
    t2, m2, w2 = key(np.array(eq2))
    print(f"  {y}: 不做择时 {tot:+.1f}%(回撤{mdd:.1f}%) | 加择时 {t2:+.1f}%(回撤{m2:.1f}% 期胜率{w2:.0f}%)")

print("\n【稳健性4】信号后5日的'冲高机会' (次日最高价) — 对'次日冲高卖出'类打法的检验")
nxt_hi = np.full_like(C, np.nan); nxt_hi[:-1] = (P["nxt_high"][:-1] / C[:-1] - 1) * 100
print("| 战法 | 次日最高均值% | 次日最高>3%概率% | 次日收盘均值% |")
print("|---|---|---|---|")
nxt_cl = np.full_like(C, np.nan); nxt_cl[:-1] = (P["nxt_close"][:-1] / C[:-1] - 1) * 100
for name, mask in S.items():
    m = mask & ok & np.isfinite(nxt_hi)
    if m.sum() == 0:
        continue
    print(f"| {name} | {np.nanmean(nxt_hi[m]):+.2f} | {np.nanmean(nxt_hi[m] > 3)*100:.1f} | {np.nanmean(nxt_cl[m]):+.2f} |")
