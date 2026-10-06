# -*- coding: utf-8 -*-
"""stock-workflow 周复盘统计（2026-09-14 ~ 2026-09-18 本周）

用法: cd <项目根>; .venv\\Scripts\\python.exe scripts\\week_review_w0918.py > out.txt 2>&1
     然后 Get-Content out.txt -Encoding UTF8
"""
import glob
import json
import os
import re
from collections import defaultdict

BASE = os.getcwd()
D = os.path.join(BASE, "data")
W0, W1 = "2026-09-14", "2026-09-19"          # 半开区间 [周一, 下周一)
DAYS = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]


def load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"__err__": str(e)}


def trades_of(p):
    d = load(p)
    return d.get("trades") if isinstance(d, dict) else d


def dd(t):
    return str(t.get("time") or t.get("ts"))[:10]


def fv(v, nd=2):
    return "--" if v is None else (round(float(v), nd) if isinstance(v, (int, float)) else v)


def stats(rows):
    buys = [t for t in rows if str(t.get("action", "")).lower() == "buy"]
    sells = [t for t in rows if str(t.get("action", "")).lower() == "sell"]
    pnls = [float(t.get("pnl") or 0) for t in sells]
    pos = [p for p in pnls if p > 0]
    neg = [p for p in pnls if p <= 0]
    hold = [float(t.get("holding_days") or 0) for t in sells if t.get("holding_days") is not None]
    return {"buy": len(buys), "sell": len(sells), "realized": round(sum(pnls), 2),
            "win_n": len(pos), "win_rate": round(len(pos) / len(pnls) * 100, 1) if pnls else None,
            "avg_win": round(sum(pos) / len(pos), 2) if pos else 0,
            "avg_loss": round(sum(neg) / len(neg), 2) if neg else 0,
            "best": round(max(pnls), 2) if pnls else 0, "worst": round(min(pnls), 2) if pnls else 0,
            "hold_avg": round(sum(hold) / len(hold), 2) if hold else None,
            "expectancy": round(sum(pnls) / len(pnls), 2) if pnls else None}


ACCOUNTS = [("主sim", os.path.join(D, "sim_trades.json"))] + [
    (os.path.basename(d).replace("agent_", ""), os.path.join(d, "trades.json"))
    for d in sorted(glob.glob(os.path.join(D, "agent_*"))) if os.path.isdir(d)]

print("=" * 24, "A. 各账户逐笔 + 汇总 + 按日")
agg = {}
for nm, p in ACCOUNTS:
    if not os.path.exists(p):
        continue
    rows = trades_of(p) or []
    wk = [t for t in rows if W0 <= dd(t) < W1]
    agg[nm] = wk
    print(f"\n--- {nm}: 全历史 {len(rows)} 笔 / 本周 {len(wk)} 笔")
    for t in wk:
        bc = t.get("buy_context") or t.get("context") or {}
        print(f"   {str(t.get('time') or t.get('ts'))[:16]} {str(t.get('action')):4} {t.get('code')} "
              f"{t.get('shares')}股 @{fv(t.get('price'))} pnl={fv(t.get('pnl'))} hold={fv(t.get('holding_days'))} "
              f"{fv(t.get('reason_label'))} {str(t.get('reason'))[:60]} strat={bc.get('strategy')}")
    print("   汇总:", json.dumps(stats(wk), ensure_ascii=False))
    for d in DAYS:
        day = [t for t in wk if dd(t) == d]
        if day:
            s = stats(day)
            print(f"     {d}: 买{s['buy']} 卖{s['sell']} 已实现{s['realized']} 胜率{s['win_rate']}")

print("\n" + "=" * 24, "B. 重叠审计（跨账户同(日,票)买入）")
buys = defaultdict(set)
for nm, wk in agg.items():
    for t in wk:
        if str(t.get("action", "")).lower() == "buy":
            buys[(dd(t), t.get("code"))].add(nm)
dup = {k: v for k, v in buys.items() if len(v) > 1}
print(f"  跨账户同(日,票)买入重叠 {len(dup)} 组 / 总 {len(buys)} 组")
for k, v in sorted(dup.items()):
    print(f"   {k[0]} {k[1]}: {sorted(v)}")
codes = {k[1] for k in dup}
tot = sum(float(t.get("pnl") or 0) for nm, wk in agg.items() for t in wk
          if t.get("code") in codes and str(t.get("action", "")).lower() == "sell")
print(f"  重叠票本周卖出已实现合计: {tot:+.2f}")

print("\n" + "=" * 24, "C. 摩擦成本 / 持仓天数 / 卖出原因前缀")
for nm, wk in agg.items():
    if not wk:
        continue
    comm = sum(float(t.get("commission") or (t.get("cost_detail") or {}).get("commission") or 0) for t in wk)
    stamp = sum(float(t.get("stamp") or (t.get("cost_detail") or {}).get("stamptax") or 0) for t in wk)
    amt = sum(float(t.get("price") or 0) * float(t.get("shares") or 0) for t in wk)
    slip = sum(abs(float(t.get("price") or 0) * float(t.get("shares") or 0)) * float(t.get("slippage_pct") or 0) / 100 for t in wk)
    hist = defaultdict(int)
    for t in wk:
        if str(t.get("action", "")).lower() == "sell":
            hist[t.get("holding_days")] += 1
    print(f"  {nm}: 成交额{amt:,.0f} 佣金{comm:.0f} 印花税{stamp:.0f} 滑点{slip:.0f} 合计{comm+stamp+slip:.0f}"
          f" ({(comm+stamp+slip)/amt*100 if amt else 0:.2f}%)")
    print(f"      持仓天数: " + " ".join(f"{k}天×{v}" for k, v in sorted(hist.items(), key=lambda x: (x[0] is None, x[0]))))
