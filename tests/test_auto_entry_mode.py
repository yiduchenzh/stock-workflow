# -*- coding: utf-8 -*-
"""P0-② 自动买入模式选择单测 (2026-08-16).

验证 _auto_entry_mode 按标的波动/趋势特征自动选买入模式:
- 高波动 + 强趋势 → same_close(当日收盘买, 吃隔夜跳空)
- 低波动 / 弱势 → next_open(次日开盘买, 避免追高)
- 数据不足 → 保守 next_open
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import prev_close_strategy as p  # noqa: E402


def _df(closes, wick_pct=0.02):
    c = np.asarray(closes, dtype=float)
    n = len(c)
    o = c * 0.995
    h = np.maximum(o, c) * (1 + wick_pct)   # 实体宽度可调(默认2%高波动)
    l = np.minimum(o, c) * (1 - wick_pct)
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n, freq="B"),
        "open": o, "high": h, "low": l, "close": c,
        "volume": np.full(n, 1e6),
    })


def _high_vol_trend(n=120):
    """高波动 + 强趋势: 近乎单调上行 + 大实体 → same_close."""
    base = [10.0] * (n - 40) + [10.0 * (1.0 + 0.004 * i) for i in range(40)]
    return np.asarray(base, dtype=float)


def _low_vol_flat(n=120):
    """低波动 + 震荡(权重/弱势): 窄幅横盘(Wick 0.3%) → next_open."""
    return np.asarray([10.0 + 0.002 * (1 if i % 2 else -1) for i in range(n)], dtype=float)


def test_high_vol_trend_picks_same_close():
    df = _df(_high_vol_trend())
    mode = p._auto_entry_mode(df)
    assert mode == "same_close", f"高波动强趋势应选当日收盘买, got {mode}"


def test_low_vol_flat_picks_next_open():
    df = _df(_low_vol_flat(), wick_pct=0.003)   # 窄幅K线 → 低ATR
    mode = p._auto_entry_mode(df)
    assert mode == "next_open", f"低波动震荡应选次日开盘买, got {mode}"


def test_insufficient_data_returns_next_open():
    small = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=15, freq="B"),
        "open": np.arange(1, 16) * 1.0, "high": np.arange(1, 16) * 1.02,
        "low": np.arange(1, 16) * 0.98, "close": np.arange(1, 16) * 1.0,
        "volume": np.ones(15) * 1e6,
    })
    assert p._auto_entry_mode(None) == "next_open"
    assert p._auto_entry_mode(small) == "next_open"


def test_real_dispatch_matches_semantic():
    """合成近似技能库实证: 高波动中小票→same_close, 低波动权重→next_open."""
    hi = p._auto_entry_mode(_df(_high_vol_trend()))
    lo = p._auto_entry_mode(_df(_low_vol_flat(), wick_pct=0.003))
    assert hi == "same_close" and lo == "next_open"
