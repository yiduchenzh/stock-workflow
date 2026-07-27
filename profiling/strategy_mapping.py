from .trader_types import get_trader_profile, get_screening_config

def get_strategy_weights(profile_name="上班族中短线"):
    return get_trader_profile(profile_name)["strategy_weights"]

def get_risk_params(profile_name="上班族中短线"):
    return get_trader_profile(profile_name)["risk"]

def get_screening_params(profile_name="上班族中短线"):
    """获取分类施策的选股参数"""
    return get_screening_config(profile_name)

def get_engine_config(profile_name="上班族中短线"):
    profile = get_trader_profile(profile_name)
    risk = profile["risk"]
    market = profile["market"]
    return {
        "profile_name": profile_name,
        "profile_code": profile["code"],
        "trader_level": profile["trader_level"],
        "holding_period": profile["holding_period"],
        "primary_kline": profile["primary_kline"],
        "secondary_kline": profile["secondary_kline"],
        "min_kline_days": profile["min_kline_days"],
        "strategy_weights": profile["strategy_weights"],
        "risk": {"capital": 1_000_000, "stop_loss_pct": risk["stop_loss_pct"], "take_profit_pct": risk["take_profit_pct"], "max_position_pct": risk["max_position_pct"], "max_positions": risk["max_positions"], "daily_loss_limit_pct": risk["daily_loss_limit_pct"], "kelly_fraction": risk["kelly_fraction"]},
        "market": {"min_score_to_trade": market["min_score_to_trade"], "min_score_to_full": market["min_score_to_full"], "bear_regime_stop": market["bear_regime_stop"], "scores": {"bull_strong": (70, 100), "bull_weak": (market["min_score_to_full"], 69), "range": (market["min_score_to_trade"], market["min_score_to_full"] - 1), "bear_weak": (25, market["min_score_to_trade"] - 1), "bear_strong": (0, 24)}},
        "coach_style": profile["coach_style"],
        "training_focus": profile["training_focus"],
        "description": profile["description"],
    }

def detect_and_configure(answers=None, profile_name=None):
    from .trader_types import detect_profile_from_answers
    if profile_name is None and answers:
        profile_name = detect_profile_from_answers(answers)
    elif profile_name is None:
        profile_name = "上班族中短线"
    return get_engine_config(profile_name)