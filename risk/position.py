
"""仓位计划 — Kelly公式 + GARCH波动率调整 · 斯波朗迪+索罗斯"""
import logging, numpy as np
logger = logging.getLogger("aurora.position")

def plan_positions(scores: list, capital: float, cfg: dict) -> list:
    risk_cfg = cfg.get("risk", {})
    weights = risk_cfg.get("position_weights", {"strong": 0.30, "normal": 0.20, "weak": 0.10})
    max_pos = risk_cfg.get("max_positions", 5)
    plans = []
    for s in scores[:max_pos * 2]:
        if not s.get("signal"): continue
        score = s.get("composite", s.get("best_score", 50))
        # Kelly公式: f = (p*b - q) / b  简化: p=胜率 b=盈亏比
        win_rate = 0.45 if score >= 75 else (0.38 if score >= 60 else 0.33)
        rr = risk_cfg.get("take_profit", {}).get("rr_ratio", 2.0)
        kelly = max(0.01, (win_rate * rr - (1 - win_rate)) / rr)
        kelly = min(kelly, 0.25)
        # GARCH波动率调整
        garch_adj = _estimate_volatility(s)
        kelly *= garch_adj
        price = s.get("entry_price", s.get("price", 10)) or 10
        position_capital = capital * kelly
        shares = max(100, int(position_capital / price / 100) * 100)
        # 止损止盈
        sl = s.get("stop_loss", price * (1 - risk_cfg.get("stop_loss", {}).get("hard_pct", 5.0) / 100))
        tp = price * (1 + rr * risk_cfg.get("risk_per_trade_pct", 1.0) / 100)
        plans.append({
            "code": s.get("code",""), "name": s.get("name",""),
            "strategy": s.get("best_strategy",""),
            "entry_price": price, "shares": shares,
            "weight": round(kelly, 3),
            "stop_loss": sl, "take_profit": tp,
            "score": score, "kelly": round(kelly, 3),
        })
        if len(plans) >= max_pos: break
    return plans

def _estimate_volatility(s: dict) -> float:
    """简化GARCH: 高波动率→降仓, 低波动率→加仓"""
    atr_pct = s.get("atr_pct", 2.0)
    if atr_pct < 1.5: return 1.2
    elif atr_pct < 3.0: return 1.0
    elif atr_pct < 5.0: return 0.8
    return 0.6
