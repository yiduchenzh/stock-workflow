"""集成测试 — 真实K线数据下的策略管线验证"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests.fixtures.test_data import load_real_kline, load_all_test_data, TEST_CODES
import pandas as pd
import numpy as np
def _make_kline(close):
    c = np.array(close, dtype=float)
    n = len(c)
    o = c * (1 + np.random.uniform(-0.01, 0.01, n))
    o[0] = c[0] * 0.99
    h = np.maximum(c, o) * (1 + np.random.uniform(0, 0.02, n))
    l = np.minimum(c, o) * (1 - np.random.uniform(0, 0.02, n))
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c,
                         "volume": np.ones(n) * 1_000_000})

class TestRealDataStrategies:
    """用真实K线数据测试各策略"""

    @classmethod
    def setup_class(cls):
        cls.data = load_all_test_data(250)
    def test_wave_point_on_600519(self):
        from strategies.runner import _check_wave_point
        df = self.data.get("600519", {}).get("kline")
        if df is not None:
            result = _check_wave_point(df)
            assert isinstance(result, (int, float))
            assert 0 <= result <= 100
        else:
            df = _make_kline([10.0 + i*0.3 for i in range(60)])
            result = _check_wave_point(df)
            assert isinstance(result, (int, float))
    def test_momentum_breakout_on_600519(self):
        from strategies.momentum_breakout import check_momentum_breakout
        df = self.data.get("600519", {}).get("kline")
        if df is not None:
            result = check_momentum_breakout(df)
            assert "signal" in result
            assert "score" in result
    def test_mean_reversion_on_000001(self):
        from strategies.mean_reversion import check_mean_reversion
        df = self.data.get("000001", {}).get("kline")
        if df is not None:
            result = check_mean_reversion(df)
            assert "signal" in result
            assert "score" in result
    def test_naked_k_on_600519(self):
        from strategies.naked_k import naked_k_score
        df = self.data.get("600519", {}).get("kline")
        if df is not None:
            result = naked_k_score(df)
            assert isinstance(result, (int, float))
            assert 0 <= result <= 100
    def test_all_strategies_on_real_data(self):
        """所有4个活跃策略在真实数据上都能运行"""
        from strategies.runner import _check_wave_point, _check_123_rule, _check_ma_breakout
        from strategies.momentum_breakout import check_momentum_breakout
        from strategies.mean_reversion import check_mean_reversion
        from strategies.naked_k import naked_k_score

        fns = {
            "wave_point": lambda df: _check_wave_point(df),
            "momentum": lambda df: check_momentum_breakout(df)["score"],
            "mean_rev": lambda df: check_mean_reversion(df)["score"] if check_mean_reversion(df)["signal"] else 0,
            "naked_k": lambda df: naked_k_score(df),
        }

        for code in TEST_CODES:
            df = self.data.get(code, {}).get("kline")
            if df is None or df.empty:
                continue
            for name, fn in fns.items():
                try:
                    result = fn(df)
                    assert isinstance(result, (int, float))
                    assert 0 <= result <= 100
                except Exception as e:
                    raise AssertionError(f"{name} failed on {code}: {e}")

class TestPipelineOnRealData:
    """用真实K线数据测试analyze_all全线"""

    @classmethod
    def setup_class(cls):
        cls.data = load_all_test_data(250)

    def test_analyze_all_with_real_klines(self):
        from strategies.runner import analyze_all
        candidates = []
        kline_override = {}
        for code, d in self.data.items():
            df = d.get("kline")
            if df is not None and not df.empty:
                candidates.append({
                    "code": code, "name": d["name"],
                    "price": float(df["close"].iloc[-1]),
                })
                kline_override[code] = df

        if not candidates:
            return  # 无真实数据时跳过

        results = analyze_all(candidates, kline_override=kline_override)
        assert len(results) == len(candidates)
        for r in results:
            assert "code" in r
            assert "signal" in r
            assert "best_score" in r
            assert "all_signals" in r
            assert isinstance(r["best_score"], (int, float))
            assert 0 <= r["best_score"] <= 100
    def test_analyze_all_result_structure(self):
        """返回结构完整"""
        from strategies.runner import analyze_all
        kline = self.data.get("600519", {}).get("kline")
        if kline is not None:
            candidates = [{"code": "600519", "name": "茅台", "price": float(kline["close"].iloc[-1])}]
            results = analyze_all(candidates, kline_override={"600519": kline})
            assert len(results) == 1
            r = results[0]
            for key in ["code", "name", "signal", "best_strategy", "best_score", "all_signals"]:
                assert key in r, f"Missing key: {key}"

class TestEvolutionOnRealData:
    """用真实K线数据测试自进化记录"""

    @classmethod
    def setup_class(cls):
        cls.data = load_all_test_data(250)
    def test_record_and_health(self):
        from strategies.evolution import (
            record_signal, record_trade_result, record_regime, record_ic,
            get_strategy_health, get_all_health, compute_ic, compute_half_life
        )
        import os
        f = os.path.join(os.path.dirname(__file__), "..", "data", "strategy_evolution.json")
        backup = None
        if os.path.exists(f):
            import shutil
            backup = f + ".bak"
            shutil.copy2(f, backup)

        try:
            # Run strategy on real data and record
            df = self.data.get("600519", {}).get("kline")
            if df is not None:
                from strategies.momentum_breakout import check_momentum_breakout
                for i in range(20, min(40, len(df))):
                    sub = df.iloc[:i].copy()
                    r = check_momentum_breakout(sub)
                    record_signal("test_real", r["score"])
                    record_ic("test_real", r["score"], 1.0 if r["signal"] else -1.0)
                    record_regime("test_real", "range")
                    record_trade_result("test_real", 0.02 if r["signal"] else -0.01, r["signal"])

                h = get_strategy_health("test_real")
                assert h["status"] in ("new", "warning", "healthy", "critical", "dead")
                all_h = get_all_health()
                assert len(all_h) > 0
        finally:
            if backup and os.path.exists(backup):
                import shutil
                shutil.copy2(backup, f)
                os.remove(backup)
            elif os.path.exists(f):
                os.remove(f)