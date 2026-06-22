
"""市场状态自适应 — regime→策略+参数切换 · 彼得斯分形"""
import logging
logger = logging.getLogger("aurora.regime")

# 每个regime下的活跃策略和参数
REGIME_CONFIG = {
    "bull_strong": {
        "strategies": ["first_board", "pullback", "ma_breakout", "123_rule"],
        "params": {"first_board_lookback": 30, "pullback_ratio": 0.382, "vol_surge": 1.5},
        "max_positions": 5, "kelly_mult": 1.0,
    },
    "bull_weak": {
        "strategies": ["first_board", "pullback", "wave_point", "ma_breakout"],
        "params": {"first_board_lookback": 45, "pullback_ratio": 0.382, "vol_surge": 1.8},
        "max_positions": 4, "kelly_mult": 0.8,
    },
    "range": {
        "strategies": ["wave_point", "test_line", "naked_k"],
        "params": {"first_board_lookback": 60, "pullback_ratio": 0.5, "vol_surge": 2.0},
        "max_positions": 2, "kelly_mult": 0.5,
    },
    "bear_weak": {
        "strategies": ["wave_point"],
        "params": {"first_board_lookback": 90, "pullback_ratio": 0.618, "vol_surge": 2.5},
        "max_positions": 1, "kelly_mult": 0.25,
    },
    "bear_strong": {
        "strategies": [],
        "params": {},
        "max_positions": 0, "kelly_mult": 0.0,
    },
}

def get_regime_config(regime: str) -> dict:
    return REGIME_CONFIG.get(regime, REGIME_CONFIG["range"])

def filter_strategies_by_regime(regime: str, strategies: list) -> list:
    """按市场状态过滤活跃策略"""
    cfg = get_regime_config(regime)
    active = cfg["strategies"]
    return [s for s in strategies if s in active]
