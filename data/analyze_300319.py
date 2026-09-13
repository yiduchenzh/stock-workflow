# -*- coding: utf-8 -*-
"""300319 交易记录深度统计 (2024-08 ~ 2026-08, 320笔)"""
import csv, statistics
from collections import defaultdict, Counter

ROWS = []
with open(r"D:\Hermes Agent CN Desktop\stock-workflow\data\300319_trades_20260822.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        r["price"] = float(r["price"]) if r["price"] else 0.0
        r["shares"] = int(r["shares"])
        r["pnl"] = float(r["pnl_pct"]) if r["pnl_pct"] else None
        r["asset"] = float(r["asset"])
        ROWS.append(r)
ROWS = ROWS[::-1]  # 正序: id 1 → 320

print("=" * 70)
print(f"总交易笔数: {len(ROWS)} | 期间: {ROWS[0]['date']} → {ROWS[-1]['date']}")
print(f"资产: ¥{ROWS[0]['asset']:,.0f} → ¥{ROWS[-1]['asset']:,.0f}  (+{(ROWS[-1]['asset']/ROWS[0]['asset']-1)*100:.1f}%)")
peak = max(ROWS, key=lambda r: r["asset"])
print(f"资产峰值: ¥{peak['asset']:,.0f} @ {peak['date']} {peak['time']}")

# ── 1. 动作分布 ──
print("\n" + "=" * 70)
print("① 动作分布")
acts = Counter(r["action"] for r in ROWS)
for a, c in acts.most_common():
    print(f"  {a:<12} {c:>3} 次")

# ── 2. 清仓/减半盈亏统计 (带 pnl 的卖出) ──
print("\n" + "=" * 70)
print("② 清仓/闪崩清仓/减半 盈亏统计 (带 pnl 的卖出动作)")
exit_acts = [r for r in ROWS if r["pnl"] is not None and r["action"] != "T0卖高抛"]
wins = [r for r in exit_acts if r["pnl"] > 0]
losses = [r for r in exit_acts if r["pnl"] < 0]
flat = [r for r in exit_acts if r["pnl"] == 0]
print(f"  卖出笔数: {len(exit_acts)} (盈{wins} / 亏{losses} / 平{flat})")
print(f"  胜率: {len(wins)/len(exit_acts)*100:.1f}%")
avg_w = statistics.mean([r['pnl'] for r in wins]) if wins else 0
avg_l = statistics.mean([r['pnl'] for r in losses]) if losses else 0
print(f"  平均盈利: +{avg_w:.2f}% | 平均亏损: {avg_l:.2f}% | 盈亏比: {abs(avg_w/avg_l) if avg_l else 0:.2f}")
total_pnl_pct = sum(r['pnl'] for r in exit_acts)
print(f"  累计盈亏%(简单加总): {total_pnl_pct:+.1f}")
print("  亏损单明细:")
for r in sorted([x for x in losses], key=lambda x: x["pnl"])[:8]:
    print(f"    {r['date']} {r['action']:<8} {r['price']:.2f} {r['pnl']:+.2f}% 资产¥{r['asset']:,.0f}")

# ── 3. T0 配对分析 (同日 T0卖高抛 → T0买接回) ──
print("\n" + "=" * 70)
print("③ T0 做T配对效率 (高抛价 vs 接回价, 同一天内相邻配对)")
by_date = defaultdict(list)
for r in ROWS:
    by_date[r["date"]].append(r)
t0_rounds = []      # 每轮: 卖价 - 买价(下一次买入)
t0_success = 0
t0_fail = 0
for d, rs in by_date.items():
    sells = [r for r in rs if r["action"] == "T0卖高抛"]
    buys = [r for r in rs if r["action"] == "T0买接回"]
    sells.sort(key=lambda x: x["time"])
    buys.sort(key=lambda x: x["time"])
    # 顺序配对: 卖→买 或 买→卖 交替; 简单法: 每个卖价 vs 其后最近买价
    events = sorted(rs, key=lambda x: x["time"])
    sell_queue = []
    for e in events:
        if e["action"] == "T0卖高抛":
            sell_queue.append(e["price"])
        elif e["action"] == "T0买接回" and sell_queue:
            sell_px = sell_queue.pop(0)
            diff = (sell_px - e["price"]) / e["price"] * 100
            t0_rounds.append(diff)
            if diff > 0: t0_success += 1
            else: t0_fail += 1
    # 若先买后卖(反向做T): 买价 vs 其后卖价
    buy_queue = []
    for e in events:
        if e["action"] == "T0买接回":
            buy_queue.append(e["price"])
        elif e["action"] == "T0卖高抛" and buy_queue:
            buy_px = buy_queue.pop(0)
            diff = (e["price"] - buy_px) / buy_px * 100
            t0_rounds.append(diff)
            if diff > 0: t0_success += 1
            else: t0_fail += 1
if t0_rounds:
    print(f"  配对轮次: {len(t0_rounds)} | 成功(卖>买): {t0_success} | 失败: {t0_fail} | 胜率 {t0_success/len(t0_rounds)*100:.1f}%")
    print(f"  平均单轮价差: {statistics.mean(t0_rounds):+.2f}% | 中位: {statistics.median(t0_rounds):+.2f}%")
    print(f"  单轮最大: {max(t0_rounds):+.2f}% | 最小: {min(t0_rounds):+.2f}%")
# 每日做T次数 Top
t0_days = {d: sum(1 for r in rs if 'T0' in r['action']) for d, rs in by_date.items()}
top_t0 = sorted(t0_days.items(), key=lambda x: -x[1])[:5]
print("  做T最密集的5天:", [(d, c) for d, c in top_t0])

# ── 4. 加仓分析 (加仓价 vs 当日首次建仓/进场价) ──
print("\n" + "=" * 70)
print("④ 加仓行为分析 (加仓价 vs 当日/持仓周期起点价)")
add_ups = []  # 加仓价高于前次买入价(追高)
add_downs = []  # 加仓价低于前次买入价(低吸)
prev_buy = None
for r in ROWS:
    if r["action"] in ("重新进场", "建仓兜底", "弱转强低吸", "T0买接回"):
        prev_buy = r["price"]
    elif r["action"] == "加仓" and prev_buy:
        diff = (r["price"] - prev_buy) / prev_buy * 100
        if diff >= 0: add_ups.append(diff)
        else: add_downs.append(diff)
        prev_buy = r["price"]  # 加仓后成为新基准
print(f"  加仓总次数: {len(add_ups)+len(add_downs)}")
print(f"  追高加仓(价高于上次买入): {len(add_ups)} 次 | 平均追高 {statistics.mean(add_ups):+.1f}%" if add_ups else "  无追高加仓")
print(f"  低吸加仓(价低于上次买入): {len(add_downs)} 次 | 平均低吸 {statistics.mean(add_downs):+.1f}%" if add_downs else "  无低吸加仓")

# ── 5. 持仓周期 (重新进场/建仓 → 清仓) ──
print("\n" + "=" * 70)
print("⑤ 完整持仓周期 (进场→清仓, 含中间加减仓)")
from datetime import datetime
periods = []
cur_entry = None
for r in ROWS:
    if r["action"] in ("重新进场", "建仓兜底", "弱转强低吸") and r["pnl"] is None:
        cur_entry = r
    elif r["action"] in ("清仓", "闪崩清仓", "清仓T1次日") and r["pnl"] is not None and cur_entry:
        d1 = datetime.strptime(cur_entry["date"], "%Y-%m-%d")
        d2 = datetime.strptime(r["date"], "%Y-%m-%d")
        periods.append(((d2 - d1).days + 1, cur_entry["price"], r["price"], r["pnl"], cur_entry["date"], r["date"]))
        cur_entry = None
if periods:
    print(f"  完整周期数: {len(periods)}")
    lens = [p[0] for p in periods]
    print(f"  持仓天数: 平均 {statistics.mean(lens):.1f} 天 | 中位 {statistics.median(lens):.0f} 天 | 最短 {min(lens)} | 最长 {max(lens)}")
    print("  周期盈亏分布:")
    for p in sorted(periods, key=lambda x: -x[3])[:5]:
        print(f"    {p[4]}→{p[5]} {p[0]}天 进{p[1]:.2f} 出{p[2]:.2f} {p[3]:+.2f}%")
    print("  最亏5个周期:")
    for p in sorted(periods, key=lambda x: x[3])[:5]:
        print(f"    {p[4]}→{p[5]} {p[0]}天 进{p[1]:.2f} 出{p[2]:.2f} {p[3]:+.2f}%")

# ── 6. 月度盈亏 ──
print("\n" + "=" * 70)
print("⑥ 月度盈亏 (清仓/减半/T0卖 的全部 pnl 加总)")
month_pnl = defaultdict(float)
for r in ROWS:
    if r["pnl"] is not None:
        month_pnl[r["date"][:7]] += r["pnl"]
for m in sorted(month_pnl):
    print(f"  {m}  {month_pnl[m]:+8.1f}%")

# ── 7. 买卖点时间分布 ──
print("\n" + "=" * 70)
print("⑦ 操作时间分布 (几点钟操作最多)")
hour_cnt = Counter()
for r in ROWS:
    if r["time"] and len(r["time"]) >= 5:
        hour_cnt[r["time"][:2]] += 1
for h in sorted(hour_cnt):
    print(f"  {h}:00  {hour_cnt[h]} 次")

# ── 8. T0卖 显示的盈亏 vs 当日接回 (说明记录语义) ──
print("\n" + "=" * 70)
print("⑧ 结论支撑: T0卖'显示盈亏'=该批次自建仓以来累计浮动盈利(非当次做T收益)")
big = [r for r in ROWS if r["action"] == "T0卖高抛" and r["pnl"] and r["pnl"] > 15]
for r in big[:5]:
    print(f"  {r['date']} {r['time']} 卖{r['price']:.2f} 显示{r['pnl']:+.1f}%")

# 资产阶段
print("\n" + "=" * 70)
print("⑨ 资产阶段 (关键时点)")
milestones = [
    ("2024-08-07", "起点"), ("2024-10-23", "第一波主升"),
    ("2025-01-01", "2025年初"), ("2025-06-01", "2025年中"),
    ("2025-09-01", "2025年9月"), ("2026-01-01", "2026年初"),
    ("2026-06-22", "6月主升"), ("2026-08-21", "当前"),
]
for d, label in milestones:
    near = min(ROWS, key=lambda r: abs((datetime.strptime(r["date"], "%Y-%m-%d") - datetime.strptime(d, "%Y-%m-%d")).days))
    print(f"  {d} {label:<10} 资产¥{near['asset']:,.0f} @{near['date']}")
