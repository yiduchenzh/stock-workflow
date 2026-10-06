# -*- coding: utf-8 -*-
"""核心机制检验: 当日涨幅分层 / 短期反转效应 / 市场环境门控 / 最终候选组合
这是给"哪些自媒体规则其实站不住"下结论的关键部分
"""
import numpy as np
from ev import load, stat, table, yearly

P = load()
C, O, H, L, V = P["close"], P["open"], P["high"], P["low"], P["volume"]
pct, islim, newstk = P["pct"], P["is_limit"], P["new_stock"]
ma5, ma20, ma60, vma5, vma20 = P["ma5"], P["ma20"], P["ma60"], P["vma5"], P["vma20"]
F5, F10, F20 = P["fwd5"], P["fwd10"], P["fwd20"]
mkt = P["mkt_pct"]
ok = ~newstk & np.isfinite(ma20)

gap = np.full_like(C, np.nan); gap[:-1] = (P["nxt_open"][:-1] / C[:-1] - 1) * 100
d1c = np.full_like(C, np.nan); d1c[:-1] = (P["nxt_close"][:-1] / C[:-1] - 1) * 100
d1h = np.full_like(C, np.nan); d1h[:-1] = (P["nxt_high"][:-1] / C[:-1] - 1) * 100

print("=" * 100)
print("【核心1】当日涨幅分层 → 次日/未来收益 (检验'尾盘追涨'与'别追高'两种对立说法)")
print("=" * 100)
print("| 当日涨幅 | 样本 | 隔夜跳空% | 次日收盘% | 次日超额% | 次日胜率% | 5日超额% | 10日超额% |")
print("|---|---|---|---|---|---|---|---|")
buckets = [(0, 2, "0~2%"), (2, 5, "2~5%(文章黄金区间)"), (5, 7, "5~7%"),
           (7, 9.5, "7~9.5%(强势未封板)"), (9.5, 100, "涨停(收盘买不到)"),
           (-5, 0, "下跌(-5~0%)"), (-100, -5, "大跌(<-5%)")]
for lo, hi, nm in buckets:
    m = ok & (pct > lo) & (pct <= hi)
    a, b, s5, s10 = stat(gap, m, P, demean=False), stat(d1c, m, P), stat(F5, m, P), stat(F10, m, P)
    print(f"| {nm} | {b['n']:,} | {a['mean']:+.2f} | {b['mean']:+.2f} | {b['exc']:+.2f} | {b['win']:.1f} | "
          f"{s5['exc']:+.2f} | {s10['exc']:+.2f} |")

print("\n【核心2】短期反转效应: 过去N日涨幅分位 → 未来收益 (A股日线尺度的主导效应)")
print("| 过去20日涨幅分位 | 样本 | 未来5日超额% | 未来10日超额% | 未来20日超额% | 10日胜率% |")
print("|---|---|---|---|---|---|")
ret20 = np.full_like(C, np.nan); ret20[20:] = (C[20:] / C[:-20] - 1) * 100
r20_rank = np.full_like(C, np.nan)
sub = np.where(np.isfinite(ret20), ret20, np.nan)
order = np.argsort(np.argsort(np.nan_to_num(sub, nan=-999), axis=1), axis=1)
cnt = np.sum(np.isfinite(sub), axis=1, keepdims=True)
r20_rank = order / np.maximum(cnt - 1, 1)
for lo, hi, nm in [(0, 0.2, "最弱20%"), (0.2, 0.4, "20-40%"), (0.4, 0.6, "中位"),
                   (0.6, 0.8, "60-80%"), (0.8, 1.01, "最强20%")]:
    m = ok & (r20_rank >= lo) & (r20_rank < hi)
    s5, s10, s20 = stat(F5, m, P), stat(F10, m, P), stat(F20, m, P)
    print(f"| {nm} | {s10['n']:,} | {s5['exc']:+.2f} | {s10['exc']:+.2f} | {s20['exc']:+.2f} | {s10['win']:.1f} |")

