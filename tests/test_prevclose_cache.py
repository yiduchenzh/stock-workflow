# -*- coding: utf-8 -*-
"""prev_close_strategy.py 4个核心回测函数的结果级缓存单测.

验证要点:
(a) 同参(K线不变+参数不变)二次回测命中缓存返回, 且两次结果 dict 相等。
(b) 改 capital/stop_pct 后 miss 且结果不同(至少 key 或 final_equity 不同)。
(c) make_bt_key 对含 df 指纹的 params 稳定; 换不同 K 线段则 key 变化。
(d) BUST_CACHE=True 强制重算不命中(走重算+覆写路径)。

测试全程隔离缓存文件: 用 monkeypatch 把 prev_close_strategy._PREV_CACHE 指向
临时文件, 不污染真实 data/prevclose_result_cache.json。
"""
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import prev_close_strategy as p
from data.result_cache import ResultCache


# ────────────────────────────── 工具 ──────────────────────────────
def make_synthetic_df(n=60, seed=7, code="600519", base=100.0) -> pd.DataFrame:
    """确定性合成日K (下降+震荡足够触发昨收信号)."""
    rng = np.random.default_rng(seed)
    closes = base + np.cumsum(rng.normal(0, 1.0, n))
    opens = closes * 0.99
    highs = np.maximum(opens, closes) * 1.01
    lows = np.minimum(opens, closes) * 0.99
    vols = rng.integers(100_000, 500_000, n).astype(float)
    df = pd.DataFrame({
        "date": pd.date_range("2020-01-01", periods=n, freq="D"),
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": vols,
    })
    df.attrs["code"] = code
    return df


def real_or_synth(n=100, code="000001"):
    """优先拉真实日K; 网络受限则降级为合成 df."""
    try:
        df = p.fetch_kline(code, n, tf="day")
        if df is not None and not df.empty:
            df.attrs["code"] = code
            return p.generate_signals(df)
    except Exception:
        pass
    return p.generate_signals(make_synthetic_df())


@pytest.fixture(autouse=True)
def clean_cache(monkeypatch):
    """每个测试用独立的临时 ResultCache, 保证隔离与可重复."""
    tmp = Path(tempfile.mkdtemp()) / "test_prevclose_cache.json"
    cache = ResultCache(tmp)
    monkeypatch.setattr(p, "_PREV_CACHE", cache)
    # 恢复总开关默认值, 防止上个用例的 BUST/CACHE 状态泄漏
    monkeypatch.setattr(p, "CACHE_ENABLED", True)
    monkeypatch.setattr(p, "BUST_CACHE", False)
    yield cache


# ────────────────────────── (a) 同参命中且结果相等 ──────────────────────────
def test_single_twice_missed_then_hit_equals():
    sd = p.generate_signals(make_synthetic_df())
    r1 = p.backtest_single(sd, capital=100_000)
    stats_after_miss = p._PREV_CACHE.stats()
    r2 = p.backtest_single(sd, capital=100_000)   # 同参 → HIT
    assert r1 == r2
    assert r2["final_equity"] == r1["final_equity"]
    # 第二次命中: hits 增加、misses 不再增加
    stats_after_hit = p._PREV_CACHE.stats()
    assert stats_after_hit["hits"] == stats_after_miss["hits"] + 1
    assert stats_after_hit["misses"] == stats_after_miss["misses"]


def test_minute_twice_missed_then_hit_equals():
    sd = real_or_synth(n=120, code="000001")
    r1 = p.backtest_minute(sd, capital=100_000, bars_per_day=16, stop_pct=0.05)
    r2 = p.backtest_minute(sd, capital=100_000, bars_per_day=16, stop_pct=0.05)
    assert r1 == r2


def test_multitf_twice_missed_then_hit_equals():
    def mk_tf(n, idx0):
        rng = np.random.default_rng(3)
        closes = 100 + np.cumsum(rng.normal(0, 0.5, n))
        opens = closes * 0.99
        d = pd.DataFrame({
            "date": pd.date_range(idx0, periods=n, freq="15min"),
            "open": opens, "high": np.maximum(opens, closes) * 1.01,
            "low": np.minimum(opens, closes) * 0.99,
            "close": closes,
            "volume": rng.integers(1000, 9000, n).astype(float),
        })
        d.attrs["code"] = "600519"
        return d
    dm1 = mk_tf(300, "2020-09-01 09:30")
    dm15 = mk_tf(300, "2020-09-01 09:30")
    dday = make_synthetic_df(n=120)
    dday["date"] = pd.to_datetime(dday["date"])
    r1 = p.backtest_multitf(dm1, dm15, dday, capital=100_000, stop_pct=0.05)
    r2 = p.backtest_multitf(dm1, dm15, dday, capital=100_000, stop_pct=0.05)
    assert r1 == r2


def test_portfolio_twice_missed_then_hit_equals():
    sigs = {
        "600519": p.generate_signals(make_synthetic_df(code="600519")),
        "000858": p.generate_signals(make_synthetic_df(code="000858", base=50.0)),
    }
    r1 = p.backtest_portfolio(sigs, capital=1_000_000, max_positions=3, stop_pct=0.08)
    r2 = p.backtest_portfolio(sigs, capital=1_000_000, max_positions=3, stop_pct=0.08)
    assert r1 == r2


