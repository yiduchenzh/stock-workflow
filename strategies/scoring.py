
"""综合评分 v3.0 — 8维度: 战法30+MTF15+量能15+裸K10+缠论10+流动10+市场5+CS5"""
import logging
logger = logging.getLogger("aurora.score")

def composite_score(analysis: list, market_regime: str, market_score: float) -> list:
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
            "signal": True, "best_strategy": a.get("best_strategy"),
            "kline_df": kline_df,
        }
        # 1. 战法 30%
        strategy_score = a.get("best_score", 0) * 0.30
        
        # 2. MTF共振 15% (不再与趋势重复)
        from strategies.mtf_resonance import check_mtf_resonance
        mtf = check_mtf_resonance(kline_df) if kline_df is not None else {"score": 0}
        mtf_score = mtf.get("score", 0) * 0.15
        
        # 3. 量能 15% — 真实计算换手率+量比
        vol_score = _calc_volume_score(kline_df, a)
        
        # 4. 裸K 10% — 接入完整裸K评分
        from strategies.naked_k import naked_k_score
        nk = naked_k_score(kline_df) if kline_df is not None else 35
        nk_score = nk * 0.10
        
        # 5. 缠论 10%
        from strategies.chan_theory import chan_score
        chan_val = chan_score(kline_df) if kline_df is not None else 40
        chan_score_val = chan_val * 0.10
        
        # 6. 流动性 10% — 真实成交额+换手
        liq_score = _calc_liquidity_score(a)
        
        # 7. 市场适配 5%
        market_adapt = 5 if market_regime.startswith("bull") else (3 if market_regime == "range" else 1)
        
        # 8. CAN SLIM 5%
        cs = a.get("can_slim", 50) * 0.05
        
        total = strategy_score + mtf_score + vol_score + nk_score + chan_score_val + liq_score + market_adapt + cs
        
        # 反身性调整
        from strategies.reflexivity import analyze_reflexivity
        ref = analyze_reflexivity(market_score, market_regime)
        reflex_adj = ref.get("reflexivity_score", 50) / 100
        total *= max(0.5, reflex_adj)
        
        base["composite"] = round(min(total, 100), 1)
        base["score"] = base["composite"]
        base["chan"] = round(chan_val, 0)
        base["nk_score"] = round(nk, 0)
        base["reflexivity"] = ref.get("stage", "")[:20]
        results.append(base)
    
    results.sort(key=lambda x: x["composite"], reverse=True)
    logger.info(f"[Score] {len(results)} scored (Chan+NakedK v2.0 integrated)")
    return results

def _calc_volume_score(kline_df, analysis):
    """量能评分: 换手率+量比+量价关系"""
    if kline_df is None or len(kline_df) < 5: return 7.5
    try:
        vol = kline_df["volume"].values
        close = kline_df["close"].values
        vol_ratio = vol[-1] / (vol[-20:].mean() or 1)
        # 量价八法: 价涨量增=健康
        price_up = close[-1] > close[-5] if len(close) >= 5 else True
        vol_up = vol[-1] > vol[-5] if len(vol) >= 5 else True
        score = 7.5
        if vol_ratio > 2.0: score += 5
        elif vol_ratio > 1.5: score += 3
        elif vol_ratio > 1.0: score += 1
        if price_up and vol_up: score += 2.5  # 量价配合
        return min(score, 15)
    except: return 7.5

def _calc_liquidity_score(analysis):
    """流动性评分: 基于mcap+换手率"""
    mcap = analysis.get("mcap", analysis.get("mcap_yi", 50))
    turnover = analysis.get("turnover", 1.0)
    score = 5
    if 50 <= mcap <= 800: score += 3  # 中等市值流动性最佳
    elif mcap > 800: score += 1
    if turnover > 3: score += 2
    elif turnover > 1: score += 1
    return min(score, 10)
