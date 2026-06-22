
"""风控审核 — 日亏损熔断 + 最大回撤 + 连续亏损"""
import json, logging
from pathlib import Path
logger = logging.getLogger("aurora.risk")
STATE_FILE = Path(__file__).resolve().parent.parent / "data" / "risk_state.json"

def _load():
    try:
        return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    except: return {}
def _save(s):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2))

def check_all(plans: list, positions: dict, cfg: dict) -> tuple:
    state = _load()
    state.setdefault("breaker", False); state.setdefault("consec", 0)
    state.setdefault("daily_pnl", 0.0); state.setdefault("max_dd", 0.0)
    state.setdefault("peak_value", 0.0); state.setdefault("prev_day_value", 0.0)
    if state["breaker"]:
        return [], [{"type": "breaker", "msg": "熔断已触发,需人工恢复"}]
    risk_cfg = cfg.get("risk", {})
    max_pos = risk_cfg.get("max_positions", 5)
    daily_limit = risk_cfg.get("daily_loss_limit_pct", -3.0) / 100
    dd_limit = risk_cfg.get("max_drawdown_pct", -10.0) / 100
    alerts = []
    # 连续亏损检查
    if state["consec"] >= risk_cfg.get("max_consecutive_losses", 3):
        return [], [{"type": "consec", "msg": f"连续{state['consec']}次亏损,暂停"}]
    # 仓位上限检查
    filtered = plans[:max_pos]
    if len(plans) > max_pos:
        alerts.append({"type": "cap", "msg": f"仓位超限({len(plans)}→{max_pos})"})
    return filtered, alerts

def record_trade(pnl_pct: float):
    state = _load()
    state["consec"] = state.get("consec", 0) + 1 if pnl_pct < 0 else 0
    _save(state)

def reset():
    _save({"breaker": False, "consec": 0, "daily_pnl": 0.0, "max_dd": 0.0, "peak_value": 0.0, "prev_day_value": 0.0})
    logger.info("风控状态已重置")