print("\n【核心3】市场环境门控: 大盘(等权)相对MA20 → 个股未来收益")
mkt_ma20 = np.full_like(mkt, np.nan)
mkt_ma20[20:] = [np.nanmean(mkt[i - 20:i]) for i in range(20, len(mkt))]
# 用等权指数
idx_eq = np.cumprod(1 + np.nan_to_num(mkt) / 100.0)
idx_ma20 = np.full_like(idx_eq, np.nan)
for i in range(20, len(idx_eq)):
    idx_ma20[i] = idx_eq[i - 20:i].mean()
above = idx_eq > idx_ma20
print("| 市场状态 | 样本 | 未来5日超额% | 未来10日超额% | 10日胜率% |")
print("|---|---|---|---|---|")
for nm, cond in [("大盘在MA20上方(多头环境)", above), ("大盘在MA20下方(空头环境)", ~above & ~np.isnan(idx_ma20))]:
    m = ok & np.nan_to_num(cond)[:, None].astype(bool)
    s5, s10 = stat(F5, m, P), stat(F10, m, P)
    print(f"| {nm} | {s10['n']:,} | {s5['exc']:+.2f} | {s10['exc']:+.2f} | {s10['win']:.1f} |")
print(f"  (样本期 2025-03~2026-09 等权指数累计 {idx_eq[-1]/idx_eq[20]-1:+.1%}; "
      f"多头环境天数 {above.sum()}/{len(above)})")

print("\n【核心4】'弱转强'检验: 前一日大跌 + 当日放量收阳 (低吸而非追高)")
prev_dn = np.roll(pct, 1, axis=0); prev_dn[0] = np.nan
weak2strong = ok & (prev_dn < -3) & (pct > 2) & (V > vma5)
strong2strong = ok & (prev_dn > 3) & (pct > 2) & (V > vma5)
rows = [
    ("昨跌>3% + 今放量涨>2% (弱转强)", weak2strong, F5),
    ("昨涨>3% + 今放量涨>2% (强更强)", strong2strong, F5),
    ("昨跌>3% + 今缩量跌 (阴跌)", ok & (prev_dn < -3) & (pct < 0) & (V < vma5), F5),
    ("[基线] 全市场", ok, F5),
]
print(table([(n, stat(f, m, P)) for n, m, f in rows]))

print("\n【核心5】最终候选战法组合 (逐步叠加, 全部无未来函数; 次日开盘买入)")
hi60, lo60 = P["hi60"], P["lo60"]
pos60 = np.where(hi60 > lo60, (C - lo60) / (hi60 - lo60), np.nan)
ind = P["code_ind_idx"]; ipct = P["ind_pct"]
ipct_c = ipct[:, np.maximum(ind, 0)]
lo_breakout = ok & (pos60 < 0.35) & (pct > 3) & (V > vma5 * 1.2) & (C > ma5)
combos = [
    ("S0 全市场", ok),
    ("S1 低位(<0.35分位) + 放量涨>3%", lo_breakout),
    ("S2 = S1 + 站上MA20", lo_breakout & (C > ma20)),
    ("S3 = S2 + 大盘在MA20上方", lo_breakout & (C > ma20) & np.nan_to_num(above)[:, None].astype(bool)),
    ("S4 = S3 + 所属行业当日涨>1%", lo_breakout & (C > ma20) & np.nan_to_num(above)[:, None].astype(bool) & (ipct_c > 1)),
]
print(table([(n, stat(F5, m, P)) for n, m, in [(x[0], x[1]) for x in combos]]))
for n, m in combos:
    s10, s20 = stat(F10, m, P), stat(F20, m, P)
    print(f"  {n}: 10日超额{s10['exc']:+.2f}% 胜率{s10['win']:.1f}% | 20日超额{s20['exc']:+.2f}%")