# ────────────────────────── (b) 参数变更 miss 且结果不同 ──────────────────────────
def test_single_capital_change_misses_and_differs():
    sd = p.generate_signals(make_synthetic_df())
    r_base = p.backtest_single(sd, capital=100_000)
    m_before = p._PREV_CACHE.stats()
    r_changed = p.backtest_single(sd, capital=200_000)   # capital 变 → 新 key → MISS
    assert p._PREV_CACHE.stats()["misses"] == m_before["misses"] + 1
    assert r_changed["final_equity"] != r_base["final_equity"]


def test_single_stop_change_misses():
    sd = p.generate_signals(make_synthetic_df())
    p.backtest_single(sd, stop_pct=0.08)
    m_before = p._PREV_CACHE.stats()
    p.backtest_single(sd, stop_pct=0.15)   # stop 变 → MISS
    assert p._PREV_CACHE.stats()["misses"] == m_before["misses"] + 1


# ────────────────────────── (c) make_bt_key 稳定 / df 变化 ──────────────────────────
def test_make_bt_key_stable_with_same_df_and_fp_change_with_diff_df():
    d1 = make_synthetic_df(n=60, seed=7, code="600519")
    d2 = make_synthetic_df(n=80, seed=99, code="600519")   # 不同段
    base = {"mode": "single", "capital": 100_000, "stop_pct": 0.08}
    k1a = p.make_bt_key({**base, "fingerprint": p._df_fingerprint(d1)})
    k1b = p.make_bt_key({**base, "fingerprint": p._df_fingerprint(d1)})
    k2 = p.make_bt_key({**base, "fingerprint": p._df_fingerprint(d2)})
    assert k1a == k1b          # 同 df 稳定
    assert k1a != k2           # 不同 df 变化


def test_change_data_segment_misses():
    """同一函数/参数, 但换成不同 K 线段 → 指纹变 → MISS."""
    sd1 = p.generate_signals(make_synthetic_df(n=60, seed=7))
    p.backtest_single(sd1, capital=100_000)
    m_before = p._PREV_CACHE.stats()
    sd2 = p.generate_signals(make_synthetic_df(n=80, seed=99))
    p.backtest_single(sd2, capital=100_000)
    assert p._PREV_CACHE.stats()["misses"] == m_before["misses"] + 1


# ────────────────── (c2) 指纹内容碰撞: 内部分布不同但和相同必须不同 fp ──────────────────
def test_fingerprint_content_collision_close_distribution():
    """P1 回归: 关闭盘和[10,11] vs [11,10](和均为21)但内部分布不同 → 指纹必须不同。

    旧版用'收盘和'做签名可碰撞, [10,11] 与 [11,10] 和相同会误命中旧缓存返回错结果。
    修复后按 OHLCV 逐行内容 MD5 感知内部顺序分布, 二者指纹必须不同。
    """
    cls1 = [10.0, 11.0]   # 和 21, 先涨后更高
    cls2 = [11.0, 10.0]   # 和 21, 先高后低 —— 内部分布不同
    fp1 = _fingerprint_for_close(cls1)
    fp2 = _fingerprint_for_close(cls2)
    assert fp1 != fp2
    # 同分布(完全相同的 df/相同列含 attrs)则稳定相等
    assert _fingerprint_for_close(cls1) == fp1


def _fingerprint_for_close(closes):
    """构造一个 OHLCV 全相同的两行 df(仅 close 序列按入参), 返回其指纹。"""
    n = len(closes)
    opens = [9.0, 9.5]
    highs = [12.0, 12.5]
    lows = [8.0, 8.5]
    vols = [1000.0, 2000.0]
    d = pd.DataFrame({
        "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
        "open": opens[:n], "high": highs[:n], "low": lows[:n],
        "close": list(closes), "volume": vols[:n],
    })
    d.attrs["code"] = "600519"
    return p._df_fingerprint(d)


# ────────────────────────── (d) 含 df.attrs 代码进 key ──────────────────────────
def test_fingerprint_uses_code_attr():
    d = make_synthetic_df(code="600519")
    fp = p._df_fingerprint(d)
    assert "code:600519" in fp


# ────────────────────────── (e) BUST_CACHE 强制重算不命中 ──────────────────────────
def test_bust_cache_forces_recompute(monkeypatch):
    monkeypatch.setattr(p, "BUST_CACHE", True)
    sd = p.generate_signals(make_synthetic_df(n=60, seed=7))
    r1 = p.backtest_single(sd, capital=100_000)   # 写缓存
    hits_before = p._PREV_CACHE.stats()["hits"]
    # BUST 下再跑: 不查命中(直接重算并覆写), hits 不增加
    r2 = p.backtest_single(sd, capital=100_000)
    assert p._PREV_CACHE.stats()["hits"] == hits_before
    assert r2 == r1
    monkeypatch.setattr(p, "BUST_CACHE", False)


# ────────────────────────── (f) CACHE_DISABLED 直接重算 ──────────────────────────
def test_cache_disabled_runs_without_cache(monkeypatch):
    monkeypatch.setattr(p, "CACHE_ENABLED", False)
    sd = p.generate_signals(make_synthetic_df())
    p.backtest_single(sd, capital=100_000)
    # 关闭缓存时 key 生成被跳过, 不写入; 直接重算返回
    assert p._PREV_CACHE.size() == 0
    monkeypatch.setattr(p, "CACHE_ENABLED", True)
