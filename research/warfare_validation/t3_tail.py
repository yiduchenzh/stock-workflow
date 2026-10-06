# -*- coding: utf-8 -*-
"""【文章H】尾盘30分钟战法 八大标准 真实效力 (日线近似, 无未来函数)
买点=当日收盘价(14:50~15:00可成交), 收益口径: 隔夜跳空 / 次日收盘 / 次日最高冲高
"""
import numpy as np
from ev import load, stat, table, yearly

P = load()
C, O, H, L, V = P["close"], P["open"], P["high"], P["low"], P["volume"]
ma5, ma10, ma20, ma60 = P["ma5"], P["ma10"], P["ma20"], P["ma60"]
vma5, hi60, lo60 = P["vma5"], P["hi60"], P["lo60"]
pct, newstk, ind = P["pct"], P["new_stock"], P["code_ind_idx"]
ilc, ipct = P["ind_lim_count"], P["ind_pct"]

gap = np.full_like(C, np.nan); gap[:-1] = (P["nxt_open"][:-1] / C[:-1] - 1) * 100      # 隔夜跳空
d1c = np.full_like(C, np.nan); d1c[:-1] = (P["nxt_close"][:-1] / C[:-1] - 1) * 100     # 到次日收盘
d1h = np.full_like(C, np.nan); d1h[:-1] = (P["nxt_high"][:-1] / C[:-1] - 1) * 100      # 次日最高
mkt = P["mkt_pct"]

ok = ~newstk & np.isfinite(ma20) & np.isfinite(hi60)
pos60 = np.where(hi60 > lo60, (C - lo60) / (hi60 - lo60), np.nan)
bar_pos = P["bar_pos"]
vr = np.where(vma5 > 0, V / vma5, np.nan)

s1 = (pct >= 2) & (pct <= 5)                                   # ① 涨幅2-5%
s2 = vr >= 1.2                                                  # ② 量比≥1.2
s3 = (C > ma5) & (C > ma10) & (C > ma20)                        # ③ 站上三条短均线
s4 = bar_pos >= 0.7                                             # ④ 收盘强势(收在当日振幅上半部)
s5 = np.zeros_like(ok)                                          # ⑤ 板块效应
idx = np.arange(C.shape[1])
good_ind = (ilc >= 1) & (ipct > 1.0)                            # 行业有涨停 且 行业涨幅>1%
s5 = np.where(ind >= 0, good_ind[:, np.maximum(ind, 0)], False)
s5 = np.nan_to_num(s5).astype(bool) & (ind >= 0)
s6 = pos60 < 0.8                                                # ⑥ 不在高位

print("=" * 100)
print("【文章H】尾盘战法逐条验证 (买=当日收盘, 持有过夜)")
print("=" * 100)


def row(name, m):
    m = m & ok
    a, b, c = stat(gap, m, P, demean=False), stat(d1c, m, P), stat(d1h, m, P, demean=False)
    if b["n"] == 0:
        return f"| {name} | 0 | - | - | - | - | - |"
    return (f"| {name} | {b['n']:,} | {a['mean']:+.2f} | {b['mean']:+.2f} | {b['exc']:+.2f} | "
            f"{b['win']:.1f} | {c['mean']:+.2f} |")


print("| 条件 | 样本 | 隔夜跳空% | 次日收盘% | 次日超额% | 次日胜率% | 次日最高% |")
print("|---|---|---|---|---|---|---|")
for name, m in [
    ("① 涨幅2-5%", s1),
    ("② 量比≥1.2", s2),
    ("③ 站上MA5/10/20", s3),
    ("④ 收盘强势(振幅上半部)", s4),
    ("⑤ 板块共振(行业有涨停+涨幅>1%)", s5),
    ("⑥ 不在高位(60日分位<0.8)", s6),
    ("①+②+③", s1 & s2 & s3),
    ("①+②+③+④", s1 & s2 & s3 & s4),
    ("①+②+③+④+⑤+⑥ (文章全条件)", s1 & s2 & s3 & s4 & s5 & s6),
    ("[对照] 涨幅>7%追高", (pct > 7)),
    ("[对照] 全市场任意日", np.ones_like(ok, dtype=bool)),
]:
    print(row(name, m))

print("\n【H-2】'尾盘偷袭' vs '全天强势' (用收盘在振幅位置区分)")
print("| 分组 | 样本 | 隔夜跳空% | 次日收盘% | 次日超额% | 次日胜率% |")
print("|---|---|---|---|---|---|")
for name, m in [
    ("涨幅2-5% 且 收盘在振幅下部(<0.4, 冲高回落)", s1 & (bar_pos < 0.4)),
    ("涨幅2-5% 且 收盘在中部", s1 & (bar_pos >= 0.4) & (bar_pos < 0.7)),
    ("涨幅2-5% 且 收盘在上部(≥0.7, 强势收官)", s1 & (bar_pos >= 0.7)),
]:
    m = m & ok
    a, b = stat(gap, m, P, demean=False), stat(d1c, m, P)
    print(f"| {name} | {b['n']:,} | {a['mean']:+.2f} | {b['mean']:+.2f} | {b['exc']:+.2f} | {b['win']:.1f} |")

print("\n【H-3】大盘环境分层 (文章: 大盘跌>1.5%时胜率从80%掉到30%)")
print("| 市场环境 | 样本 | 次日收盘% | 次日超额% | 次日胜率% |")
print("|---|---|---|---|---|")
for name, cond in [
    ("大盘当日跌>1.5%", mkt < -1.5),
    ("大盘当日跌0.5~1.5%", (mkt <= -0.5) & (mkt >= -1.5)),
    ("大盘当日涨0~0.5%", (mkt > 0) & (mkt <= 0.5)),
    ("大盘当日涨>0.5%", mkt > 0.5),
]:
    m = (s1 & s2 & s3 & s4 & s6 & ok) & cond[:, None]
    s = stat(d1c, m, P)
    print(f"| {name} | {s['n']:,} | {s['mean']:+.2f} | {s['exc']:+.2f} | {s['win']:.1f} |")

print("\n【H-4】全条件 分年度 (次日收盘)")
full = s1 & s2 & s3 & s4 & s5 & s6
for y, s in yearly(d1c, full & ok, P).items():
    print(f"  {y}: n={s['n']:,} 均值{s['mean']:+.2f}% 胜率{s['win']:.1f}% 超额{s['exc']:+.2f}%")
print(f"  全条件平均每日信号数: {np.nansum((full & ok))/np.sum(np.isfinite(mkt)):.1f} 只/日")

print("\n【H-5】换手率条件的替代检验 (缺流通股本, 用相对成交额分位代理)")
amt = C * V
amt_r = np.where(np.isfinite(np.roll(amt, 20, axis=0)), amt / (np.nan_to_num(np.roll(amt, 20, axis=0)) + 1e-9), np.nan)
print("| 相对成交额(当日/20日前) | 样本 | 次日收盘% | 次日超额% | 次日胜率% |")
print("|---|---|---|---|---|")
for lo, hi, nm in [(0, 1, "缩量(<1x)"), (1, 2, "温和放量1-2x"), (2, 5, "明显放量2-5x"), (5, 1e9, "巨量>5x")]:
    m = (s1 & s3 & s4 & s6 & ok) & (amt_r > lo) & (amt_r <= hi)
    s = stat(d1c, m, P)
    print(f"| {nm} | {s['n']:,} | {s['mean']:+.2f} | {s['exc']:+.2f} | {s['win']:.1f} |")
