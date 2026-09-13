# -*- coding: utf-8 -*-
"""P2: 账户级策略档案对照 — 画像应买 vs 实际买 (v14.47)

输出每个 Agent 的信号白名单 + 实际交易信号, 标出"越界"策略。
"""
import sys, json
sys.path.insert(0, '.')
from pathlib import Path
from collections import defaultdict

ROOT = Path(r"D:\Hermes Agent CN Desktop\stock-workflow")
data_dir = ROOT / "data"

from profiling.trader_types import SCREENING_CONFIGS
from risk.position import signal_allowed

def load(name):
    p = data_dir / f"agent_{name}" / "trades.json"
    if not p.exists(): return []
    raw = p.read_bytes()
    for enc in ("utf-8", "gbk"):
        try: return json.loads(raw.decode(enc))
        except: continue
    return []

report = {"generated": __import__("datetime").datetime.now().isoformat(), "agents": {}}

for agent, cfg in SCREENING_CONFIGS.items():
    prefer = cfg.get("signal_prefer", {})
    trades = load(agent)
    # 统计各策略实际使用
    used = defaultdict(int)
    for t in trades:
        strat = (t.get("context") or {}).get("strategy") or (t.get("buy_context") or {}).get("strategy") or t.get("reason", "")
        if t["action"] == "buy":
            used[strat] += 1
    # 越界 = 实际用但不在白名单 (与 plan_positions 同匹配逻辑)
    violations = []
    for strat, cnt in used.items():
        if not signal_allowed(strat, prefer):
            violations.append({"strategy": strat, "count": cnt})

    agent_report = {
        "signal_prefer": prefer,
        "used": dict(used),
        "violations": violations,
        "pool_desc": cfg.get("desc", ""),
    }
    report["agents"][agent] = agent_report
    print(f"\n【{agent}】池子: {cfg.get('desc','')}")
    print(f"  白名单: {list(prefer.keys())}")
    print(f"  实际用: {dict(used) if used else '(无买入记录)'}")
    if violations:
        print(f"  ❌ 越界策略: {violations}")
    else:
        print(f"  ✅ 全部在画像内")

out = data_dir / "agent_strategy_audit.json"
out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\n报告已存: {out}")
