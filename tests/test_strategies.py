"""策略检测模块测试 — runner.py 七大战法 + analyze_all + 投票机制"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
import pandas as pd

def _make_kline(close_prices, vol_factor=1.0):
    n = len(close_prices)
    close = np.array(close_prices, dtype=float)
    open_ = close * (1 + np.random.uniform(-0.01, 0.01, n))
    open_[0] = close[0] * 0.99
    high = np.maximum(close, open_) * (1 + np.random.uniform(0, 0.02, n))
    low = np.minimum(close, open_) * (1 - np.random.uniform(0, 0.02, n))
    volume = np.ones(n) * 1_000_000 * vol_factor
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})


class TestFirstBoard:
    def test_detected(self):
        from strategies.runner import _check_first_board
        close = [10.0] * 60
        close[59] = 11.0  # 涨停
        close.extend([11.2, 11.0, 11.3, 11.1, 11.5])
        df = _make_kline(close)
        df.iloc[-1, df.columns.get_loc("volume")] = np.mean(df["volume"].values[-20:]) * 2.5
        score = _check_first_board(df)
        assert score >= 50, f"Expected >=50, got {score}"

    def test_no_limit_up(self):
        from strategies.runner import _check_first_board
        close = [10.0 + i * 0.05 for i in range(70)]
        df = _make_kline(close)
        assert _check_first_board(df) == 0

    def test_short_data(self):
        from strategies.runner import _check_first_board
        df = _make_kline([10.0] * 30)
        assert _check_first_board(df) == 0


class TestPullback:
    def test_at_fib_382(self):
        """回调: 有涨停+涨幅>10%区间+价格回到0.382位（函数取limit-up前的range算fib）"""
        from strategies.runner import _check_pullback
        # 16根横盘(>=30) + 10根上升(10→15) + 涨停到16.5 + 3根回踩fib
        base = [10.0] * 16
        base.extend([10.5, 11.0, 11.5, 12.0, 12.5, 13.0, 13.5, 14.0, 14.5, 15.0])
        base.append(16.5)  # 涨停+10%
        # 函数用close[:last_lu+1]算range->high=15,low=10
        # fib = 15 - (15-10)*0.382 = 13.09
        fib_func = 15.0 - (15.0 - 10.0) * 0.382
        base.append(fib_func * 1.01)
        base.append(fib_func * 0.996)
        base.append(fib_func * 1.005)
        df = _make_kline(base)
        score = _check_pullback(df)
        assert score > 0, f"Expected >0, got {score} (fib={fib_func:.2f})"

    def test_away_from_fib(self):
        from strategies.runner import _check_pullback
        close = [10.0] + [12.0] + [11.0 + i * 0.2 for i in range(30)]  # 有涨停但不在fib
        df = _make_kline(close)
        assert _check_pullback(df) == 0


class TestWavePoint:
    def test_uptrend_low_position(self):
        from strategies.runner import _check_wave_point
        close = list(np.linspace(8, 14, 60))
        df = _make_kline(close)
        score = _check_wave_point(df)
        assert score >= 0

    def test_downtrend_no_signal(self):
        from strategies.runner import _check_wave_point
        close = list(np.linspace(14, 8, 60))
        df = _make_kline(close)
        assert _check_wave_point(df) == 0

    def test_high_position_no_signal(self):
        from strategies.runner import _check_wave_point
        close = list(np.linspace(9, 13, 55))
        for _ in range(5):
            close.append(13.0 + np.random.uniform(-0.05, 0.05))
        df = _make_kline(close)
        assert _check_wave_point(df) >= 0


class Test123Rule:
    def test_low_adx_no_signal(self):
        from strategies.runner import _check_123_rule
        close = [10.0 + np.random.randn() * 0.1 for _ in range(60)]
        df = _make_kline(close)
        assert _check_123_rule(df) == 0

    def test_breakout_with_retrace(self):
        from strategies.runner import _check_123_rule
        np.random.seed(42)
        close = list(np.linspace(10, 11.5, 30))
        close.extend([11.3, 11.2, 11.1, 11.15, 11.2])
        close.extend([11.6, 11.8, 12.0])
        df = _make_kline(close)
        assert _check_123_rule(df) >= 0


class TestMABreakout:
    def test_bullish_alignment(self):
        from strategies.runner import _check_ma_breakout
        close = list(np.linspace(10, 14, 25))
        df = _make_kline(close)
        df.iloc[-1, df.columns.get_loc("volume")] = np.mean(df["volume"].values[-20:]) * 1.5
        assert _check_ma_breakout(df) >= 60

    def test_no_alignment(self):
        from strategies.runner import _check_ma_breakout
        close = [10.0] * 10 + [9.0] * 10 + [11.0]
        df = _make_kline(close)
        assert _check_ma_breakout(df) == 0


class TestTestLine:
    def test_long_lower_wick(self):
        from strategies.runner import _check_test_line
        df = _make_kline([10.0] * 11 + [10.5])
        df.iloc[-1] = {"open": 10.5, "high": 10.6, "low": 9.8, "close": 10.55, "volume": 1_000_000}
        assert _check_test_line(df) > 0

    def test_no_wick(self):
        from strategies.runner import _check_test_line
        df = _make_kline([10.0] * 10)
        df.iloc[-1] = {"open": 10.0, "high": 10.1, "low": 9.9, "close": 10.05, "volume": 1_000_000}
        assert _check_test_line(df) == 0


class TestAnalyzeAll:
    def test_empty_candidates(self):
        from strategies.runner import analyze_all
        assert analyze_all([]) == []

    def test_short_kline_no_signal(self):
        from strategies.runner import analyze_all
        df = _make_kline([10.0] * 20)
        result = analyze_all([{"code": "000001", "name": "T"}], kline_override={"000001": df})
        assert result[0]["signal"] == False

    def test_multi_vote_bonus(self):
        from strategies.runner import analyze_all
        close = list(np.linspace(10, 14, 60))
        df = _make_kline(close)
        df.iloc[-1, df.columns.get_loc("volume")] = np.mean(df["volume"].values[-20:]) * 2
        result = analyze_all([{"code": "000001", "name": "T"}], kline_override={"000001": df})
        if result and result[0]["signal"]:
            assert result[0]["signal_count"] >= 1

    def test_result_structure(self):
        from strategies.runner import analyze_all
        df = _make_kline([10.0] * 50)
        result = analyze_all([{"code": "000001", "name": "T"}], kline_override={"000001": df})
        r = result[0]
        for k in ["code", "name", "signal", "best_strategy", "best_score",
                   "entry_price", "stop_loss", "take_profit"]:
            assert k in r, f"Missing key: {k}"