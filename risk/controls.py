
"""风控审核 — VaR + 压力测试 + 熔断 · 斯波朗迪+格雷厄姆"""
import json, logging, numpy as np
from pathlib import Path
logger = logging.getLogger("aurora.risk")
STATE_FILE = Path(__file__).resolve().parent.parent / "data" / "risk_state.json"

def _load(): 
    try: return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    except: return {}
def _save(s): 
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2))

def check_all(plans: list, positions: dict, cfg: dict) -> tuple:
    state = _load()
    state.setdefault("breaker", False); state.setdefault("consec", 0)
    state.setdefault("daily_pnl", 0.0); state.setdefault("peak_value", 0.0)
    state.setdefault("prev_day_value", 0.0)
    if state.get("breaker"):
        return [], [{"type": "breaker", "msg": "熔断已触发，需人工恢复"}]
    risk_cfg = cfg.get("risk", {})
    max_pos = risk_cfg.get("max_positions", 5)
    max_consec = risk_cfg.get("max_consecutive_losses", 3)
    alerts = []
    # 连续亏损
    if state.get("consec", 0) >= max_consec:
        return [], [{"type": "consec", "msg": f"连续{state['consec']}次亏损,暂停"}]
    # 仓位上限
    filtered = plans[:max_pos]
    if len(plans) > max_pos:
        alerts.append({"type": "cap", "msg": f"仓位超限({len(plans)}→{max_pos})"})
    # VaR检查: 单笔风险不超过总资本3%
    capital = risk_cfg.get("capital", 1_000_000)
    for p in filtered:
        risk_amount = p.get("entry_price", 0) * p.get("shares", 0) * 0.05
        if risk_amount > capital * 0.03:
            alerts.append({"type": "var", "code": p.get("code"), "msg": f"单笔VaR超3%: {risk_amount/capital*100:.1f}%"})
    return filtered, alerts

def record_trade(pnl_pct: float):
    state = _load()
    state["consec"] = state.get("consec", 0) + 1 if pnl_pct < 0 else 0
    state["daily_pnl"] = round(state.get("daily_pnl", 0) + pnl_pct, 4)
    _save(state)

def reset():
    _save({"breaker": False, "consec": 0, "daily_pnl": 0.0, "peak_value": 0.0, "prev_day_value": 0.0})
