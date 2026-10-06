# -*- coding: utf-8 -*-
"""本周复盘补充诊断: 画像权重映射 / 死账户 / 板块数据失败 / 资金流0通过"""
import glob
import json
import os
import re

BASE = os.getcwd()
D = os.path.join(BASE, "data")
W0, W1 = "2026-09-14", "2026-09-19"

print("=" * 22, "G. 画像权重表 (profiling/trader_types.py)")
src = open(os.path.join(BASE, "profiling", "trader_types.py"), encoding="utf-8").read()
# 画像名通常形如  "画像名": {  或  "key": "画像名"
names = re.findall(r'^\s{0,4}"([^"]{2,10})":\s*\{', src, re.M)
blocks = re.split(r'\n(?=\s{0,4}"[^"]{2,10}":\s*\{)', src)
for nm in names:
    i = src.find('"%s": {' % nm)
    seg = src[i:i + 1400]
    sw = re.search(r'"strategy_weights":\s*\{([^}]*)\}', seg)
    sp = re.search(r'"signal_prefer":\s*\{([^}]*)\}', seg)
    print(f"\n--- {nm}")
    print("   strategy_weights:", (sw.group(1).replace("\n", " ").strip() if sw else "(无)")[:260])
    print("   signal_prefer   :", (sp.group(1).replace("\n", " ").strip() if sp else "(无)")[:260])

print("\n" + "=" * 22, "H. 各 agent 全历史活跃度 / 本周 / 期末浮盈")
agg = json.load(open(os.path.join(D, "agent_aggregate.json"), encoding="utf-8")).get("agents", {})
for d in sorted(glob.glob(os.path.join(D, "agent_*"))):
    if not os.path.isdir(d):
        continue
    nm = os.path.basename(d).replace("agent_", "")
    tp = os.path.join(d, "trades.json")
    rows = []
    if os.path.exists(tp):
        try:
            rows = json.load(open(tp, encoding="utf-8"))
            if isinstance(rows, dict):
                rows = rows.get("trades") or []
        except Exception:
            rows = []
    wk = [t for t in rows if W0 <= str(t.get("time") or t.get("ts"))[:10] < W1]
    times = sorted(str(t.get("time") or t.get("ts"))[:10] for t in rows if (t.get("time") or t.get("ts")))
    a = agg.get(nm, {})
    print(f"  {nm:<12} 全历史{len(rows):>4}笔  首{times[0] if times else '--'} 末{times[-1] if times else '--'}"
          f"  本周{len(wk):>3}笔 | 总资产{a.get('total_value',0):>12,.0f} 盈亏{a.get('pnl',0):>10,.0f}"
          f" ({a.get('return_pct',0)}%) 持仓{a.get('positions',0)}")

print("\n" + "=" * 22, "I. 板块数据失败 / 资金流0通过 (本周日志样本)")
log = os.path.join(D, "aurora.log")
if os.path.exists(log):
    lines = open(log, encoding="utf-8", errors="replace").read().splitlines()
    wk = [l for l in lines if W0 <= l[:10] < W1]
    for pat, cap in [("板块数据失败", 6), ("Capital flow top200", 6), ("Dedup", 4), ("[Auction]", 4), ("Quality filter", 4)]:
        h = [l for l in wk if pat in l]
        print(f"\n  --- {pat}: {len(h)} 行")
        for l in h[:cap]:
            print("     ", l[:190])

print("\n" + "=" * 22, "J. 本周日志中的画像级预算/风控拦截")
if os.path.exists(log):
    for pat in ["预算", "budget", "清仓", "减仓", "拒", "熔断", "RiskBudget"]:
        h = [l for l in wk if pat in l]
        if h:
            print(f"  {pat}: {len(h)} 行, 样本:")
            for l in h[:3]:
                print("     ", l[:170])
else:
    print("  无日志")

print("\n" + "=" * 22, "K. 主sim 本周与 agent 是否同源(同票)")
sim = json.load(open(os.path.join(D, "sim_trades.json"), encoding="utf-8"))
srows = sim.get("trades") if isinstance(sim, dict) else sim
swk = [t for t in (srows or []) if W0 <= str(t.get("time") or t.get("ts"))[:10] < W1]
print("  主sim 本周:", [(str(t.get('time'))[:10], t.get('action'), t.get('code')) for t in swk])
for d in sorted(glob.glob(os.path.join(D, "agent_*"))):
    tp = os.path.join(d, "trades.json")
    if not os.path.exists(tp):
        continue
    nm = os.path.basename(d).replace("agent_", "")
    try:
        rows = json.load(open(tp, encoding="utf-8"))
        rows = rows.get("trades") if isinstance(rows, dict) else rows
    except Exception:
        continue
    same = [t.get("code") for t in (rows or [])
            if W0 <= str(t.get("time") or t.get("ts"))[:10] < W1
            and t.get("code") in {x.get("code") for x in swk}]
    if same:
        print(f"  ⚠️ {nm} 与主sim 同票: {same}")
