# -*- coding: utf-8 -*-
"""P0-① 回测强势池预筛单测（2026-08-16）.

验证 prev_close_strategy._strong_pool_gate + screening/strong_stock.score_strong_kline:
- 权重蓝筹(601318 类, 长期阴跌/横盘无动量) → grade D, 非强势池, 被拦。
- 强势成长(300319 类, 上行+动量+涨停基因) → 强势池, 放行。
- gate 口径与实盘 runner.py:166-174 一致: strong_grade∈{A,B} 或 score≥70。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from screening.strong_stock import score_strong_kline  # noqa: E402
import prev_close_strategy as p  # noqa: E402


def _df_from_closes(closes, seed=1):
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    opens = closes * 0.995
    highs = np.maximum(opens, closes) * 1.01
    lows = np.minimum(opens, closes) * 0.99
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n, freq="D"),
        "open": opens, "high": highs, "low": lows,
        "close": closes,
        "volume": np.full(n, 1e6),
    })


def _flat_then_down(n=120):
    """长期横盘/阴跌（权重蓝筹特征）: 无动量、无涨停基因."""
    return [10.0] * (n - 20) + [10.0 - i * 0.01 for i in range(20)]


def _strong_uptrend(n=120):
    """强势上行: MA20上方 + 近20日涨>8% + 近60日≥3次+10%涨停 + 近5日续涨 → A/B级入池。

    chg≥9.5% 判定是单根 close 相对前一根 close 的逐日涨幅, 故"涨停"必须是孤立单根
    相对前收盘 +10%(不是在一个持续变动的序列里算加权). 构造:
      前(n-60)根: 10元平台(均线低);
      近60根: 交替 小阳(2-4%) + 单根+10%涨停(共3根, 涨停之间插入平稳日) + 中间缓涨;
      末尾6根续涨(chg5>0)。整体近20日涨幅>8%。
    """
    closes = [10.0] * (n - 60)          # 平台
    cur = 10.0
    burst = [1.10, 0.99, 1.03, 1.02]    # 每轮: 一根+10%涨停后小回3%再缓涨
    for k in range(3):
        for m in burst:
            cur *= m
            closes.append(cur)
        # 涨停之间插2根缓涨
        cur *= 1.05; closes.append(cur)
        cur *= 1.04; closes.append(cur)
    # 末尾6根续涨
    for m in [1.012, 1.015, 1.018, 1.015, 1.02, 1.022]:
        cur *= m; closes.append(cur)
    return closes


def test_score_strong_weak_flat_bluechip_blocked():
    closes = _flat_then_down()
    r = score_strong_kline(closes)
    assert r["strong"] is False, f"权重蓝筹阴跌应非强势, got {r}"
    assert r["grade"] in ("C", "D")


def test_score_strong_uptrend_passes():
    closes = _strong_uptrend()
    r = score_strong_kline(closes)
    assert r["strong"] is True, f"强势上行应入池, got {r}"
    assert r["grade"] in ("A", "B")


def test_gate_matches_live_threshold_semantics():
    """gate 的 strong 口径 = grade∈{A,B} 或 score≥70（与 runner.py:166-174 同）。"""
    weak = score_strong_kline(_flat_then_down())
    strong = score_strong_kline(_strong_uptrend())
    # weak: 不满足 score≥70
    if weak["score"] >= 70:
        raise AssertionError("阴跌票 score 不应≥70")
    # strong: 满足其一
    assert (strong["grade"] in ("A", "B")) or (strong["score"] >= 70)


def test_strong_pool_gate_uses_strong_kline():
    """_strong_pool_gate 在 df 上调用 score_strong_kline, 返回 (bool, info)."""
    strong_df = _df_from_closes(_strong_uptrend())
    ok, info = p._strong_pool_gate(strong_df)
    assert ok is True and info["decision"] == "pass"
    weak_df = _df_from_closes(_flat_then_down())
    ok2, info2 = p._strong_pool_gate(weak_df)
    assert ok2 is False and info2["decision"] == "not_in_strong_pool"


def test_strong_pool_gate_insufficient_kline_blocked():
    """K线不足(<30根) → 无法判定, 保守按非强势池拦（宁缺毋滥）. """
    small = _df_from_closes([10.0] * 20)
    ok, info = p._strong_pool_gate(small)
    assert ok is False
    assert "K线不足" in info["decision"]
