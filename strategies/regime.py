import logging
logger = logging.getLogger("aurora.regime")
REGIME_CONFIG = {
    "bull_strong": {"strategies": ["ma_breakout", "123_rule", "naked_k"], "params": {}, "max_positions": 5, "kelly_mult": 1.0},
    "bull_weak": {"strategies": ["ma_breakout", "123_rule", "naked_k"], "params": {}, "max_positions": 4, "kelly_mult": 0.8},
    "range": {"strategies": ["naked_k", "ma_breakout", "123_rule"], "params": {}, "max_positions": 3, "kelly_mult": 0.6},
    "bear_weak": {"strategies": ["naked_k"], "params": {}, "max_positions": 1, "kelly_mult": 0.3},
    "bear_strong": {"strategies": [], "params": {}, "max_positions": 0, "kelly_mult": 0.0},
}
def get_regime_config(regime): return REGIME_CONFIG.get(regime, REGIME_CONFIG["range"])
def filter_strategies_by_regime(regime, strategies):
    active = get_regime_config(regime)["strategies"]
    return [s for s in strategies if s in active]
