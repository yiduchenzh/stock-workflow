# -*- coding: utf-8 -*-
"""组合级模拟 v2: 消除"随机抽10只"采样噪声 — 每期用【全部信号股】等权平均
同一时间窗内比较, 并与逐笔统计对齐 (t+1开盘买 → t+5收盘卖, 双边成本0.15%)
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
ok = (~newstk) & np.isfinite(ma20) & np.isfinite(ma60)
vr = np.where(vma5 > 0, V / vma5, np.nan)
pos60 = np.where(hi60 > lo60, (C - lo60) / (hi60 - lo60), np.nan)
ret20 = np.full_like(C, np.nan); ret20[20:] = (C[20:] / C[:-20] - 1) * 100
ipct_c = ipct[:, np.maximum(ind, 0)]; ilc_c = ilc[:, np.maximum(ind, 0)]
prev_dn = np.roll(pct, 1, axis=0); prev_dn[0] = np.nan
mkt = P["mkt_pct"]
idx_eq = np.cumprod(1 + np.nan_to_num(mkt) / 100.0)
idx_ma20 = np.full_like(idx_eq, np.nan)
for i in range(20, len(idx_eq)):
    idx_ma20[i] = idx_eq[i - 20:i].mean()
above = idx_eq > idx_ma20

hi20_prev = np.full_like(H, np.nan); hi20_prev[1:] = hi20[:-1]
S = {
    "S0 全市场等权(基线)": ok,
    "S_mom 动量: 20日最强5%": ok & (ret20 >= np.nanpercentile(ret20, 95, axis=1)[:, None]),
    "S_rev 反转: 20日最弱10%+缩量": ok & (ret20 <= np.nanpercentile(ret20, 10, axis=1)[:, None]) & (V < vma20) & (C > ma20),
    "S_w2s 弱转强(昨跌>3%今放量涨>2%)": ok & (prev_dn < -3) & (pct > 2) & (V > vma5),
    "S_tail 尾盘战法全条件(文章H)": ok & (pct >= 2) & (pct <= 5) & (vr >= 1.2) & (C > ma5) & (C > ma10) & (C > ma20) \
        & (bar_pos >= 0.7) & (pos60 < 0.8) & (ilc_c >= 1) & (ipct_c > 1),
    "S_G 三招合一(文章G)": ok & (C > ma60) & (ma60 > np.nan_to_num(np.roll(ma60, 5, axis=0))) & (ma20 > ma60) & (ma5 > ma20) \
        & (C > O) & (V > vma5),
    "S_break 裸突破20日高+放量1.5x": ok & (C > hi20_prev) & (V > vma5 * 1.5),
    "S_lowlim 低位首板(分位<0.35)": ok & islim & (streak == 1) & (pos60 < 0.35),
    "S_limit1 首板(全部)": ok & islim & (streak == 1),
    "S_strong 强势未封板(7~9.5%)": ok & (pct >= 7) & (pct < 9.5) & (V > vma5),
    "S_naked 涨停(收盘买不到,理论值)": ok & islim,
}
COST = 0.0015
STEP = 5


def sim_all(mask, step=STEP, cost=COST, topn=None, score=None):
    """每期用全部信号股(或按score取前topn)等权, 返回净值序列与统计"""
    eq = [1.0]; ns = []; per = []
    for t0 in range(60, n - step - 1, step):
        m = mask[t0] & np.isfinite(O[t0 + 1]) & np.isfinite(C[t0 + step])
        idxs = np.where(m)[0]
        if topn and len(idxs) > topn:
            idxs = idxs[np.argsort(-np.nan_to_num(score[t0, idxs]))[:topn]]
        if len(idxs) == 0:
            ns.append(0); per.append(0.0); eq.append(eq[-1]); continue
        r = np.nanmean(C[t0 + step, idxs] / O[t0 + 1, idxs] - 1) - cost
        ns.append(len(idxs)); per.append(r)
        eq.append(eq[-1] * (1 + r))
    return np.array(eq), np.array(ns), np.array(per)


def met(eq):
    r = np.diff(eq) / eq[:-1]
    yrs = len(r) * STEP / 244
    peak = np.maximum.accumulate(eq)
    return dict(total=eq[-1] - 1, cagr=eq[-1] ** (1 / max(yrs, 1e-9)) - 1,
                mdd=np.min((eq - peak) / peak), win=np.mean(r > 0) * 100, avg=np.mean(r) * 100,
                n=len(r))


print("=" * 108)
print(f"组合模拟v2 (无采样噪声): 每5交易日调仓, 用当期【全部信号股】等权, 次日开盘买/第5日收盘卖")
print(f"成本 {COST*100:.2f}% / 调仓;  样本 {days[60].date()} ~ {days[-1].date()}, {len(range(60, n-6, STEP))} 期")
print("=" * 108)
print("| 战法 | 累计 | 年化 | 最大回撤 | 期胜率% | 单期均值% | 平均信号数 |")
print("|---|---|---|---|---|---|---|")
res = {}
for name, mask in S.items():
    eq, ns, per = sim_all(mask)
    m = met(eq)
    res[name] = m
    print(f"| {name} | {m['total']*100:+.1f}% | {m['cagr']*100:+.1f}% | {m['mdd']*100:.1f}% | "
          f"{m['win']:.1f} | {m['avg']:+.2f} | {ns.mean():.1f} |")

print("\n【同期等权指数基准】", f"累计 {(idx_eq[-1]/idx_eq[60]-1)*100:+.1f}%  "
      f"最大回撤 {np.min((idx_eq[60:]-np.maximum.accumulate(idx_eq[60:]))/np.maximum.accumulate(idx_eq[60:]))*100:.1f}%")

print("\n【择时版: 大盘在等权指数MA20上方才持有】")
for name in ["S0 全市场等权(基线)", "S_break 裸突破20日高+放量1.5x"]:
    eq, ns, per = sim_all(S[name])
    eq2 = [1.0]
    for i, t0 in enumerate(range(60, n - STEP - 1, STEP)):
        r = per[i] if above[t0] else 0.0
        eq2.append(eq2[-1] * (1 + r))
    m = met(np.array(eq2))
    print(f"  {name} + 择时: 累计{m['total']*100:+.1f}% 年化{m['cagr']*100:+.1f}% 回撤{m['mdd']*100:.1f}%")

print("\n【逐笔口径复核: S_break 全部信号 vs 组合口径 (排除采样噪声)】")
mask = S["S_break 裸突破20日高+放量1.5x"]
r5c = np.full_like(C, np.nan); r5c[:-5] = (C[5:] / C[:-5] - 1) * 100       # 收盘买→5日后收
r5o = np.full_like(C, np.nan); r5o[:-6] = (C[6:] / O[1:-5] - 1) * 100       # 次日开→第5日收
for nm, F, mm in [("信号日收盘买入→持5日", r5c, mask), ("次日开盘买入→持5日", r5o, np.roll(mask, 1, axis=0))]:
    m = mm & ok & np.isfinite(F)
    print(f"  {nm}: n={m.sum():,} 均值{np.mean(F[m]):+.2f}% 胜率{np.mean(F[m]>0)*100:.1f}%")
base_m = ok & np.isfinite(r5o)
print(f"  [基线] 全市场次日开买入持5日: n={base_m.sum():,} 均值{np.nanmean(r5o[base_m]):+.2f}% 胜率{np.nanmean(r5o[base_m]>0)*100:.1f}%")
