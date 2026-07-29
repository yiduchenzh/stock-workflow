"""持仓监控 — 止损止盈+移动止盈+分批止盈 (使用executor版SimAccount)"""
import json, logging
from pathlib import Path
from data.sources import get_tencent_quotes
from risk.trailing import calc_trailing_stop, should_scale_out
logger = logging.getLogger("aurora.watch")

_trailing_stops: dict[str, float] = {}

def watch_positions(positions: dict, cfg: dict) -> list:
    """持仓监控 — 止损止盈+移动止盈+分批止盈。整个函数体含异常兜底"""
    try:
        if not positions: return []
        codes = list(positions.keys())
        quotes = get_tencent_quotes(codes)
        alerts = []
        risk_cfg = cfg.get("risk", {})
        # 修复P0: 优先使用profile的stop_loss_pct, 其次才是hard_pct
        profile_sl = risk_cfg.get("stop_loss_pct", None)
        hard_pct = risk_cfg.get("stop_loss", {}).get("hard_pct", 5.0)
        stop_loss_pct = profile_sl if profile_sl is not None else hard_pct
        for code, pos in positions.items():
            q = quotes.get(code, {})
            cur = q.get("price", pos.get("current_price", pos.get("avg_cost", 0)))
            entry = pos.get("avg_cost", cur)

            sl = pos.get("stop_loss", entry * (1 - stop_loss_pct / 100))
            if cur <= sl:
                alerts.append({"type": "stop_loss", "code": code, "price": cur, "stop": sl})
                _trailing_stops.pop(code, None)
                continue

            tp = pos.get("take_profit", entry * 1.10)
            if cur >= tp:
                alerts.append({"type": "take_profit", "code": code, "price": cur, "target": tp})

            profit_pct = (cur - entry) / entry * 100
            current_ts = _trailing_stops.get(code, 0.0)
            new_ts = calc_trailing_stop(entry, cur, current_ts)

            if new_ts > current_ts and new_ts > 0:
                _trailing_stops[code] = new_ts
                alerts.append({
                    "type": "trailing_stop", "code": code,
                    "price": cur, "trailing_stop": round(new_ts, 4),
                    "profit_pct": round(profit_pct, 2)
                })
                logger.info(f"  [Trailing] {code}: stop raised to {new_ts:.4f} (profit {profit_pct:.1f}%)")

            if current_ts > 0 and cur <= current_ts:
                alerts.append({
                    "type": "breach_stop", "code": code,
                    "price": cur, "trailing_stop": round(current_ts, 4),
                    "profit_pct": round(profit_pct, 2)
                })
                logger.warning(f"  [Breach] {code}: price {cur:.4f} hit trailing stop {current_ts:.4f}")
                _trailing_stops.pop(code, None)

        return alerts
    except Exception as e:
        logger.error(f"[Watcher] watch_positions 异常兜底: {e}", exc_info=True)
        return []