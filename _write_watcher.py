import sys
# Read the old watcher.py
path = r'D:\Hermes Agent CN Desktop\stock-workflow\monitor\watcher.py'
content = open(path, 'r', encoding='utf-8').read()
print(f'Read {len(content)} bytes')
if 'calc_trailing_stop' in content:
    print('Already updated, skipping')
    sys.exit(0)

# New watcher.py content
new_content = '''"""\u6301\u4ed3\u76d1\u63a7 \u2014 \u6b62\u635f\u6b62\u76c8+\u79fb\u52a8\u6b62\u76c8+\u5206\u6279\u6b62\u76c8"""
import json, logging
from pathlib import Path
from data.sources import get_tencent_quotes
from risk.trailing import calc_trailing_stop, should_scale_out
logger = logging.getLogger("aurora.watch")

# Module-level trailing stop tracking (persisted across watch_positions calls)
_trailing_stops: dict[str, float] = {}

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

        # --- 1. Hard stop loss (most critical) ---
        sl = pos.get("stop_loss", entry * (1 - risk_cfg.get("stop_loss", {}).get("hard_pct", 5.0) / 100))
        if cur <= sl:
            alerts.append({"type": "stop_loss", "code": code, "price": cur, "stop": sl})
            _trailing_stops.pop(code, None)
            continue

        # --- 2. Take profit (full exit target) ---
        tp = pos.get("take_profit", entry * 1.10)
        if cur >= tp:
            alerts.append({"type": "take_profit", "code": code, "price": cur, "target": tp})

        # --- 3. Trailing stop logic (calc_trailing_stop handles 5%/10%/20% tiers) ---
        profit_pct = (cur - entry) / entry * 100
        current_ts = _trailing_stops.get(code, 0.0)
        new_ts = calc_trailing_stop(entry, cur, current_ts)

        if new_ts > current_ts and new_ts > 0:
            _trailing_stops[code] = new_ts
            alerts.append({
                "type": "trailing_stop",
                "code": code,
                "price": cur,
                "trailing_stop": round(new_ts, 4),
                "profit_pct": round(profit_pct, 2)
            })
            logger.info(f"  [Trailing] {code}: stop raised to {new_ts:.4f} (profit {profit_pct:.1f}%)")

        # --- 4. Check breach of trailing stop ---
        if current_ts > 0 and cur <= current_ts:
            alerts.append({
                "type": "breach_stop",
                "code": code,
                "price": cur,
                "trailing_stop": round(current_ts, 4),
                "profit_pct": round(profit_pct, 2)
            })
            logger.warning(f"  [Breach] {code}: price {cur:.4f} hit trailing stop {current_ts:.4f}")
            _trailing_stops.pop(code, None)

        # --- 5. Scale-out suggestion ---
        scale_should, scale_shares = should_scale_out(entry, cur, pos.get("shares", 0))
        if scale_should:
            alerts.append({
                "type": "scale_out",
                "code": code,
                "price": cur,
                "shares_to_sell": scale_shares,
                "profit_pct": round(profit_pct, 2)
            })
            logger.info(f"  [ScaleOut] {code}: sell {scale_shares} shares (profit {profit_pct:.1f}%)")

    return alerts
'''

with open(path, 'w', encoding='utf-8') as f:
    f.write(new_content)
print(f'Wrote {len(new_content)} bytes to watcher.py')
