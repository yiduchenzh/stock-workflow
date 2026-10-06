# -*- coding: utf-8 -*-
"""本周复盘第三批诊断: 持仓归属(本周新开/存量) / 09-16 批量砍仓原因 / 策略同质化 / 买后即减仓矛盾"""
import glob
import json
import os
import re
from collections import Counter, defaultdict

BASE = os.getcwd()
D = os.path.join(BASE, "data")
W0, W1 = "2026-09-14", "2026-09-19"


def jload(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def trades(p):
    d = jload(p)
    r = d.get("trades") if isinstance(d, dict) else d
    return r or []


print("=" * 22, "L. 期末持仓归属: 本周新开 vs 存量（按最后一次买入日）")
agg = jload(os.path.join(D, "agent_aggregate.json")).get("agents", {})
for d in sorted(glob.glob(os.path.join(D, "agent_*"))):
    if not os.path.isdir(d):
        continue
    nm = os.path.basename(d).replace("agent_", "")
    rows = trades(os.path.join(d, "trades.json"))
    a = agg.get(nm, {})
    holds = a.get("positions_detail") or []
    if not holds:
        print(f"  {nm:<12} 无持仓")
        continue
    print(f"\n  {nm}  (总资产 {a.get('total_value',0):,.0f} / 盈亏 {a.get('pnl',0):+,.0f} / 现金 {a.get('cash',0):,.0f})")
    for h in holds:
        c = str(h.get("code"))
        buys = [t for t in rows if str(t.get("code")) == c and str(t.get("action", "")).lower() == "buy"
                and abs(float(t.get("shares") or 0) - float(h.get("shares") or 0)) < 1e-6]
        lastb = buys[-1] if buys else None
        bt = str(lastb.get("time") or lastb.get("ts"))[:10] if lastb else "--"
        flag = "🆕本周新开" if bt >= W0 else "存量"
        print(f"     {c} {h.get('shares')}股 @成本{h.get('cost')}  最后买入 {bt} [{flag}]"
              f"  策略={((lastb or {}).get('buy_context') or {}).get('strategy')}")

print("\n" + "=" * 22, "M. 本周各账户使用的策略分布（同质化检查）")
mix = defaultdict(Counter)
for d in sorted(glob.glob(os.path.join(D, "agent_*"))) + ["__sim__"]:
    if d == "__sim__":
        rows, nm = trades(os.path.join(D, "sim_trades.json")), "主sim"
    else:
        nm = os.path.basename(d).replace("agent_", "")
        rows = trades(os.path.join(d, "trades.json"))
    for t in rows:
        if W0 <= str(t.get("time") or t.get("ts"))[:10] < W1:
            bc = t.get("buy_context") or t.get("context") or {}
            mix[nm][str(bc.get("strategy") or t.get("strategy") or "?")] += 1
for nm, c in mix.items():
    print(f"  {nm:<12} {dict(c)}")

print("\n" + "=" * 22, "N. 09-16 批量砍仓当日上下文")
log = os.path.join(D, "aurora.log")
lines = open(log, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(log) else []
d16 = [l for l in lines if l.startswith("2026-09-16")]
print(f"  09-16 日志 {len(d16)} 行")
for pat in ["regime", "大盘", "普跌", "涨跌", "熔断", "Step5", "sell", "止损", "mtf", "TrendHealth", "减仓", "清仓"]:
    h = [l for l in d16 if pat in l]
    if h:
        print(f"   --- {pat}: {len(h)}")
        for l in h[:4]:
            print("      ", l[:180])

print("\n" + "=" * 22, "O. 每日 regime/评分（从日志抓）")
for day in ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]:
    dl = [l for l in lines if l.startswith(day)]
    scores = [l for l in dl if re.search(r"score=\d", l, re.I)]
    reg = [l for l in dl if re.search(r"regime", l, re.I)]
    print(f"  {day}: 日志{len(dl):>5}行 | score行{len(scores)} | regime行{len(reg)}")
    for l in (reg[:2] or scores[:2]):
        print("      ", l[:170])

print("\n" + "=" * 22, "P. 价值投资者 301308 买后1分钟被判减仓 矛盾核查")
for d in sorted(glob.glob(os.path.join(D, "agent_*"))):
    nm = os.path.basename(d).replace("agent_", "")
    rows = trades(os.path.join(d, "trades.json"))
    for t in rows:
        if str(t.get("code")) == "301308":
            print(f"  {nm}: {str(t.get('time'))[:16]} {t.get('action')} {t.get('shares')}股 @{t.get('price')}"
                  f" pnl={t.get('pnl')} reason={str(t.get('reason'))[:60]}")
h = [l for l in lines if "301308" in l and l.startswith(("2026-09-18", "2026-09-17"))]
print("  引擎日志(301308, 09-17~18):")
for l in h[:12]:
    print("     ", l[:180])
