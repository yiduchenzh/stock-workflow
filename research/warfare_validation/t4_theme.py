# -*- coding: utf-8 -*-
"""【文章A/J】主线题材识别: 涨停梯队 / 板块联动 / 持续放量 / 龙头 vs 跟风
行业分类 = 东财行业(5577只映射), 无未来函数
"""
import numpy as np
from ev import load, stat, table, yearly

P = load()
C, O, H, L, V = P["close"], P["open"], P["high"], P["low"], P["volume"]
islim, streak, pct = P["is_limit"], P["limit_streak"], P["pct"]
ma20, ma60 = P["ma20"], P["ma60"]
ilc, ipct, ind = P["ind_lim_count"], P["ind_pct"], P["code_ind_idx"]
newstk = P["new_stock"]
F5, F10, F20 = P["fwd5"], P["fwd10"], P["fwd20"]
ok = ~newstk & np.isfinite(ma20)
n, k = C.shape

# 个股所属行业当日涨停家数 / 行业涨幅 (广播到个股)
ilc_c = ilc[:, np.maximum(ind, 0)]
ipct_c = ipct[:, np.maximum(ind, 0)]
# 行业成交额
amt = C * V
ind_amt = np.zeros((n, ilc.shape[1]))
for j in range(ilc.shape[1]):
    m = ind == j
    if m.any():
        ind_amt[:, j] = np.nansum(np.nan_to_num(amt[:, m]), axis=1)
ind_amt5 = np.vstack([np.full((5, ind_amt.shape[1]), np.nan), ind_amt[:-5]])
ind_amt_ratio = np.where(ind_amt5 > 0, ind_amt / ind_amt5, np.nan)
iamt_c = ind_amt_ratio[:, np.maximum(ind, 0)]

print("=" * 100)
print("【文章A-1】涨停梯队效应: 孤零零涨停 vs 板块批量涨停 (验证'零星是消息, 批量才是主线')")
print("=" * 100)
prev5lim = np.zeros_like(islim)
for h in range(1, 6):
    prev5lim |= np.nan_to_num(np.roll(islim, h, axis=0)).astype(bool)
ev = (islim & (streak == 1) & (~prev5lim))
r5 = np.full_like(C, np.nan); r5[:-1] = (P["nxt_close"][:-1] / P["nxt_open"][:-1] - 1) * 100  # 次日开→次日收
hold5 = np.full_like(C, np.nan)
hold5[:-6] = (P["close"][6:] / P["open"][1:-5] - 1) * 100                                     # 次日开→持5日
print("| 涨停当日板块涨停家数 | 样本 | 次日(开→收)% | 持5日% | 持5日超额% | 持5日胜率% |")
print("|---|---|---|---|---|---|")
for lo, hi, nm in [(0, 1, "0 (数据缺失)"), (1, 1, "仅1只(孤军)"), (2, 2, "2只"), (3, 5, "3-5只"),
                   (6, 1e9, "≥6只(批量涨停)")]:
    m = ev & ok & (ilc_c >= lo) & (ilc_c <= hi)
    a, b = stat(r5, m, P), stat(hold5, m, P)
    if b["n"]:
        print(f"| {nm} | {b['n']:,} | {a['mean']:+.2f} | {b['mean']:+.2f} | {b['exc']:+.2f} | {b['win']:.1f} |")

print("\n【文章A-2】板块联动'跟风/补涨'股 (未涨停但板块批量涨停) → 未来收益")
for lo, hi, nm in [(0, 0, "板块无涨停"), (1, 1, "板块1只涨停"), (2, 2, "板块2只"), (3, 5, "板块3-5只"),
                   (6, 1e9, "板块≥6只")]:
    m = ok & (~islim) & (pct > 0) & (ilc_c >= lo) & (ilc_c <= hi)
    s = stat(F5, m, P)
    if s["n"]:
        s10 = stat(F10, m, P)
        print(f"  {nm}: n={s['n']:,} 5日{s['mean']:+.2f}%(超额{s['exc']:+.2f}% 胜{s['win']:.1f}%) "
              f"10日超额{s10['exc']:+.2f}%")

print("\n【文章A-3】行业持续性 & 放量 (文章: 成交额'连续多日'放大才是主线)")
print("| 行业状态 | 样本 | 5日均值% | 5日超额% | 5日胜率% | 10日超额% |")
print("|---|---|---|---|---|---|")
base = ok & (~islim)
rows = [
    ("行业当日放量>1.3x (单日)", base & (iamt_c > 1.3)),
    ("行业连续3日放量(均>1.3x)", base & (iamt_c > 1.3) & (np.roll(iamt_c > 1.3, 1, axis=0)) & (np.roll(iamt_c > 1.3, 2, axis=0))),
    ("行业5日涨幅排名前10%", None),
    ("行业当日涨幅>2%", base & (ipct_c > 2)),
    ("行业当日跌幅>2%", base & (ipct_c < -2)),
]
# 行业5日涨幅排名
ind_ret5 = np.full_like(ind_amt, np.nan)
ind_close_avg = np.zeros_like(ind_amt); ind_close_avg[:] = np.nan
for j in range(ilc.shape[1]):
    m = ind == j
    if m.any():
        ind_close_avg[:, j] = np.nanmean(np.where(np.isfinite(C[:, m]), C[:, m], np.nan), axis=1)
