import logging
logger = logging.getLogger("aurora.regime")
REGIME_CONFIG = {
    # R22最终结论: wave_point为唯一正期望策略(44%WR/PF1.45/+$176K)
    # ma_breakout/123_rule/naked_k全部禁用(回测确认亏损)
    "bull_strong": {"strategies": ["wave_point"], "params": {}, "max_positions": 5, "kelly_mult": 1.0},
    "bull_weak":   {"strategies": ["wave_point"], "params": {}, "max_positions": 3, "kelly_mult": 0.7},
    "range":       {"strategies": [], "params": {}, "max_positions": 0, "kelly_mult": 0.0},
    "bear_weak":   {"strategies": [], "params": {}, "max_positions": 0, "kelly_mult": 0.0},
    "bear_strong": {"strategies": [], "params": {}, "max_positions": 0, "kelly_mult": 0.0},
}
def get_regime_config(regime): return REGIME_CONFIG.get(regime, REGIME_CONFIG["range"])
def filter_strategies_by_regime(regime, strategies):
    active = get_regime_config(regime)["strategies"]
    return [s for s in strategies if s in active]
