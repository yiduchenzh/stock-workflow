"""策略自适应选择器 — 股性×市场×板块 自动匹配交易风格"""
import numpy as np
import logging
logger = logging.getLogger("aurora.selector")

# 交易风格定义
TRADING_STYLES = {
    "trend_follow": {
        "name": "趋势跟踪",
        "strategies": ["ma_breakout", "123_rule", "pullback"],
        "hold_days": "10-30天",
        "stop_atr_mult": 2.5,
        "take_profit_rr": 3.5,
        "position_weight": 0.20,
        "suitable_for": "高波+强趋势+牛市",
    },
    "swing_trade": {
        "name": "波段交易",
        "strategies": ["wave_point", "naked_k", "test_line"],
        "hold_days": "3-10天",
        "stop_atr_mult": 1.8,
        "take_profit_rr": 2.8,
        "position_weight": 0.15,
        "suitable_for": "中波+震荡市+强势板块",
    },
    "momentum": {
        "name": "短线动量",
        "strategies": ["first_board", "naked_k"],
        "hold_days": "1-5天",
        "stop_atr_mult": 1.5,
        "take_profit_rr": 2.2,
        "position_weight": 0.10,
        "suitable_for": "高波+涨停基因+牛市",
    },
    "value_hold": {
        "name": "中长线持有",
        "strategies": ["pullback", "123_rule"],
        "hold_days": "20-60天",
        "stop_atr_mult": 3.0,
        "take_profit_rr": 4.0,
        "position_weight": 0.25,
        "suitable_for": "低波+弱市+防御板块",
    },
    "defensive": {
        "name": "防御观望",
        "strategies": [],
        "hold_days": "空仓",
        "stop_atr_mult": 0,
        "take_profit_rr": 0,
        "position_weight": 0,
        "suitable_for": "大盘极弱",
    },
}

def select_trading_style(market_regime: str, market_score: float,
                          personality: dict, sector_heat: float) -> dict:
    """根据市场+股性+板块 自动选择交易风格
    
    决策逻辑:
    1. 大盘极弱(ms<30) → 防御观望
    2. 高波+强趋势+牛市 → 趋势跟踪
    3. 中波+震荡/弱牛 → 波段交易
    4. 高波+涨停基因+强市 → 短线动量
    5. 低波+弱市 → 中长线持有
    """
    
    # Rule 1: Market crash → defensive
    if market_score < 30:
        return {**TRADING_STYLES["defensive"], "reason": "大盘极弱, 防御观望"}
    
    vol_type = personality.get("type", "mid_vol")
    limit_gene = personality.get("limit_up_gene", "none")
    daily_vol = personality.get("daily_vol", 2.0)
    
    # Rule 2: High vol + bull market + strong trend → trend following
    if market_regime.startswith("bull") and sector_heat > 1.0:
        return {**TRADING_STYLES["trend_follow"], 
                "reason": f"牛市+热板块→趋势跟踪",
                "stop_atr_mult": 2.5, "position_weight": 0.18}
    
    # Rule 3: High vol + limit-up gene + strong market → momentum
    if vol_type in ("high_vol", "mid_vol") and limit_gene in ("strong", "normal") \
       and market_score >= 55 and sector_heat > 1.5:
        return {**TRADING_STYLES["momentum"],
                "reason": f"涨停基因({limit_gene})+强市+热板块→短线动量",
                "position_weight": 0.12}
    
    # Rule 4: Mid vol + range/weak bull → swing trading

    
    # Rule 5: Low vol + any market → value hold
    if vol_type == "low_vol" and market_regime.startswith("bear"):
        return {**TRADING_STYLES["value_hold"],
                "reason": f"低波+弱市→中长线防御",
                "stop_atr_mult": 2.5, "position_weight": 0.15}
    
    # Rule 6: Mid vol + bull strong → trend following
    if market_regime == "bull_strong" and sector_heat > 2.0:
        return {**TRADING_STYLES["trend_follow"],
                "reason": f"强牛市+热板块→趋势跟踪",
                "position_weight": 0.20}
    
    # Default: swing trading
    return {**TRADING_STYLES["swing_trade"],
            "reason": "默认→波段交易",
            "position_weight": 0.10}

def filter_strategies_by_style(analysis: list, style: dict) -> list:
    """按交易风格过滤策略信号"""
    allowed = style.get("strategies", [])
    if not allowed:
        return []  # 防御模式: 不交易
    
    filtered = []
    for a in analysis:
        if not a.get("signal"): continue
        strat = a.get("best_strategy", "")
        if strat in allowed:
            a["trading_style"] = style["name"]
            filtered.append(a)
    
    return filtered

def get_style_params(style: dict) -> dict:
    """提取交易风格的止损/止盈/仓位参数"""
    return {
        "stop_atr_mult": style.get("stop_atr_mult", 2.0),
        "take_profit_rr": style.get("take_profit_rr", 2.0),
        "position_weight": style.get("position_weight", 0.15),
        "style_name": style.get("name", "unknown"),
    }