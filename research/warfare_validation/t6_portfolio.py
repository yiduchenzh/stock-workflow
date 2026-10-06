# -*- coding: utf-8 -*-
"""候选战法 组合级模拟 (真实净值): 每周调仓(5交易日), 等权持有5日, 双边成本0.15%
输出: 累计收益/年化/最大回撤/日胜率/月度胜率/调仓次数 — 用真实数据说话
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
ipct_c = ipct[:, np.maximum(ind, 0)]
ilc_c = ilc[:, np.maximum(ind, 0)]
prev_dn = np.roll(pct, 1, axis=0); prev_dn[0] = np.nan

mkt = P["mkt_pct"]
idx_eq = np.cumprod(1 + np.nan_to_num(mkt) / 100.0)
idx_ma20 = np.full_like(idx_eq, np.nan)
for i in range(20, len(idx_eq)):
    idx_ma20[i] = idx_eq[i - 20:i].mean()
above = idx_eq > idx_ma20

# ---------- 信号定义 (t 日收盘可得, 次日开盘买入) ----------
S = {
    "S0 等权全市场(基线)": ok,
    "S_mom 动量: 20日最强5%": ok & (ret20 >= np.nanpercentile(ret20, 95, axis=1)[:, None]),
    "S_rev 反转: 20日最弱10% + 缩量": ok & (ret20 <= np.nanpercentile(ret20, 10, axis=1)[:, None]) & (V < vma20) & (C > ma20),
    "S_w2s 弱转强: 昨跌>3%今放量涨>2%": ok & (prev_dn < -3) & (pct > 2) & (V > vma5),
    "S_tail 尾盘战法全条件": ok & (pct >= 2) & (pct <= 5) & (vr >= 1.2) & (C > ma5) & (C > ma10) & (C > ma20) \
        & (bar_pos >= 0.7) & (pos60 < 0.8) & (ilc_c >= 1) & (ipct_c > 1),
    "S_G 三招合一(均线+量价+回踩)": ok & (C > ma60) & (ma60 > np.nan_to_num(np.roll(ma60, 5, axis=0))) & (ma20 > ma60) & (ma5 > ma20) \
        & (C > O) & (V > vma5),
    "S_break 裸突破20日高+放量": ok & (C > np.nan_to_num(np.roll(hi20, 1, axis=0))) & (V > vma5 * 1.5),
    "S_lowlim 低位首板(60日分位<0.35)": ok & islim & (streak == 1) & (pos60 < 0.35),
    "S_strong 强势未封板(涨7-9.5%)": ok & (pct >= 7) & (pct < 9.5) & (V > vma5),
}
# 择时版: 大盘在MA20上方才持仓, 否则空仓
S_timed = {"S_timing 等权+大盘MA20择时": ok}

COST = 0.0015  # 双边
TOPN = 10


def simulate(mask, topn=TOPN, timed=False, step=5, score=None):
    eq = [1.0]
    dates = []
    n_select = []
    for t0 in range(60, n - step - 1, step):
        if timed and not above[t0]:
            eq.append(eq[-1])
            dates.append(days[t0])
            n_select.append(0)
            continue
        m = mask[t0] & np.isfinite(C[t0]) & np.isfinite(O[t0 + 1])
        idxs = np.where(m)[0]
        if score is not None and len(idxs) > topn:
            s = score[t0, idxs]
            idxs = idxs[np.argsort(-np.nan_to_num(s))[:topn]]
        elif len(idxs) > topn:
            idxs = np.random.default_rng(t0).choice(idxs, topn, replace=False)
        if len(idxs) == 0:
            eq.append(eq[-1]); dates.append(days[t0]); n_select.append(0); continue
        p0 = O[t0 + 1, idxs]
        p1 = C[t0 + step, idxs]
        r = np.nanmean(p1 / p0 - 1) - COST
        eq.append(eq[-1] * (1 + r))
        dates.append(days[t0]); n_select.append(len(idxs))
    eq = np.array(eq)
    return eq, dates, n_select


def metrics(eq, dates):
    r = np.diff(eq) / eq[:-1]
    yrs = len(r) * 5 / 244
    cagr = eq[-1] ** (1 / max(yrs, 1e-9)) - 1
    peak = np.maximum.accumulate(eq)
    mdd = np.min((eq - peak) / peak)
    return dict(total=eq[-1] - 1, cagr=cagr, mdd=mdd,
                win=np.mean(r > 0) * 100, n_pos=int(np.sum(r > 0)), n_tot=len(r),
                avg=np.mean(r) * 100)


print("=" * 108)
print(f"组合级模拟: 每5个交易日调仓, 等权最多{TOPN}只, 持有5日(次日开盘买), 双边成本0.15%")
print(f"样本 {days[60].date()} ~ {days[-1].date()}  ({(n-60)//5} 个调仓期)")
print("=" * 108)
print("| 战法 | 累计收益 | 年化 | 最大回撤 | 调仓胜率% | 盈利期/总期 | 单期均值% |")
print("|---|---|---|---|---|---|---|")
res = {}
for name, mask in S.items():
    eq, dts, nsel = simulate(mask)
    m = metrics(eq, dts)
    res[name] = (eq, m, nsel)
    print(f"| {name} | {m['total']*100:+.1f}% | {m['cagr']*100:+.1f}% | {m['mdd']*100:.1f}% | "
          f"{m['win']:.1f} | {m['n_pos']}/{m['n_tot']} | {m['avg']:+.2f} |")
for name, mask in S_timed.items():
    eq, dts, nsel = simulate(mask, timed=True)
    m = metrics(eq, dts)
    res[name] = (eq, m, nsel)
    print(f"| {name} | {m['total']*100:+.1f}% | {m['cagr']*100:+.1f}% | {m['mdd']*100:.1f}% | "
          f"{m['win']:.1f} | {m['n_pos']}/{m['n_tot']} | {m['avg']:+.2f} |")

print("\n【等权指数基准(买满全市场永不调仓)】")
base = idx_eq[-1] / idx_eq[60] - 1
peak = np.maximum.accumulate(idx_eq[60:])
mdd = np.min((idx_eq[60:] - peak) / peak)
print(f"  累计 {base*100:+.1f}%  最大回撤 {mdd*100:.1f}%")

print("\n【信号频率】平均每次调仓选出的股票数")
for name, (eq, m, nsel) in list(res.items())[:12]:
    print(f"  {name}: 平均 {np.mean(nsel):.1f} 只, 有信号的期数 {np.sum(np.array(nsel)>0)}/{len(nsel)}")

np.save("portfolio_curves.npy", {k: v[0] for k, v in res.items()}, allow_pickle=True)
print("\n[saved] portfolio_curves.npy")
