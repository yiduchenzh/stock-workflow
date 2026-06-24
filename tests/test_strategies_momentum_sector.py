"""动量突破 + 板块轮动策略测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
import pandas as pd
from strategies.momentum_breakout import check_momentum_breakout
from strategies.sector_rotation import check_sector_rotation

def _make(close):
    c = np.array(close, dtype=float)
    n = len(c)
    o = c * (1 + np.random.uniform(-0.01, 0.01, n))
    o[0] = c[0] * 0.99
    h = np.maximum(c, o) * (1 + np.random.uniform(0, 0.02, n))
    l = np.minimum(c, o) * (1 - np.random.uniform(0, 0.02, n))
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": np.ones(n) * 1_000_000})

class TestMomentum:
    def test_signal_ok(self):
        df = _make([10 + i*0.3 for i in range(60)])
        df.loc[df.index[-1], "close"] = max(df["high"].iloc[-20:]) * 1.01
        df.loc[df.index[-1], "volume"] = 3_000_000
        r = check_momentum_breakout(df)
        assert r["signal"] == True
        assert r["score"] >= 50
    def test_no_vol(self):
        df = _make([10 + i*0.3 for i in range(60)])
        df.loc[df.index[-1], "close"] = max(df["high"].iloc[-20:]) * 1.01
        r = check_momentum_breakout(df)
        assert r["signal"] == False
    def test_no_high(self):
        df = _make([10 + i*0.05 for i in range(60)])
        r = check_momentum_breakout(df)
        assert r["signal"] == False
    def test_downtrend(self):
        df = _make([20 - i*0.2 for i in range(60)])
        df.loc[df.index[-1], "close"] = max(df["high"].iloc[-20:]) * 1.01
        df.loc[df.index[-1], "volume"] = 3_000_000
        r = check_momentum_breakout(df)
        assert r["signal"] == False
    def test_short_data(self):
        r = check_momentum_breakout(_make([10]*20))
        assert r["signal"] == False
    def test_none(self):
        r = check_momentum_breakout(None)
        assert r["signal"] == False

class TestSector:
    def test_no_data(self):
        r = check_sector_rotation({})
        assert r["signal"] == False
    def test_with_sectors(self):
        kl = {"000001": _make([10 + i*0.2 for i in range(60)])}
        ss = [{"name": "白酒", "change_pct": 3.5, "leader": "000001"},
              {"name": "半导体", "change_pct": 2.1, "leader": "000002"}]
        r = check_sector_rotation(kl, sector_data=ss)
        assert r["signal"] == True
        assert r["sector_rank"] == 1
    def test_no_leader(self):
        kl = {"000999": _make([10 + i*0.2 for i in range(60)])}
        ss = [{"name": "白酒", "change_pct": 3.5, "leader": "000001"}]
        r = check_sector_rotation(kl, sector_data=ss)
        assert r["signal"] == False

class TestRegime:
    def test_has_momentum(self):
        from strategies.regime import get_regime_config
        c = get_regime_config("bull_strong")
        assert "momentum_breakout" in c["strategies"]
    def test_has_sector(self):
        from strategies.regime import get_regime_config
        c = get_regime_config("bull_strong")
        assert "sector_rotation" in c["strategies"]
    def test_range_no_momentum(self):
        from strategies.regime import get_regime_config
        c = get_regime_config("range")
        assert "momentum_breakout" not in c["strategies"]
    def test_filter(self):
        from strategies.regime import filter_strategies_by_regime
        a = filter_strategies_by_regime("bull_strong", ["wave_point", "momentum_breakout", "ma_breakout"])
        assert "momentum_breakout" in a
        assert "wave_point" in a
        assert "ma_breakout" not in a

class TestSectorBacktest:
    def test_with_cached_sector_data(self):
        """sector_rotation用预缓存板块数据可运行"""
        from strategies.sector_rotation import check_sector_rotation
        klines = {"000001": _make([10 + i*0.2 for i in range(60)])}
        sectors = [{"name":"白酒","change_pct":3.5,"leader":"000001"},
                   {"name":"半导体","change_pct":2.0,"leader":"000002"}]
        r = check_sector_rotation(klines, sector_data=sectors)
        assert r["signal"] == True

    def test_no_sector_leader_skips(self):
        """板块领涨股不在候选股中跳过"""
        from strategies.sector_rotation import check_sector_rotation
        klines = {"000999": _make([10 + i*0.2 for i in range(60)])}
        sectors = [{"name":"白酒","change_pct":3.5,"leader":"000001"}]
        r = check_sector_rotation(klines, sector_data=sectors)
        assert r["signal"] == False

    def test_sector_rotation_in_runner(self):
        """sector_rotation从runner.py的analyze_all可调用"""
        from strategies.runner import analyze_all
        candidates = [{"code":"000001","name":"测试","price":12.0}]
        kline_override = {"000001": _make([10 + i*0.2 for i in range(60)])}
        results = analyze_all(candidates, kline_override=kline_override)
        assert len(results) >= 1
        assert "all_signals" in results[0]
