# -*- coding: utf-8 -*-
"""【文章C/G/B】趋势>位置>形态>量能>突破确认 的优先级 + 三招合一 + 回调缩量五条件
观察日 t 用 t 及之前数据判信号, 前瞻收益 = t+1 起 (无未来函数)
"""
import numpy as np
from ev import load, stat, table, yearly

P = load()
C, O, H, L, V = P["close"], P["open"], P["high"], P["low"], P["volume"]
ma5, ma10, ma20, ma60, ma60p5 = P["ma5"], P["ma10"], P["ma20"], P["ma60"], P["ma60_prev5"]
vma5, vma20, hi20, lo20, hi60, lo60 = P["vma5"], P["vma20"], P["hi20"], P["lo20"], P["hi60"], P["lo60"]
pct, islim, newstk = P["pct"], P["is_limit"], P["new_stock"]

F5, F10, F20 = P["fwd5"], P["fwd10"], P["fwd20"]
ok = ~newstk & np.isfinite(ma60) & np.isfinite(hi60)

# ---------- 三大要素 ----------
trend_up = (C > ma60) & (ma60 > np.nan_to_num(ma60p5)) & (ma20 > ma60) & (ma5 > ma20)
trend_dn = (C < ma60) & (ma60 < np.nan_to_num(ma60p5))
pos60 = np.where(np.isfinite(hi60 - lo60) & (hi60 > lo60), (C - lo60) / (hi60 - lo60), np.nan)
pos_low = pos60 < 0.4
pos_high = pos60 > 0.8
vol_up = V > vma5 * 1.5                       # 放量
pullback_shrink = (V < vma20 * 0.8)           # 缩量(回踩)
breakout = (C > np.nan_to_num(np.roll(hi20, 1, axis=0))) & vol_up   # 放量突破20日高点
pull_confirm = (L <= ma20 * 1.02) & (C > ma20) & (C > O) & (V > vma5)  # 回踩MA20后放量收阳

print("=" * 110)
print("【文章C】优先级验证: 同样'放量突破20日高点', 在不同趋势/位置下的前瞻收益")
print("=" * 110)
print("| 组合 | 样本 | 5日均值% | 5日超额% | 10日均值% | 10日超额% | 10日胜率% | 20日超额% |")
print("|---|---|---|---|---|---|---|---|")
combos = [
    ("趋势↑ + 低位(分位<0.4)", breakout & trend_up & pos_low & ok),
    ("趋势↑ + 高位(分位>0.8)", breakout & trend_up & pos_high & ok),
    ("趋势↑ + 中位", breakout & trend_up & ~pos_low & ~pos_high & ok),
    ("趋势↓ + 低位", breakout & trend_dn & pos_low & ok),
    ("趋势↓ + 高位", breakout & trend_dn & pos_high & ok),
    ("[只看突破] 不看趋势位置", breakout & ok),
    ("[基线] 全市场", np.ones_like(ok, dtype=bool) & ok),
]
for name, m in combos:
    m = m & np.nan_to_num(np.isfinite(F5)).astype(bool)
    s5, s10, s20 = stat(F5, m, P), stat(F10, m, P), stat(F20, m, P)
    if s10["n"] == 0:
        print(f"| {name} | 0 | - | - | - | - | - | - |")
        continue
    print(f"| {name} | {s10['n']:,} | {s5['mean']:+.2f} | {s5['exc']:+.2f} | {s10['mean']:+.2f} | "
          f"{s10['exc']:+.2f} | {s10['win']:.1f} | {s20['exc']:+.2f} |")

print("\n【C-2】单因子独立效力 (逐层单独看, 验证'顺序不能乱')")
rows = [
    ("① 趋势↑ (MA多头+MA60上翘)", trend_up & ok, F10),
    ("② 低位 (60日分位<0.4)", pos_low & ok, F10),
    ("③ 形态: 放量突破20日高", breakout & ok, F10),
    ("④ 量能: 缩量回踩(量<20日均量80%)", (V < vma20 * 0.8) & (C > ma20) & ok, F10),
    ("⑤ 回踩MA20放量收阳(确认)", pull_confirm & ok, F10),
    ("① + ⑤ (趋势 + 回踩确认)", trend_up & pull_confirm & ok, F10),
    ("① + ② + ⑤ (趋势+低位+确认)", trend_up & pos_low & pull_confirm & ok, F10),
    ("② + ⑤ (低位 + 确认, 忽略趋势)", pos_low & pull_confirm & ok, F10),
]
print(table([(n, stat(f, m, P)) for n, m, f in rows]))

print("\n【C-3】'高位放量突破'的陷阱检验 (文章: 高位放量滞涨=出货)")
hi_break_high = breakout & pos_high & ok
print("  高位(>0.8分位)放量突破20日高 → 10日超额:",
      f"{stat(F10, hi_break_high, P)['exc']:+.2f}%  胜率{stat(F10, hi_break_high, P)['win']:.1f}%"
      f"  n={stat(F10, hi_break_high, P)['n']:,}")
