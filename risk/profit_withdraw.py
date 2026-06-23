"""获利提取 — 斯波朗迪: 账户由亏转盈后提取50%利润"""
import json, logging
from pathlib import Path
logger = logging.getLogger("aurora.withdraw")
STATE = Path(__file__).resolve().parent.parent / "data" / "withdraw_state.json"

def check_withdraw(account_value: float, initial_capital: float) -> dict:
    state = _load()
    state.setdefault("peak_value", initial_capital)
    state.setdefault("withdrawn_total", 0.0)
    state.setdefault("prev_value", initial_capital)
    profit = account_value - initial_capital
    prev_profit = state["prev_value"] - initial_capital
    peak = state["peak_value"]
    if account_value > peak: state["peak_value"] = account_value
    result = {"should_withdraw": False, "amount": 0.0, "reason": ""}
    if prev_profit <= 0 and profit > initial_capital * 0.05:
        amount = profit * 0.50
        result = {"should_withdraw": True, "amount": round(amount, 2),
                 "reason": f"由亏转盈, 提取50%利润({amount:,.0f})"}
        state["withdrawn_total"] += amount
    elif profit > 0 and account_value < peak * 0.90:
        amount = profit * 0.50
        result = {"should_withdraw": True, "amount": round(amount, 2),
                 "reason": f"峰值回撤>10%, 提取50%利润({amount:,.0f})"}
        state["withdrawn_total"] += amount
    state["prev_value"] = account_value; _save(state)
    return result

# utility: available for future use
def get_total_withdrawn() -> float:
    return _load().get("withdrawn_total", 0.0)

def _load():
    try: return json.loads(STATE.read_text()) if STATE.exists() else {}
    except Exception: return {}
def _save(s):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=2))