r5ind = np.full_like(ind_amt, np.nan)
r5ind[5:] = ind_close_avg[5:] / ind_close_avg[:-5] - 1
rank = np.argsort(np.argsort(np.nan_to_num(r5ind, nan=-9), axis=1), axis=1) / (ind_amt.shape[1] - 1)
top_ind = rank >= 0.9
rows[2] = ("行业5日涨幅排名前10%", base & top_ind[:, np.maximum(ind, 0)])
for nm, m in rows:
    s5, s10 = stat(F5, m, P), stat(F10, m, P)
    print(f"| {nm} | {s5['n']:,} | {s5['mean']:+.2f} | {s5['exc']:+.2f} | {s5['win']:.1f} | {s10['exc']:+.2f} |")

print("\n【文章A-4】'只做板块龙头'再检验: 行业内当日相对强度 (涨幅排名) 分层 → 5日收益")
# 行业内当日涨幅排名分位
pct_f = np.where(np.isfinite(pct), pct, np.nan)
ind_rank = np.full_like(C, np.nan)
for j in np.unique(ind):
    if j < 0:
        continue
    m = ind == j
    sub = pct_f[:, m]
    if sub.shape[1] < 3:
        continue
    order = np.argsort(np.argsort(np.nan_to_num(sub, nan=-999), axis=1), axis=1)
    cnt = np.sum(np.isfinite(sub), axis=1, keepdims=True)
    ind_rank[:, m] = order / np.maximum(cnt - 1, 1)
print("| 行业内涨幅排名分位 | 样本 | 5日均值% | 5日超额% | 5日胜率% | 20日超额% |")
print("|---|---|---|---|---|---|")
for lo, hi, nm in [(0.0, 0.2, "后20%(最弱)"), (0.2, 0.4, "20-40%"), (0.4, 0.6, "中间"),
                   (0.6, 0.8, "60-80%"), (0.8, 0.95, "前20%(次强)"), (0.95, 1.01, "第1名(龙头)")]:
    m = base & np.isfinite(ind_rank) & (ind_rank >= lo) & (ind_rank < hi) & (pct > 0)
    s5, s20 = stat(F5, m, P), stat(F20, m, P)
    if s5["n"]:
        print(f"| {nm} | {s5['n']:,} | {s5['mean']:+.2f} | {s5['exc']:+.2f} | {s5['win']:.1f} | {s20['exc']:+.2f} |")

print("\n【文章J-2】市场情绪周期: 全市场涨停家数分层 → 全市场次日/5日收益 (验证'情绪周期')")
md = P["days"]
tot_lim = np.nansum(islim, axis=1)
print("| 全市场涨停家数 | 天数 | 次日全市场均值% | 次日胜率% | 5日全市场均值% |")
print("|---|---|---|---|---|")
for lo, hi, nm in [(0, 20, "<20(冰点)"), (20, 40, "20-40"), (40, 70, "40-70"), (70, 110, "70-110"), (110, 1e9, ">110(亢奋)")]:
    rows_m = np.where((tot_lim >= lo) & (tot_lim < hi))[0]
    if len(rows_m) == 0:
        continue
    m = np.zeros_like(ok, dtype=bool); m[rows_m] = True
    s1, s5 = stat(P["fwd1"], m & ok, P), stat(F5, m & ok, P)
    print(f"| {nm} | {len(rows_m)} | {s1['mean']:+.2f} | {s1['win']:.1f} | {s5['mean']:+.2f} |"
          if s1.get("n") else f"| {nm} | {len(rows_m)} | - | - | - |")

print("\n【A-5】板块梯队 + 低位 + 首板 (综合最优组合尝试) → 持5日/10日")
hi60, lo60 = P["hi60"], P["lo60"]
pos60 = np.where(hi60 > lo60, (C - lo60) / (hi60 - lo60), np.nan)
for nm, m in [
    ("首板 + 板块≥3只涨停", ev & ok & (ilc_c >= 3)),
    ("首板 + 板块≥3只涨停 + 低位(<0.4)", ev & ok & (ilc_c >= 3) & (pos60 < 0.4)),
    ("首板 + 板块≥3只涨停 + 低位 + 行业涨幅>2%", ev & ok & (ilc_c >= 3) & (pos60 < 0.4) & (ipct_c > 2)),
]:
    for h, F in [(5, hold5), (10, np.full_like(C, np.nan))]:
        if h == 10:
            F[:-11] = (P["close"][11:] / P["open"][1:-10] - 1) * 100
        s = stat(F, m, P)
        print(f"  {nm} 持{h}日: n={s['n']:,} 均值{s['mean']:+.2f}% 中位{s['med']:+.2f}% 胜率{s['win']:.1f}% 超额{s['exc']:+.2f}%")
