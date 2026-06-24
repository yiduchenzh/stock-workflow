import logging
logger = logging.getLogger("aurora.regime")
REGIME_CONFIG = {
    # R24: momentum_breakout (trend-following breakout) + sector_rotation (sector rotation)
    # wave_point (dip-buying) complements momentum_breakout (breakout-chasing)
    # sector_rotation is stock-agnostic, near-zero correlation with all strategies
    "bull_strong": {"strategies": ["wave_point", "momentum_breakout", "mean_reversion", "sector_rotation"],
                    "params": {}, "max_positions": 5, "kelly_mult": 1.0},
    "bull_weak":   {"strategies": ["wave_point", "momentum_breakout", "mean_reversion"],
                    "params": {}, "max_positions": 3, "kelly_mult": 0.7},
    "range":       {"strategies": ["mean_reversion"],
                    "params": {}, "max_positions": 2, "kelly_mult": 0.5},
    "bear_weak":   {"strategies": [], "params": {}, "max_positions": 0, "kelly_mult": 0.0},
    "bear_strong": {"strategies": [], "params": {}, "max_positions": 0, "kelly_mult": 0.0},
}
def get_regime_config(regime): return REGIME_CONFIG.get(regime, REGIME_CONFIG["range"])
def filter_strategies_by_regime(regime, strategies):
    active = get_regime_config(regime)["strategies"]
    return [s for s in strategies if s in active]