# -*- coding: utf-8 -*-
"""验证【文章F】"涨停全加自选, 数够5天再决定"笨办法 + 文章A(梯队/连板) 的真实有效性
样本: 全市场 2025-03-06~2026-09-14, 5539只, 374个交易日
"""
import numpy as np
from ev import load, stat, table, hold_from_open, yearly, daymean

P = load()
C, O, H, L, V = P["close"], P["open"], P["high"], P["low"], P["volume"]
islim, streak, pct = P["is_limit"], P["limit_streak"], P["pct"]
vma5, ma5, ma10, ma20 = P["vma5"], P["ma5"], P["ma10"], P["ma20"]
mx = lambda s: (s, s)  # noqa


def shift_fwd(F, h):
    """把 t 日的值平移到 t+h (用于"5天后筛选"时读当日特征)"""
    out = np.full_like(F, np.nan) if F.dtype.kind == "f" else np.zeros_like(F)
    out[h:] = F[:-h]
    return out


print("=" * 100)
print("【文章F-1】原文明示数字: 涨停后次日追 vs 等5天再进   (基准=同日全市场等权)")
print("=" * 100)
first = islim & (streak == 1)
# 首板且前5日无涨停 (避免重叠事件)
prev5lim = np.zeros_like(islim)
for h in range(1, 6):
    prev5lim |= shift_fwd(islim, h)
ev = first & (~prev5lim)

r_t1_oc = P["t1_oc"]                                     # 次日开→次日收
r_t1_5 = hold_from_open(P, 1, 5)                          # 次日开→5日后收
r_t1_10 = hold_from_open(P, 1, 10)
r_t5_5 = hold_from_open(P, 6, 5)                          # 第6日(即涨停后第5个交易日后)开→再持5日
r_t5_10 = hold_from_open(P, 6, 10)

rows = [
    ("涨停后次日开盘买入,当日收盘卖(文章:亏3.2%/胜38%)", stat(r_t1_oc, ev, P)),
    ("涨停后次日开盘买入,持5日", stat(r_t1_5, ev, P)),
    ("涨停后次日开盘买入,持10日", stat(r_t1_10, ev, P)),
    ("涨停后第6个交易日开盘买入,持5日(文章:赚8.7%/胜64%)", stat(r_t5_5, ev, P)),
    ("涨停后第6个交易日开盘买入,持10日", stat(r_t5_10, ev, P)),
    ("[基线]全市场任意日买入持5日", stat(r_t1_5, np.ones_like(ev), P)),
]
print(table(rows))

print("\n【1b】连板高度分层 (文章: '三连板以上直接剔除'): 次日开→持5日")
for k in (1, 2, 3):
    m = islim & (streak == k)
    s = stat(r_t1_5, m, P)
    print(f"  首板后买入(n={k}连板): n={s['n']:,} 均值{s['mean']:+.2f}% 胜率{s['win']:.1f}% 超额{s['exc']:+.2f}%")
m = islim & (streak >= 4)
s = stat(r_t1_5, m, P)
print(f"  ≥4连板后买入: n={s['n']:,} 均值{s['mean']:+.2f}% 胜率{s['win']:.1f}% 超额{s['exc']:+.2f}%")

print("\n【1c】涨停位置分层 (文章: 低位启动 vs 高位诱多): 次日开→持5日")
pos60 = np.where(np.isfinite(P["hi60"] - P["lo60"]),
                 (C - P["lo60"]) / (P["hi60"] - P["lo60"]), np.nan)
for lo, hi, name in [(-0.01, 0.3, "低位(0-30%分位)"), (0.3, 0.6, "中位"), (0.6, 0.85, "中高位"),
                     (0.85, 1.01, "高位(>85%, 贴60日高)")]:
    m = ev & (pos60 > lo) & (pos60 <= hi)
    s = stat(r_t1_5, m, P)
    if s["n"]:
        print(f"  {name}: n={s['n']:,} 均值{s['mean']:+.2f}% 胜率{s['win']:.1f}% 超额{s['exc']:+.2f}%")

print("\n【1d】涨停日量能分层 (文章: 放量涨停=分歧 缩量涨停=锁定好): 次日开→持5日")
vr = np.where(vma5 > 0, V / vma5, np.nan)
for lo, hi, name in [(-0.01, 1.0, "缩量涨停(量<5日均量)"), (1.0, 1.5, "温和放量1-1.5x"),
                     (1.5, 3.0, "放量1.5-3x"), (3.0, 1e9, "巨量>3x")]:
    m = ev & (vr > lo) & (vr <= hi)
    s = stat(r_t1_5, m, P)
    if s["n"]:
        print(f"  {name}: n={s['n']:,} 均值{s['mean']:+.2f}% 胜率{s['win']:.1f}% 超额{s['exc']:+.2f}%")

print("\n" + "=" * 100)
print("【文章F-2】5天窗口 + A/B/C 分类的真实效力 (文章核心: 5天后按量价结构分类, 只做A类)")
print("=" * 100)
# t+5 时点可见的特征 (全部 <= t+5)
lim_close = C                                    # 涨停日收盘价(=涨停价)
px5 = shift_fwd(C, 5)                            # 第5日收盘
lo5b = np.full_like(L, np.nan)
for h in range(1, 6):
    lo5b = np.fmin(lo5b, shift_fwd(L, h))        # 涨停后1~5日最低
