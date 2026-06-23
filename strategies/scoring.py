
"""综合评分 v4.0 — MACD背离+KDJ+BOLL+K线组合+涨停板+GARCH"""
import logging
logger = logging.getLogger("aurora.score")

def composite_score(analysis: list, market_regime: str, market_score: float) -> list:
    results = []
    for a in analysis:
        if not a.get("signal"): continue
        kline_df = a.get("kline_df")
        base = _make_base(a, kline_df)
        
        # 1. 战法 25% (下调5%, 给指标系统)
        strategy_score = a.get("best_score", 0) * 0.25
        
        # 2. MTF共振 15%
        from strategies.mtf_resonance import check_mtf_resonance
        mtf = check_mtf_resonance(kline_df) if kline_df is not None else {"score": 0}
        mtf_score = mtf.get("score", 0) * 0.15
        
        # 3. 指标系统 15% (新增: MACD背离+KDJ+BOLL)
        from strategies.indicator_system import indicator_composite_score
        ind_score = indicator_composite_score(kline_df) * 0.15 if kline_df is not None else 7.5
        
        # 4. 量能 10% — 含涨停板分析
        vol_score = _calc_volume_score(kline_df, a)
        
        # 5. 裸K 10%
        from strategies.naked_k import naked_k_score
        nk = naked_k_score(kline_df) if kline_df is not None else 35
        nk_score = nk * 0.10
        
        # 6. 缠论 10%
        from strategies.chan_theory import chan_score
        chan_val = chan_score(kline_df) if kline_df is not None else 40
        chan_score_val = chan_val * 0.10
        
        # 7. 流动性 5%
        liq_score = _calc_liquidity_score(a)
        
        # 8. 市场适配 5%
        market_adapt = 5 if market_regime.startswith("bull") else (3 if market_regime == "range" else 1)
        
        # 9. CAN SLIM 5%
        cs = a.get("can_slim", 50) * 0.05
        
        # K线组合加分项 (独立于权重体系)
        from strategies.kline_patterns import detect_eight_patterns
        eight_p = detect_eight_patterns(kline_df) if kline_df is not None else []
        pattern_bonus = sum(p.get("score", 0) * 0.05 for p in eight_p[:2])  # 取前2个最高分
        
        total = (strategy_score + mtf_score + ind_score + vol_score + nk_score +
                 chan_score_val + liq_score + market_adapt + cs + pattern_bonus)
        
        # GARCH波动率调整
        from risk.garch_var import get_kelly_adjustment
        garch_adj = get_kelly_adjustment(kline_df) if kline_df is not None else 1.0
        total *= garch_adj
        
        # 反身性调整
        from strategies.reflexivity import analyze_reflexivity
        ref = analyze_reflexivity(market_score, market_regime)
        reflex_adj = ref.get("reflexivity_score", 50) / 100
        total *= max(0.5, reflex_adj)
        
        base["composite"] = round(min(total, 100), 1)
        base["score"] = base["composite"]
        base["mtf"] = mtf; base["chan"] = round(chan_val, 0)
        base["nk_score"] = round(nk, 0); base["ind_score"] = round(ind_score/0.15, 0)
        base["patterns"] = [p["type"] for p in eight_p[:2]]
        results.append(base)
    
    results.sort(key=lambda x: x["composite"], reverse=True)
    logger.info(f"[Score v4.0] {len(results)} scored (MACD+KDJ+BOLL+K线组合+GARCH)")
    return results

def _make_base(a, kline_df):
    return {
        "code": a.get("code"), "name": a.get("name"),
        "price": a.get("price", a.get("entry_price", 0)),
        "entry_price": a.get("entry_price", a.get("price", 0)),
        "stop_loss": a.get("stop_loss", a.get("price", 0) * 0.95),
        "take_profit": a.get("take_profit", a.get("price", 0) * 1.10),
        "signal": True, "best_strategy": a.get("best_strategy"),
        "kline_df": kline_df,
    }

def _calc_volume_score(kline_df, _analysis):
    if kline_df is None or len(kline_df) < 5: return 5
    try:
        vol = kline_df["volume"].values; close = kline_df["close"].values
        vol_ratio = vol[-1] / (vol[-20:].mean() or 1)
        price_up = close[-1] > close[-5] if len(close) >= 5 else True
        vol_up = vol[-1] > vol[-5] if len(vol) >= 5 else True
        score = 5
        if vol_ratio > 2.0: score += 3
        elif vol_ratio > 1.5: score += 2
        elif vol_ratio > 1.0: score += 1
        if price_up and vol_up: score += 2  # 量价配合
        # 涨停板加成
        from strategies.kline_patterns import analyze_limit_up
        lu = analyze_limit_up(kline_df) if kline_df is not None else None
        if lu: score += {"A": 4, "B": 3, "C": 1, "D": -2}.get(lu["quality"], 0)
        return min(max(score, 0), 12)
    except Exception: return 5

def _calc_liquidity_score(analysis):
    mcap = analysis.get("mcap", 50); turnover = analysis.get("turnover", 1.0)
    score = 2
    if 50 <= mcap <= 800: score += 2
    elif mcap > 800: score += 0.5
    if turnover > 3: score += 1
    elif turnover > 1: score += 0.5
    return min(score, 5)
