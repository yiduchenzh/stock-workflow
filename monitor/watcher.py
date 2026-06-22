
"""持仓监控 — 止损止盈+移动止盈"""
import json, logging
from pathlib import Path
from data.sources import get_tencent_quotes
logger = logging.getLogger("aurora.watch")

def watch_positions(positions: dict, cfg: dict) -> list:
    if not positions: return []
    codes = list(positions.keys())
    quotes = get_tencent_quotes(codes)
    alerts = []
    risk_cfg = cfg.get("risk", {})
    for code, pos in positions.items():
        q = quotes.get(code, {})
        cur = q.get("price", pos.get("current_price", pos.get("avg_cost", 0)))
        entry = pos.get("avg_cost", cur)
        sl = pos.get("stop_loss", entry * (1 - risk_cfg.get("stop_loss", {}).get("hard_pct", 5.0) / 100))
        tp = pos.get("take_profit", entry * 1.10)
        if cur <= sl:
            alerts.append({"type": "stop_loss", "code": code, "price": cur, "stop": sl})
        elif cur >= tp:
            alerts.append({"type": "take_profit", "code": code, "price": cur, "target": tp})
    return alerts
