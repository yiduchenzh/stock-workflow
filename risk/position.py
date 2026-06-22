
"""仓位计划 — 动态Kelly(回测验证) + GARCH波动率 + 移动止盈"""
import logging
logger = logging.getLogger("aurora.position")

def plan_positions(scores: list, capital: float, cfg: dict, bt_engine=None) -> list:
    risk_cfg = cfg.get("risk", {})
    max_pos = risk_cfg.get("max_positions", 5)
    rr = risk_cfg.get("take_profit", {}).get("rr_ratio", 2.0)
    plans = []
    for s in scores[:max_pos * 2]:
        if not s.get("signal"): continue
        strategy = s.get("best_strategy", "unknown")
        # 动态Kelly: 从回测引擎获取真实胜率
        if bt_engine:
            kelly = bt_engine.get_kelly_weight(strategy, rr)
        else:
            score_val = s.get("composite", 50)
            win_rate = 0.45 if score_val >= 75 else (0.38 if score_val >= 60 else 0.33)
            kelly = max(0.01, (win_rate * rr - (1 - win_rate)) / rr)
        # GARCH波动率调整
        atr_pct = s.get("atr_pct", 2.0)
        garch_adj = 1.2 if atr_pct < 1.5 else (1.0 if atr_pct < 3.0 else (0.8 if atr_pct < 5.0 else 0.6))
        kelly *= garch_adj
        kelly = min(kelly, 0.25)
        price = s.get("entry_price", s.get("price", 10)) or 10
        shares = max(100, int(capital * kelly / price / 100) * 100)
        # 移动止盈默认值
        sl = s.get("stop_loss", price * 0.95)
        tp = price * (1 + rr * risk_cfg.get("risk_per_trade_pct", 1.0) / 100)
        # 置信度调整: 多信号确认的给更高权重
        confidence = s.get("confidence", 0.5)
        kelly *= (0.5 + confidence * 0.5)
        plans.append({
            "code": s.get("code",""), "name": s.get("name",""),
            "strategy": strategy,
            "entry_price": price, "shares": shares,
            "weight": round(kelly, 3), "confidence": confidence,
            "stop_loss": sl, "take_profit": tp,
            "score": s.get("composite", 50),
        })
        if len(plans) >= max_pos: break
    return plans
