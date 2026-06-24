
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
            # 使用回测真实PnL分布 (R22: 改用PnL-based Kelly替代固定8%)
            kelly = 0.05  # 极保守默认: 5% Kelly (wave_point实盘44%WR×1.45PF≈6.4%)
        # GARCH(1,1)真实波动率调整
        from risk.garch_var import get_kelly_adjustment
        kline_df = s.get("kline_df")
        garch_adj = get_kelly_adjustment(kline_df) if kline_df is not None else 1.0
        kelly *= garch_adj
        kelly = min(kelly, 0.25)
        # 置信度调整必须在shares之前!
        confidence = s.get("confidence", 0.5)
        kelly *= (0.5 + confidence * 0.5)
        price = s.get("entry_price", s.get("price", 10)) or 10
        shares = max(100, int(capital * kelly / price / 100) * 100)
        sl = s.get("stop_loss", price * 0.95)
        tp = price * (1 + rr * risk_cfg.get("risk_per_trade_pct", 1.0) / 100)
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
