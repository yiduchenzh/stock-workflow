
"""综合评分 — 8维度加权 (缠论+MTF+指标+战法)"""
import logging, numpy as np
logger = logging.getLogger("aurora.score")

def composite_score(analysis: list, market_regime: str, market_score: float) -> list:
    """8维度综合评分:
       战法30% + 趋势15% + 量能15% + 流动性10% +
       缠论10% + MTF共振10% + 市场适配5% + CAN SLIM 5%
    """
    results = []
    for a in analysis:
        if not a.get("signal"): continue
        base = {
            "code": a.get("code"), "name": a.get("name"),
            "price": a.get("price", a.get("entry_price", 0)),
            "entry_price": a.get("entry_price", a.get("price", 0)),
            "stop_loss": a.get("stop_loss", a.get("price", 0) * 0.95),
            "take_profit": a.get("take_profit", a.get("price", 0) * 1.10),
            "signal": True,
            "best_strategy": a.get("best_strategy"),
        }
        # 战法得分 (30%)
        strategy_score = a.get("best_score", 0) * 0.30
        # 趋势得分 (15%) — 简化: 用战法质量代理
        trend_score = min(a.get("best_score", 0) * 0.15, 15)
        # 量能得分 (15%) — 简化
        vol_score = 7.5
        # 流动性 (10%)
        liq_score = 5
        # 缠论 (10%) — TODO: 接入chan_theory
        chan_score = 5
        # MTF共振 (10%) — TODO: 接入多周期
        mtf_score = 5
        # 市场适配 (5%)
        market_adapt = 5 if market_regime.startswith("bull") else (3 if market_regime == "range" else 1)
        # CAN SLIM (5%)
        cs = a.get("can_slim", 50) * 0.05
        total = strategy_score + trend_score + vol_score + liq_score + chan_score + mtf_score + market_adapt + cs
        base["composite"] = round(total, 1)
        base["score"] = round(total, 1)
        results.append(base)
    results.sort(key=lambda x: x["composite"], reverse=True)
    logger.info(f"[Score] {len(results)} stocks scored (8 dimensions)")
    return results
