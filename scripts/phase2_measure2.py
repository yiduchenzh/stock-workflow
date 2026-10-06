# -*- coding: utf-8 -*-
"""阶段2 量测第二批: 画像预算 daily 表 / [Step2] 信号明细 / 板块数据源"""
import json
import os
import re
from collections import Counter

BASE = os.getcwd()
D = os.path.join(BASE, "data")

print("=" * 24, "① 画像级 budget 文件全量（看 daily 表是否存在/是否有值）")
for f in ["risk_budget.json", "risk_budget_新手入门.json", "risk_budget_趋势跟踪者.json",
          "risk_budget_价值投资者.json", "risk_budget_上班族中短线.json", "risk_budget_短线狙击手.json"]:
    p = os.path.join(D, f)
    if not os.path.exists(p):
        print(f"  {f}: 不存在")
        continue
    d = json.load(open(p, encoding="utf-8"))
    daily = d.get("daily") or {}
    keys = sorted(daily)
    print(f"\n  {f}")
    print(f"     weekly_pnl={d.get('weekly_pnl')!r} monthly_pnl={d.get('monthly_pnl')!r}")
    print(f"     current_value={d.get('current_value')} peak={d.get('peak_value')} last={d.get('last_record_date')}")
    print(f"     daily 表: {len(daily)} 天, 范围 {keys[0] if keys else '--'}~{keys[-1] if keys else '--'}")
    if keys:
        print(f"     最近5天: " + json.dumps({k: daily[k] for k in keys[-5:]}, ensure_ascii=False))

print("\n" + "=" * 24, "② [Step2] 信号明细（看具体战法名 + confirmed 规则）")
log = os.path.join(D, "aurora.log")
lines = open(log, encoding="utf-8", errors="replace").read().splitlines()
recent = [l for l in lines if l[:10] >= "2026-09-10"]
idx = [i for i, l in enumerate(recent) if "[Step2]" in l]
print(f"  9/10 起 [Step2] 行 {len(idx)}")
for i in idx[:4]:
    print("   --- 上下文:")
    for l in recent[max(0, i - 6):i + 3]:
        print("      ", l[:165])

print("\n  含战法名的信号日志样本(前 25 行):")
sig_lines = [l for l in recent if re.search(r"prev_close_[AB]|chan_buy|naked_|williams_r|\borb\b|wave_point|momentum_breakout", l)]
for l in sig_lines[:25]:
    print("     ", l[:170])

print("\n" + "=" * 24, "③ 板块数据源定位")
pats = ["sector", "板块"]
files = []
for root, _d, fs in os.walk(BASE):
    if any(x in root for x in (".git", "__pycache__", ".venv", "node_modules")):
        continue
    for f in fs:
        if f.endswith(".py"):
            files.append(os.path.join(root, f))
hits = []
for p in files:
    try:
        src = open(p, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    for i, line in enumerate(src.splitlines(), 1):
        if re.search(r"def .*sector|def .*板块|板块数据|push2.*clist|fs=m:90|f14.*板块", line):
            hits.append((os.path.relpath(p, BASE), i, line.strip()[:150]))
for h in hits[:25]:
    print(f"     {h[0]}:{h[1]}: {h[2]}")

print("\n  日志里板块失败前后的其他行(定位调用方):")
fl = [i for i, l in enumerate(lines) if "板块数据失败" in l]
if fl:
    i = fl[0]
    for l in lines[max(0, i - 8):i + 4]:
        print("      ", l[:175])
