# -*- coding: utf-8 -*-
"""贝叶斯信念 P1 回归测试 — 修复"评分≥60"当盈亏的伪标签污染.

旧代码(已修复): `core/engine.py` step_evaluate 里用
`outcome = best_score>=60 or confidence>=0.6` 当盈亏喂给 update_belief —— 把
"信号评分"当"真实盈亏", 会错误膨胀策略胜率, 而信念反向影响仓位(get_adjusted_kelly)。

修复目标:
  ① 只在**有真实已平仓盈亏**时调用 update_belief;
  ② outcome 由真实平仓 pnl_pct>0 判定, 而非 best_score/confidence;
  ③ 无真实平仓证据 → 跳过 update_belief(不污染)。

注入方式: monkeypatch 模块级 engine.update_belief 捕获是否被调及 outcome 来源;
用 object.__new__ 构造最小 AuroraEngine 实例(绕开 __init__ 的外部IO/网络依赖)。
"""
import sys
import logging
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import core.engine as engine


class _MockBacktest:
    """替代 get_backtest_engine() 返回对象, 仅需 summary()."""
    def summary(self):
        return "mock-summary"


class _MockAccount:
    """最小账户: 仅暴露 trades 属性(兼容贝叶斯段读取 account.trades)."""
    def __init__(self, trades):
        self.trades = trades


def _mk_calls_capturer(monkeypatch):
    calls = []
    monkeypatch.setattr(engine, "get_backtest_engine", lambda: _MockBacktest())
    monkeypatch.setattr(engine, "get_all_health", lambda: {})
    monkeypatch.setattr(engine, "update_belief",
                        lambda s, o: calls.append((s, o)))
    return calls


def _mk_engine(account, analysis):
    e = object.__new__(engine.AuroraEngine)
    e.log = logging.getLogger("test-bayes")
    e.market_regime = "range"
    e.account = account
    e.analysis = analysis
    return e


# ─────────────────────────── ① 只有真实盈亏才更新 ───────────────────────────
def test_bayes_uses_real_pnl_not_score(monkeypatch):
    """best_score=95+confidence=0.9(旧判 WIN)但真实平仓 pnl_pct=-5(亏损)
    → 修复后必须按真实 pnl 判为 LOSS(False)。Proves 伪标签已被替换。"""
    calls = _mk_calls_capturer(monkeypatch)
    e = _mk_engine(
        _MockAccount([{
            "action": "sell", "code": "600519", "pnl": -500.0,
            "pnl_pct": -5.0, "strategy": "momentum_breakout",
        }]),
        [{"code": "600519", "best_strategy": "momentum_breakout",
          "signal": "buy", "best_score": 95, "confidence": 0.9}],
    )
    e.step_evaluate()
    assert calls == [("momentum_breakout", False)]


def test_bayes_win_when_real_pnl_positive(monkeypatch):
    """真实平仓 pnl_pct>0 → 判 WIN(True); 与评分无关。"""
    calls = _mk_calls_capturer(monkeypatch)
    e = _mk_engine(
        _MockAccount([{
            "action": "sell", "code": "600519", "pnl": 800.0,
            "pnl_pct": 8.0, "strategy": "momentum_breakout",
        }]),
        [{"code": "600519", "best_strategy": "momentum_breakout",
          "signal": "buy", "best_score": 10, "confidence": 0.1}],
    )
    e.step_evaluate()
    assert calls == [("momentum_breakout", True)]


# ─────────────────────────── ③ 无真实盈亏 → 不更新 ───────────────────────────
def test_bayes_skips_when_no_realized_pnl(monkeypatch):
    """账户无真实平仓记录(unrealized/空 trades) → 绝不允许用评分伪标签更新信念。"""
    calls = _mk_calls_capturer(monkeypatch)
    # 无 trades(未平仓), 但 analysis 有高评分信号
    e = _mk_engine(_MockAccount([]),
                   [{"code": "600519", "best_strategy": "momentum_breakout",
                     "signal": "buy", "best_score": 99, "confidence": 0.99}])
    e.step_evaluate()
    assert calls == []  # 无真实盈亏证据 → 跳过 update_belief, 0 次调用


def test_bayes_no_account_skips(monkeypatch):
    """account 为 None(无账户上下文) → 跳过信念更新, 不崩不污染。"""
    calls = _mk_calls_capturer(monkeypatch)
    e = _mk_engine(None,
                   [{"code": "600519", "best_strategy": "naked",
                     "signal": "buy", "best_score": 90, "confidence": 0.9}])
    e.step_evaluate()
    assert calls == []
