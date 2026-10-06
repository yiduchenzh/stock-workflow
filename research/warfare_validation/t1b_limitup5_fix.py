# -*- coding: utf-8 -*-
"""【文章F-2】"涨停后数5天再决定" 的真实效力 — 修正版(严格无未来函数, 观察日=涨停日t)
t 日看到的是未来5日(t+1..t+5)已走完的信息 + 从 t+6 开盘买入
"""
import numpy as np
from ev import load, stat, table, hold_from_open, yearly, fwd_at, fwd_roll

P = load()
C, O, H, L, V = P["close"], P["open"], P["high"], P["low"], P["volume"]
islim, streak = P["is_limit"], P["limit_streak"]
ma5, vma5 = P["ma5"], P["vma5"]

prev5lim = np.zeros_like(islim)
for h in range(1, 6):
    prev5lim |= np.nan_to_num(np.roll(islim, h, axis=0).astype(float)).astype(bool)
ev = (islim & (streak == 1) & (~prev5lim))          # 首板, 前5日无涨停
ev[:8] = False

# ---- 涨停日 t 观察: 未来5日(t+1..t+5)的量价结构 (已走完, 无未来函数) ----
lo_next5 = fwd_roll(L, 5, 1, "min")                 # 未来5日最低
v_next5 = fwd_roll(V, 5, 1, "mean")                 # 未来5日平均量
px5 = fwd_at(C, 5)                                  # 第5日收盘
ma5_at5 = fwd_at(ma5, 5)                            # 第5日MA5
lim_close = C                                       # 涨停日收盘 = 涨停价
lim_vol = V                                         # 涨停日成交量

not_broken = lo_next5 >= lim_close * 0.98           # 未有效跌破涨停价
shrink = v_next5 < lim_vol * 0.7                    # 回调缩量(≤涨停日量70%)
above_ma5 = px5 > ma5_at5                           # 站稳5日线
broken = lo_next5 < lim_close * 0.98
A = np.nan_to_num(not_broken & shrink & above_ma5).astype(bool)
Cc = np.nan_to_num(broken | ((v_next5 > lim_vol * 1.2) & (px5 < lim_close))).astype(bool)
B = np.nan_to_num(not_broken & (~shrink)).astype(bool) & ~Cc & ~A

r5 = hold_from_open(P, 6, 5)
r10 = hold_from_open(P, 6, 10)
r20 = hold_from_open(P, 6, 20)

print("=" * 100)
print("【文章F-2】涨停后观察5天 → 分类 → 第6日开盘买 (全部无未来函数)")
print("=" * 100)
rows = [
    ("A类(缩量+不破涨停价+站5日线) → 持5日", stat(r5, ev & A, P)),
    ("A类 → 持10日", stat(r10, ev & A, P)),
    ("A类 → 持20日", stat(r20, ev & A, P)),
    ("A类(仅不破涨停价+站5日线, 不要求缩量) → 持10日",
     stat(r10, ev & np.nan_to_num(not_broken & above_ma5).astype(bool), P)),
    ("A类(仅不破涨停价) → 持10日", stat(r10, ev & np.nan_to_num(not_broken).astype(bool), P)),
    ("B类(不破涨停价但放量) → 持10日", stat(r10, ev & B, P)),
    ("C类(破涨停价/放量下跌) → 持10日", stat(r10, ev & Cc, P)),
    ("[对照]全部首板, 第6日买持10日", stat(r10, ev, P)),
    ("[基线]全市场持10日", stat(r10, np.ones_like(ev), P)),
]
print(table(rows))
print(f"\n  各类占比: A {A[ev].mean()*100:.1f}%  B {B[ev].mean()*100:.1f}%  C {Cc[ev].mean()*100:.1f}%  (n={ev.sum():,})")

print("\n【2b】A类 分年度稳健性 (持10日)")
for y, s in yearly(r10, ev & A, P).items():
    print(f"  {y}: n={s['n']:,} 均值{s['mean']:+.2f}% 胜率{s['win']:.1f}% 超额{s['exc']:+.2f}% 中位{s['med']:+.2f}%")
print("  对照 全部首板:")
for y, s in yearly(r10, ev, P).items():
    print(f"  {y}: n={s['n']:,} 均值{s['mean']:+.2f}% 胜率{s['win']:.1f}% 超额{s['exc']:+.2f}%")

print("\n【2c】观察窗口敏感性 (文章称5天最优) — 同一套规则改用N天观察")
print("| 观察N天 | 样本 | 均值% | 中位% | 胜率% | 超额% |")
print("|---|---|---|---|---|---|")
for N in (3, 5, 7, 10):
    loN = fwd_roll(L, N, 1, "min")
    vN = fwd_roll(V, N, 1, "mean")
    pxN = fwd_at(C, N)
    ma5N = fwd_at(ma5, N)
    m = np.nan_to_num((loN >= C * 0.98) & (vN < V * 0.7) & (pxN > ma5N)).astype(bool)
    r = hold_from_open(P, N + 1, 10)
    s = stat(r, ev & m, P)
    if s["n"]:
        print(f"| {N} | {s['n']:,} | {s['mean']:+.2f} | {s['med']:+.2f} | {s['win']:.1f} | {s['exc']:+.2f} |")

print("\n【2d】涨停后5日内走势分布 (文章: 80%一日游 / 15%涨20-30% / 5%翻倍)")
h5 = P["hi_next5"]
tot = ev & np.isfinite(h5)
print(f"  5日内最高涨幅>20%: {np.mean(h5[tot]>20)*100:.1f}%   >30%: {np.mean(h5[tot]>30)*100:.1f}%   "
      f">50%: {np.mean(h5[tot]>50)*100:.1f}%   >100%: {np.mean(h5[tot]>100)*100:.1f}%")
print(f"  5日内最低跌破涨停价2%以上: {np.mean(lo_next5[tot] < C[tot]*0.98)*100:.1f}%   (n={tot.sum():,})")
print(f"  5日后收盘仍在涨停价上方: {np.mean(px5[tot] > C[tot])*100:.1f}%")

print("\n【2e】只做'缩量不破涨停价'这一类, 与用户已有战法的对比口径")
m = np.nan_to_num(not_broken & shrink).astype(bool)
for h, F in [(5, r5), (10, r10), (20, r20)]:
    s = stat(F, ev & m, P)
    print(f"  持{h}日: n={s['n']:,} 均值{s['mean']:+.2f}% 中位{s['med']:+.2f}% 胜率{s['win']:.1f}% 超额{s['exc']:+.2f}%")
