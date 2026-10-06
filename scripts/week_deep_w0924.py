# -*- coding: utf-8 -*-
"""本周复盘补充诊断 (2026-09-21~09-24)
① 持仓估值失真核实: state.current_price vs 腾讯实时价
② 账户真实浮亏重算 vs agent_aggregate 记账值
③ risk_budget_<画像>.weekly_pnl 语义核实
"""
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, '.')

BASE = Path('.').resolve()
D = BASE / 'data'


def load(p):
    try:
        return json.loads(Path(p).read_text(encoding='utf-8'))
    except Exception as e:
        return {"__err__": str(e)}


accs = {}
codes = set()
for sp in sorted(glob.glob(str(D / 'agent_*' / 'state.json'))):
    nm = Path(sp).parent.name.replace('agent_', '')
    st = load(sp)
    accs[nm] = st
    codes.update((st.get('positions') or {}).keys())
sim = load(D / 'sim_state.json')
codes.update((sim.get('positions') or {}).keys())

from data.sources import get_tencent_quotes          # noqa: E402

q = get_tencent_quotes(sorted(codes)) or {}
print(f"=== 实时价获取: {len(q)}/{len(codes)} 只 ===")

agg = load(D / 'agent_aggregate.json').get('agents') or {}
print("\n=== ① 账户估值失真核实（记账 current_price vs 实时价）===")
tot_bad = tot_real = 0.0
for nm, st in accs.items():
    cash = float(st.get('cash') or 0)
    pos = st.get('positions') or {}
    pv_bad = sum(p['shares'] * p.get('current_price', p.get('avg_cost', 0)) for p in pos.values())
    pv_real = sum(p['shares'] * (q.get(c, {}).get('price') or p.get('avg_cost', 0)) for c, p in pos.items())
    cap = float(st.get('capital') or 1000000)
    a = agg.get(nm, {})
    print(f"  {nm:<8} 持{len(pos)}只 记账总资产{cash + pv_bad:>14,.0f} (汇总表{float(a.get('total_value') or 0):>14,.0f})"
          f" 实时重算{cash + pv_real:>14,.0f} 差{(cash + pv_real) - (cash + pv_bad):>+12,.0f}"
          f" | 记账收益{(cash + pv_bad) / cap * 100 - 100:>7.2f}% 真实收益{(cash + pv_real) / cap * 100 - 100:>7.2f}%")
    tot_bad += cash + pv_bad
    tot_real += cash + pv_real
    for c, p in pos.items():
        cp = p.get('current_price')
        rp = q.get(c, {}).get('price')
        if rp and cp:
            print(f"      {c:<8} {p['shares']:>5}股 成本{p.get('avg_cost', 0):>8.3f} 记账{cp:>8.3f} 实时{rp:>8.3f}"
                  f" 偏离{(rp / cp - 1) * 100:>+6.2f}% 入场{p.get('entry_date', '')}")
print(f"  --- 合计: 记账 {tot_bad:,.0f} | 真实 {tot_real:,.0f} | 差 {tot_real - tot_bad:+,.0f} ---")

print("\n=== ② 主 sim 状态 ===")
print("  " + json.dumps({k: v for k, v in sim.items() if k in ('cash', 'total', 'date', 'positions')}, ensure_ascii=False)[:300])

print("\n=== ③ risk_budget_<画像>.weekly_pnl 语义核实 ===")
for p in sorted(glob.glob(str(D / 'risk_budget_*.json'))):
    nm = Path(p).name
    d = load(p)
    print(f"  {nm:<32} weekly_pnl={str(d.get('weekly_pnl')):<16} current={float(d.get('current_value') or 0):>14,.0f}"
          f" drawdown={float(d.get('drawdown_pct') or 0) * 100:.2f}%")
    dy = d.get('daily') or {}
    print("       daily 末6: " + ", ".join(f"{k}={v}" for k, v in sorted(dy.items())[-6:]))
