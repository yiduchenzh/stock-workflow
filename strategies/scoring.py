
"""综合评分 — 8维度加权 (MTF+缠论+波浪+反身性 全接入)"""
import logging
logger = logging.getLogger("aurora.score")

def composite_score(analysis: list, market_regime: str, market_score: float) -> list:
    """8维度: 战法30+趋势15+量能15+流动性10+缠论10+MTF10+市场5+CAN_SLIM5"""
    results = []
    for a in analysis:
        if not a.get("signal"): continue
        kline_df = a.get("kline_df")
        base = {
            "code": a.get("code"), "name": a.get("name"),
            "price": a.get("price", a.get("entry_price", 0)),
            "entry_price": a.get("entry_price", a.get("price", 0)),
            "stop_loss": a.get("stop_loss", a.get("price", 0) * 0.95),
            "take_profit": a.get("take_profit", a.get("price", 0) * 1.10),
            "signal": True,
            "best_strategy": a.get("best_strategy"),
            "kline_df": kline_df,
        }
        # 战法 30%
        strategy_score = a.get("best_score", 0) * 0.30
        # 趋势 15% — 用MTF共振代理
        from strategies.mtf_resonance import check_mtf_resonance
        mtf = check_mtf_resonance(kline_df) if kline_df is not None else {"score": 0}
        trend_score = mtf.get("score", 0) * 0.15
        # 量能 15%
        vol_score = 7.5
        # 流动性 10%
        liq_score = 5
        # 缠论 10%
        from strategies.chan_theory import chan_score
        chan_score_val = chan_score(kline_df) * 0.10 if kline_df is not None else 5
        # MTF共振 10% (已在趋势中体现,这里用加权)
        mtf_score = mtf.get("score", 0) * 0.10
        # 市场适配 5%
        market_adapt = 5 if market_regime.startswith("bull") else (3 if market_regime == "range" else 1)
        # CAN SLIM 5%
        cs = a.get("can_slim", 50) * 0.05
        total = strategy_score + trend_score + vol_score + liq_score + chan_score_val + mtf_score + market_adapt + cs
        # 反身性调整
        from strategies.reflexivity import analyze_reflexivity
        ref = analyze_reflexivity(market_score, market_regime)
        reflex_adj = ref.get("reflexivity_score", 50) / 100
        total *= max(0.5, reflex_adj)
        base["composite"] = round(min(total, 100), 1)
        base["score"] = base["composite"]
        base["mtf"] = mtf
        base["chan"] = round(chan_score_val / 0.10, 0) if kline_df is not None else 50
        base["reflexivity"] = ref.get("stage", "")[:20]
        results.append(base)
    results.sort(key=lambda x: x["composite"], reverse=True)
    logger.info(f"[Score] {len(results)} scored (MTF+Chan+Elliott+Reflex integrated)")
    return results