vol5 = np.zeros_like(V)
for h in range(1, 6):
    vol5 += np.nan_to_num(shift_fwd(V, h))
vol5 = vol5 / 5.0
# 涨停日量: 从 t+5 反查 t
vlim_past = np.full_like(V, np.nan)
vlim_past[5:] = V[:-5]                           # t+5 日的"5天前"= 涨停日量
ma5_5 = np.full_like(ma5, np.nan)
ma5_5[5:] = ma5[:-5]                             # t+5 日前的MA5
limc_past = np.full_like(C, np.nan)
limc_past[5:] = C[:-5]

not_broken = lo5b >= limc_past * 0.98            # 5日最低未有效跌破涨停价
shrink = vol5 < vlim_past * 0.7                  # 回调缩量(<涨停日量70%)
above_ma5 = px5 > ma5_5                          # 站稳5日线
# 汇总到"涨停日 t"这个观察点(评估用的是 t+5 之后的收益, 但掩码取 t+5 时点)
at = lambda M: np.vstack([M[5:], np.full((5, M.shape[1]), False)])
A = at(not_broken & shrink & above_ma5)
Ccl = at((~not_broken) | ((vol5 > vlim_past * 1.2) & (px5 < limc_past * 0.98)))
Bm = at(~(not_broken & shrink & above_ma5) & ~Ccl)

r_after5 = hold_from_open(P, 6, 5)
r_after10 = hold_from_open(P, 6, 10)
r_after20 = hold_from_open(P, 6, 20)

rows = [
    ("A类(5日缩量+未破涨停价+站5日线) → 再持5日", stat(r_after5, ev & A, P)),
    ("A类 → 再持10日", stat(r_after10, ev & A, P)),
    ("A类 → 再持20日", stat(r_after20, ev & A, P)),
    ("B类(未破但未缩量) → 再持10日", stat(r_after10, ev & Bm, P)),
    ("C类(破涨停价/放量下跌) → 再持10日", stat(r_after10, ev & Ccl, P)),
    ("[对照]全部首板无过滤, 涨停后第6日买持10日", stat(r_after10, ev, P)),
    ("[基线]全市场持10日", stat(r_after10, np.ones_like(ev), P)),
]
print(table(rows))

print("\n【2b】分年度稳健性 (A类 → 再持10日)")
for y, s in yearly(r_after10, ev & A, P).items():
    print(f"  {y}: n={s['n']:,} 均值{s['mean']:+.2f}% 胜率{s['win']:.1f}% 超额{s['exc']:+.2f}%")
print("  -- 对照: 全部首板 --")
for y, s in yearly(r_after10, ev, P).items():
    print(f"  {y}: n={s['n']:,} 均值{s['mean']:+.2f}% 胜率{s['win']:.1f}% 超额{s['exc']:+.2f}%")

print("\n【2c】观察窗口敏感性 (文章称5天最优): 在不同观察窗口N后按同规则筛选, 再持10日")
for N in (3, 5, 7, 10):
    loN = np.full_like(L, np.nan)
    for h in range(1, N + 1):
        loN = np.fmin(loN, shift_fwd(L, h))
    vN = np.zeros_like(V)
    for h in range(1, N + 1):
        vN += np.nan_to_num(shift_fwd(V, h))
    vN = vN / N
    vlimN = np.full_like(V, np.nan); vlimN[N:] = V[:-N]
    ma5N = np.full_like(ma5, np.nan); ma5N[N:] = ma5[:-N]
    cN = np.full_like(C, np.nan); cN[N:] = C[:-N]
    pxN = np.full_like(C, np.nan); pxN[N:] = C[:-N]
    m = (loN >= cN * 0.98) & (vN < vlimN * 0.7) & (pxN > ma5N)
    mm = np.vstack([m[N:], np.full((N, m.shape[1]), False)])
    r = hold_from_open(P, N + 1, 10)
    s = stat(r, ev & mm, P)
    print(f"  观察{N}天: n={s['n']:,} 均值{s['mean']:+.2f}% 胜率{s['win']:.1f}% 超额{s['exc']:+.2f}% 中位{s['med']:+.2f}%")

print("\n【2d】涨停后5日内走势分布 (文章: 80%一日游/15%涨20-30%/5%翻倍)")
h5 = P["hi_next5"]
tot = ev & np.isfinite(h5)
print(f"  涨停后5日内最高涨幅: >20% 占比 {np.mean(h5[tot] > 20)*100:.1f}%  >30% {np.mean(h5[tot]>30)*100:.1f}%  "
      f">50% {np.mean(h5[tot]>50)*100:.1f}%")
totat = ev & np.isfinite(lo5b) & np.isfinite(limc_past) & np.isfinite(P["fwd5"])
print(f"  涨停后5日内最低跌破涨停价(≥2%)的比例: "
      f"{np.mean(lo5b[totat] < limc_past[totat]*0.98)*100:.1f}%  (n={totat.sum():,})")
