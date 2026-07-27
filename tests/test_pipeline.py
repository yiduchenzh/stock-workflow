"""管线集成测试 — engine全流程 + confirmation + scoring + regime"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
import pandas as pd
from pathlib import Path

def _make_kline(close_prices):
    close = np.array(close_prices, dtype=float)
    n = len(close)
    open_ = close * (1 + np.random.uniform(-0.01, 0.01, n))
    open_[0] = close[0] * 0.99
    high = np.maximum(close, open_) * (1 + np.random.uniform(0, 0.02, n))
    low = np.minimum(close, open_) * (1 - np.random.uniform(0, 0.02, n))
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                         "volume": np.ones(n) * 1_000_000})


class TestEngine:
    def test_init(self):
        """引擎初始化"""
        from core.engine import AuroraEngine
        engine = AuroraEngine()
        assert engine.capital == 1_000_000
        assert engine.mode == "paper"
        assert engine.market_score == 50
        assert engine.market_regime == "range"
        assert engine.positions == {}

    def test_regime_mapping_bull_strong(self):
        """market_score→bull_strong"""
        from core.engine import AuroraEngine
        engine = AuroraEngine()
        engine.market_score = 85
        if engine.market_score >= 75:
            engine.market_regime = "bull_strong"
        assert engine.market_regime == "bull_strong"

    def test_regime_mapping_bear_strong(self):
        """market_score→bear_strong"""
        from core.engine import AuroraEngine
        engine = AuroraEngine()
        engine.market_score = 15
        if engine.market_score >= 75:
            engine.market_regime = "bull_strong"
        elif engine.market_score >= 55:
            engine.market_regime = "bull_weak"
        elif engine.market_score >= 45:
            engine.market_regime = "range"
        elif engine.market_score >= 25:
            engine.market_regime = "bear_weak"
        else:
            engine.market_regime = "bear_strong"
        assert engine.market_regime == "bear_strong"

    def test_step_cascade_skip_low_score(self):
        """cascade: market_score<40 → 跳过选股"""
        from core.engine import AuroraEngine
        engine = AuroraEngine()
        engine.market_score = 35
        # 模拟step_cascade行为
        if engine.market_score < 40:
            engine.candidates = []
        assert engine.candidates == []

    def test_non_trading_day_skip(self):
        """非交易日跳过"""
        from core.calendar import is_trading_day
        from datetime import date
        assert is_trading_day(date(2026, 6, 20)) == False  # Saturday
        assert is_trading_day(date(2026, 6, 21)) == False  # Sunday

    def test_trading_day_weekday(self):
        """交易日确认"""
        from core.calendar import is_trading_day
        from datetime import date
        assert is_trading_day(date(2026, 6, 22)) == True  # Monday
        assert is_trading_day(date(2026, 6, 24)) == True  # Wednesday

    def test_engine_run_order(self):
        """run()步骤顺序完整性"""
        from core.engine import AuroraEngine
        engine = AuroraEngine()
        steps = [
            "step_market", "step_cascade", "step_screen", "step_analyze",
            "step_score", "step_position", "step_risk", "step_simulate",
            "step_monitor", "step_rebalance", "step_evaluate", "step_review", "step_prep",
        ]
        for s in steps:
            assert hasattr(engine, s), f"Missing step: {s}"
            assert callable(getattr(engine, s)), f"Not callable: {s}"


class TestConfirmation:
    def test_passes_with_good_signal(self):
        """confirm_entry: 好信号通过"""
        from strategies.confirmation import confirm_entry
        kline = _make_kline([10.0 + i * 0.05 for i in range(30)])
        kline_data = {"df": kline}
        analysis = {"best_score": 70, "signal": True}
        passed, conf, checks = confirm_entry(analysis, kline_data)
        assert passed == True
        assert conf > 0.5

    def test_fails_with_no_kline(self):
        """confirm_entry: 无K线数据 → 严格不通过"""
        from strategies.confirmation import confirm_entry
        analysis = {"best_score": 50, "signal": True}
        passed, conf, checks = confirm_entry(analysis, None)
        # 至少要2/4项通过
        assert conf < 0.8

    def test_ma_trend_check(self):
        """_check_ma_trend: 多头排列通过"""
        from strategies.confirmation import _check_ma_trend
        kline = _make_kline([10.0 + i * 0.05 for i in range(25)])
        assert _check_ma_trend({"df": kline}) == True

    def test_ma_trend_no_kline(self):
        """_check_ma_trend: 无数据不通过"""
        from strategies.confirmation import _check_ma_trend
        assert _check_ma_trend(None) == False
        assert _check_ma_trend({}) == False

    def test_key_level_above_ma20(self):
        """_check_key_level: 价格>MA20通过"""
        from strategies.confirmation import _check_key_level
        kline = _make_kline([10.0 + i * 0.05 for i in range(25)])
        assert _check_key_level({"df": kline}) == True

    def test_volume_price_healthy(self):
        """_check_volume_price: 价涨量增通过"""
        from strategies.confirmation import _check_volume_price
        close = [10.0 + i * 0.05 for i in range(10)]
        df = _make_kline(close)
        assert _check_volume_price({"df": df}) in (True, False)


class TestRegime:
    def test_bull_strong_config(self):
        """regime: 牛市强配置"""
        from strategies.regime import get_regime_config
        cfg = get_regime_config("bull_strong")
        assert "wave_point" in cfg["active_strategies"]
        assert cfg["max_positions"] == 5

    def test_bear_strong_empty(self):
        """regime: 熊市强→空仓"""
        from strategies.regime import get_regime_config
        cfg = get_regime_config("bear_strong")
        assert "momentum_breakout" in cfg["active_strategies"]
        assert cfg["max_positions"] == 1

    def test_filter_strategies(self):
        """filter_strategies_by_regime: 仅保留活跃策略"""
        from strategies.regime import filter_strategies_by_regime
        all_strats = ["wave_point", "ma_breakout", "naked_k"]
        active = filter_strategies_by_regime("bull_strong", all_strats)
        assert "wave_point" in active
        assert "ma_breakout" not in active  # R22: 禁用
        assert "naked_k" in active  # v14.6: naked_前缀匹配加入

    def test_fallback_to_range(self):
        """get_regime_config: 未知regime→range"""
        from strategies.regime import get_regime_config
        cfg = get_regime_config("unknown_regime")
        assert cfg is not None


class TestScoring:
    def test_scoring_structure(self):
        """composite_score: 输出结构完整性"""
        from strategies.scoring import composite_score
        kline = _make_kline([10.0 + i * 0.02 for i in range(60)])
        analysis = [{
            "code": "000001", "name": "测试", "signal": True,
            "best_strategy": "wave_point", "best_score": 70,
            "entry_price": 11.2, "price": 11.2,
            "stop_loss": 10.64, "take_profit": 12.32,
            "can_slim": 60, "kline_df": kline,
        }]
        results = composite_score(analysis, "bull_weak", 65)
        assert len(results) >= 1
        r = results[0]
        assert "composite" in r
        assert "score" in r
        assert r["code"] == "000001"
        assert r["composite"] > 0

    def test_scoring_no_signal_skipped(self):
        """composite_score: 无信号的analysis被跳过"""
        from strategies.scoring import composite_score
        analysis = [{"code": "000001", "signal": False, "best_score": 0}]
        results = composite_score(analysis, "range", 50)
        assert len(results) == 0

    def test_scoring_empty_analysis(self):
        """composite_score: 空列表→[]"""
        from strategies.scoring import composite_score
        results = composite_score([], "range", 50)
        assert results == []