pre = defaultdict(int)
for nm, wk in agg.items():
    for t in wk:
        if str(t.get("action", "")).lower() == "sell":
            pre[str(t.get("reason") or "").split("@")[0].split(":")[0]] += 1
print("  卖出原因前缀(⚠️ trailing@ = engine 误卖路径):", dict(pre))

print("\n" + "=" * 24, "D. 日志管线统计")
log = os.path.join(D, "aurora.log")
if os.path.exists(log):
    lines = open(log, encoding="utf-8", errors="replace").read().splitlines()
    wk = [l for l in lines if W0 <= l[:10] < W1]
    print(f"  日志行命中本周区间: {len(wk)} / 总 {len(lines)}")
    s4 = [l for l in wk if "[Step4]" in l]
    s5 = [l for l in wk if "[Step5]" in l]
    liq = [l for l in wk if "[Liq]" in l]
    plans = sum(int(m.group(1)) for l in s4 if (m := re.search(r"\[Step4\] (\d+) plans", l)))
    killed = sum(int(m.group(1)) for l in liq if (m := re.search(r"\[Liq\] filtered (\d+)", l)))
    passed = sum(int(m.group(1)) for l in s5 if (m := re.search(r"\[Step5\] (\d+) passed", l)))
    print(f"  Step4 计划总数 {plans} | [Liq] 触发 {len(liq)} 次砍 {killed} 个 | Step5 通过 {passed}")
    print(f"  Step5 0 passed(全天无开仓) 次数: {len([l for l in s5 if '[Step5] 0 passed' in l])}")
    for pat in ["Sector top5 filter", "Capital flow top200", "Quality filter", "[Auction]", "板块数据失败", "Dedup"]:
        h = [l for l in wk if pat in l]
        zero = [l for l in h if re.search(r": 0/\d+ passed", l)]
        print(f"  {pat}: {len(h)} 次" + (f" (其中 0 通过 {len(zero)} → 该维度可能失效)" if zero else ""))
    print("  [SIM BUY] 成交:", len([l for l in wk if "[SIM BUY]" in l]), "笔")
    print("  [SIM SELL] 成交:", len([l for l in wk if "[SIM SELL]" in l]), "笔")
    # 关键告警
    for pat in ["ERROR", "异常", "Traceback", "恢复", "熔断", "预算", "拒单"]:
        h = [l for l in wk if pat in l]
        if h:
            print(f"  ⚠️ 含'{pat}' {len(h)} 行, 末3:")
            for l in h[-3:]:
                print("     ", l[:150])
else:
    print("  (无 data/aurora.log)")

print("\n" + "=" * 24, "E. 期末账户对比（含浮盈, 来自 agent_aggregate.json）")
ag = load(os.path.join(D, "agent_aggregate.json"))
agents = ag.get("agents") or {}
print(f"  快照时间: {ag.get('time')}")
print(f"  {'账户':<14}{'现金':>14}{'总资产':>14}{'盈亏':>12}{'收益率%':>10}{'持仓数':>7}  持仓明细")
tot_pnl = 0.0
for nm, a in agents.items():
    tot_pnl += float(a.get("pnl") or 0)
    pd = a.get("positions_detail") or []
    print(f"  {nm:<14}{a.get('cash'):>14,.0f}{a.get('total_value'):>14,.0f}{a.get('pnl'):>12,.0f}"
          f"{a.get('return_pct'):>10}{a.get('positions'):>7}  " +
          ", ".join(f"{x.get('code')}×{x.get('shares')}@{x.get('cost')}" for x in pd[:4]))
print(f"  {'合计':<14}{'':>14}{'':>14}{tot_pnl:>12,.0f}")
sim = load(os.path.join(D, "sim_state.json"))
print(f"\n  主sim: " + json.dumps(sim, ensure_ascii=False)[:400])

print("\n" + "=" * 24, "F. 风控/预算/信念 状态")
for f in ["risk_budget.json", "beliefs.json", "withdraw_state.json", "recovery_state.json",
          "strategy_evolution.json", "market_memory.json"]:
    p = os.path.join(D, f)
    if os.path.exists(p):
        print(f"  {f}:", json.dumps(load(p), ensure_ascii=False)[:420])
print("\n  --- 各画像独立预算(risk_budget_<画像>.json) ---")
for p in sorted(glob.glob(os.path.join(D, "risk_budget_*.json"))):
    print(f"  {os.path.basename(p)}:", json.dumps(load(p), ensure_ascii=False)[:260])
print("\n提示: risk_budget weekly_pnl 若为 1e-9 量级 = 日收益传参≈0 → 周/月预算闸永不触发")