lo_break_low = breakout & (pos60 < 0.2) & (pos60 >= 0) & ok
s = stat(F10, lo_break_low, P)
print(f"  低位(<0.2分位)放量突破20日高 → 10日超额: {s['exc']:+.2f}%  胜率{s['win']:.1f}%  n={s['n']:,}")

print("\n" + "=" * 110)
print("【文章G】上升趋势三招合一: 均线向上 + 量价健康 + 回踩确认")
print("=" * 110)
# 量价健康: 近5日"涨日放量+跌日缩量" 占比
up_day = C > np.nan_to_num(np.roll(C, 1, axis=0))
vol_expand_up = up_day & (V > vma5)
vol_shrink_dn = (~up_day) & (V < vma5)
healthy = np.nan_to_num(vol_expand_up | vol_shrink_dn).astype(float)
# 用近5日健康度
S = np.zeros_like(healthy)
for h in range(5):
    S += np.nan_to_num(np.roll(healthy, h, axis=0))
healthy5 = S / 5.0 >= 0.6
# 回踩确认: 近期回踩MA20不破 + 再放量上攻
recent_touch = np.zeros_like(ok)
for h in range(1, 6):
    recent_touch |= np.nan_to_num(np.roll((L <= ma20 * 1.02) & (C >= ma20 * 0.98), h, axis=0)).astype(bool)
re_attack = recent_touch & (C > O) & vol_up & (C > ma20)
g1 = trend_up & ok
g2 = g1 & healthy5
g3 = g2 & re_attack
rows = [
    ("① 只均线向上", g1, F10),
    ("② 均线向上 + 量价健康", g2, F10),
    ("③ 三招合一(再+回踩放量上攻)", g3, F10),
    ("③ 三招合一 → 持5日", g3, F5),
    ("③ 三招合一 → 持20日", g3, F20),
]
print(table([(n, stat(f, m, P)) for n, m, f in rows]))
print("\n  ③ 三招合一分年度 (持10日):")
for y, s in yearly(F10, g3, P).items():
    print(f"    {y}: n={s['n']:,} 均值{s['mean']:+.2f}% 胜率{s['win']:.1f}% 超额{s['exc']:+.2f}%")

print("\n" + "=" * 110)
print("【文章B】回调缩量模型 (五条件: 强势拉升过 + 非今日拉 + 拉升量不过大 + 回调缩量 + 均线多头)")
print("=" * 110)
ret20 = np.full_like(C, np.nan)
ret20[20:] = (C[20:] / C[:-20] - 1) * 100
lim20 = np.zeros_like(islim)
for h in range(1, 21):
    lim20 |= np.nan_to_num(np.roll(islim, h, axis=0)).astype(bool)
c1 = ret20 >= 15                                    # 近期强势拉升
c2 = pct < 5                                        # 不是今天刚拉(避免追高)
c3 = lim20                                          # 拉升期出现过涨停
v_pull = np.zeros_like(V)
for h in range(1, 4):
    v_pull += np.nan_to_num(np.roll(V, h, axis=0))
v_pull /= 3.0
c4 = v_pull < vma20 * 0.8                           # 回调缩量
c5 = (C > ma20) & (ma20 > ma60) & (ma60 > np.nan_to_num(ma60p5))
c6 = np.abs(C / ma20 - 1) < 0.05                    # 不偏离MA20太远
c7 = down3 = np.zeros_like(ok)
dn = np.zeros_like(ok)
for h in range(1, 4):
    dn |= np.nan_to_num(np.roll(C < np.nan_to_num(np.roll(C, 1, axis=0)), h, axis=0)).astype(bool)
m_all = c1 & c2 & c3 & c4 & c5 & c6 & ok
rows = [
    ("强势拉升过(20日+15%)", c1 & ok, F10),
    ("+ 回调缩量", c1 & c4 & ok, F10),
    ("+ 均线多头", c1 & c4 & c5 & ok, F10),
    ("+ 不偏离MA20", c1 & c4 & c5 & c6 & ok, F10),
    ("+ 拉升期有涨停(全部条件)", m_all, F10),
    ("全部条件 → 持5日", m_all, F5),
    ("全部条件 → 持20日", m_all, F20),
    ("[基线] 全市场", ok, F10),
]
print(table([(n, stat(f, m, P)) for n, m, f in rows]))
print("\n  全部条件 分年度 (持10日):")
for y, s in yearly(F10, m_all, P).items():
    print(f"    {y}: n={s['n']:,} 均值{s['mean']:+.2f}% 胜率{s['win']:.1f}% 超额{s['exc']:+.2f}%")
