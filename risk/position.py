
"""仓位计划 — 信号强度→仓位映射 + ATR自适应"""
import logging
logger = logging.getLogger("aurora.position")

def plan_positions(scores: list, capital: float, cfg: dict) -> list:
    risk_cfg = cfg.get("risk", {})
    weights = risk_cfg.get("position_weights", {"strong": 0.30, "normal": 0.20, "weak": 0.10})
    plans = []
    for s in scores:
        if not s.get("signal"): continue
        score = s.get("best_score", s.get("score", 50))
        if score >= 75: w = weights.get("strong", 0.30)
        elif score >= 60: w = weights.get("normal", 0.20)
        else: w = weights.get("weak", 0.10)
        price = s.get("entry_price", s.get("price", 10)) or 10
        shares = max(100, int(capital * w / price / 100) * 100)
        sl = s.get("stop_loss", price * 0.95)
        tp = s.get("take_profit", price * (1 + risk_cfg.get("take_profit", {}).get("rr_ratio", 2.0) * risk_cfg.get("risk_per_trade_pct", 1.0) / 100))
        plans.append({
            "code": s.get("code",""), "name": s.get("name",""), "strategy": s.get("best_strategy",""),
            "entry_price": price, "shares": shares, "weight": w,
            "stop_loss": sl, "take_profit": tp, "score": score,
        })
    return plans
