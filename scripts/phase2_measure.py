# -*- coding: utf-8 -*-
"""阶段2 量测脚本 — 改代码前先量清楚三件事
① 各战法近 4 周实际产信号次数（决定哪条能当画像专属主战法）
② 画像级 risk_budget 写入点（weekly_pnl=1e-9 根因）
③ 板块数据失败源头（448 行 RemoteDisconnected）
"""
import glob
import json
import os
import re
from collections import Counter

BASE = os.getcwd()
D = os.path.join(BASE, "data")
LOG = os.path.join(D, "aurora.log")

print("=" * 24, "① 各战法产信号次数（近 4 周日志 + candidate_history）")
lines = open(LOG, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(LOG) else []
recent = [l for l in lines if l[:10] >= "2026-08-20"]
print(f"  日志总行 {len(lines)}, 8/20 起 {len(recent)}")

# 信号名清单（本系统已知战法/信号）
SIGS = ["prev_close_A", "prev_close_B", "momentum_breakout", "ma_breakout", "wave_point",
        "sector_rotation", "mean_reversion", "chan_buy1", "chan_buy2", "chan_buy3",
        "first_board", "naked_pinbar", "naked_engulf", "williams_r", "orb", "pullback",
        "123_rule", "zhijian", "dip", "auction_capture"]
cnt = Counter()
for l in recent:
    for s in SIGS:
        if s in l:
            cnt[s] += 1
for s, n in cnt.most_common():
    print(f"    {s:<22} 出现 {n:>5} 行")

# 信号确认日志里的实际确认数
conf = [l for l in recent if re.search(r"confirmed|confirmation|信号确认", l, re.I)]
print(f"\n  含 confirmed 语义行: {len(conf)}")
for l in conf[:10]:
    print("     ", l[:170])

# 计划里的 strategy 字段
strat_in_plan = Counter()
for l in recent:
    m = re.findall(r"strategy['\"]?\s*[:=]\s*['\"]?([a-z_0-9]+)", l)
    for x in m:
        strat_in_plan[x] += 1
print("\n  日志里 strategy= 出现统计:", dict(strat_in_plan.most_common(12)))

ch = os.path.join(D, "candidate_history.json")
if os.path.exists(ch):
    d = json.load(open(ch, encoding="utf-8"))
    if isinstance(d, dict):
        print("\n  candidate_history keys:", list(d.keys())[:8])
        for k in list(d.keys())[:3]:
            v = d[k]
            print(f"    {k}: {type(v).__name__} len={len(v) if hasattr(v,'__len__') else '-'}")
            if isinstance(v, list) and v:
                print("      样例:", json.dumps(v[-1], ensure_ascii=False)[:300])
    elif isinstance(d, list):
        print(f"\n  candidate_history list len={len(d)}; 样例:", json.dumps(d[-1], ensure_ascii=False)[:300])
        c2 = Counter()
        for it in d:
            for key in ("strategy", "signal", "src"):
                if it.get(key):
                    c2[f"{key}={it[key]}"] += 1
        print("  字段分布:", dict(c2.most_common(15)))

print("\n" + "=" * 24, "② 画像级 risk_budget 写入点")
for pat in [r"risk_budget_", r"weekly_pnl", r"monthly_pnl"]:
    hits = []
    for root, _dirs, files in os.walk(BASE):
        if any(x in root for x in ("\\.git", "__pycache__", ".venv", "node_modules")):
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(root, f)
            try:
                src = open(p, encoding="utf-8", errors="replace").read()
            except Exception:
                continue
            for i, line in enumerate(src.splitlines(), 1):
                if re.search(pat, line):
                    hits.append((os.path.relpath(p, BASE), i, line.strip()[:150]))
    print(f"\n  --- 匹配 {pat}: {len(hits)} 处")
    for h in hits[:14]:
        print(f"     {h[0]}:{h[1]}: {h[2]}")

print("\n" + "=" * 24, "③ 板块数据失败源头")
sec = [l for l in recent if "板块数据失败" in l]
print(f"  '板块数据失败' 行数(8/20起): {len(sec)}")
# 源头函数
hits = []
for root, _dirs, files in os.walk(BASE):
    if any(x in root for x in ("\\.git", "__pycache__", ".venv", "node_modules")):
        continue
    for f in files:
        if not f.endswith(".py"):
            continue
        p = os.path.join(root, f)
        src = open(p, encoding="utf-8", errors="replace").read()
        for i, line in enumerate(src.splitlines(), 1):
            if "板块数据失败" in line:
                hits.append((os.path.relpath(p, BASE), i, line.strip()[:160]))
for h in hits:
    print(f"     {h[0]}:{h[1]}: {h[2]}")
