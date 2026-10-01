# -*- coding: utf-8 -*-
"""SAP (stock-analysis-plugin) 数据源接入的确定性契约测试

不依赖网络: 全部用 monkeypatch。
锁定三件事:
  ① get_kline 三级源全失败时, 会真的走到 SAP 兜底 (降级链末端接线正确)
  ② 适配层列序/列名与 data/sources.py 既有源一致 (date/open/close/high/low/volume)
  ③ 桥接层缺失/异常时返回空对象, **不抛异常** (否则会打死主链)
"""
import pandas as pd
import pytest

from data import sap_source
from data import sources


@pytest.fixture(autouse=True)
def _no_shared_cache(monkeypatch):
    """隔离共享缓存: 否则命中缓存就测不到降级链"""
    class _NoCache:
        def get(self, *a, **k):
            return None
        def set(self, *a, **k):
            pass
    import data.shared_cache as sc
    monkeypatch.setattr(sc, "cache", _NoCache(), raising=False)
    monkeypatch.setattr(sap_source, "_PROBED", None, raising=False)
    yield


def _fake_sap_df():
    return pd.DataFrame({
        "date": pd.to_datetime(["2026-09-28", "2026-09-29", "2026-09-30"]),
        "open": [1236.0, 1244.6, 1239.53],
        "close": [1243.88, 1235.58, 1258.62],
        "high": [1244.01, 1245.87, 1268.0],
        "low": [1228.1, 1230.88, 1236.05],
        "volume": [28218.0, 26366.0, 38331.0],
    })


def test_kline_falls_back_to_sap_when_all_primary_sources_fail(monkeypatch):
    """① 降级链末端接线: market.db/TDX/腾讯 全空 → 走 SAP"""
    monkeypatch.setattr(sources, "_get_kline_from_marketdb", lambda *a, **k: None)
    monkeypatch.setattr(sources, "_get_kline_from_tdx", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(sources, "_get_kline_from_tencent", lambda *a, **k: pd.DataFrame())
    called = {}

    def _sap(code, days=250):
        called["code"] = code
        return _fake_sap_df()

    monkeypatch.setattr(sap_source, "get_kline_df", _sap)

    df = sources.get_kline("600519", 3)
    assert called.get("code") == "600519", "未走到 SAP 兜底"
    assert len(df) == 3
    assert float(df["close"].iloc[-1]) == pytest.approx(1258.62)


def test_primary_source_still_wins_when_available(monkeypatch):
    """② 主链优先: 腾讯可用时不得调用 SAP (SAP 只作最后一道)"""
    monkeypatch.setattr(sources, "_get_kline_from_marketdb", lambda *a, **k: None)
    monkeypatch.setattr(sources, "_get_kline_from_tdx", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(sources, "_get_kline_from_tencent",
                        lambda *a, **k: _fake_sap_df().tail(1).reset_index(drop=True))
    hit = {"n": 0}

    def _sap(code, days=250):
        hit["n"] += 1
        return _fake_sap_df()

    monkeypatch.setattr(sap_source, "get_kline_df", _sap)
    df = sources.get_kline("600519", 3)
    assert hit["n"] == 0, "主源可用时不应触碰 SAP"
    assert len(df) == 1


def test_sap_source_column_contract(monkeypatch):
    """③ 列序/列名与既有源一致 (date/open/close/high/low/volume); volume 单位=手"""
    class _B:
        def kline(self, code, count, unit="lots"):
            return {"ok": True, "data": [
                {"date": "2026-09-30", "open": 1239.53, "high": 1268.0,
                 "low": 1236.05, "close": 1258.62, "volume": 38331.0}]}

    monkeypatch.setattr(sap_source, "_get_bridge", lambda: _B())
    df = sap_source.get_kline_df("600519", 1)
    assert list(df.columns) == ["date", "open", "close", "high", "low", "volume"]
    assert pd.api.types.is_datetime64_any_dtype(df["date"])
    # 手 → 股 = ×100 (真值 3,833,100 股)
    assert float(df["volume"].iloc[0]) * 100 == pytest.approx(3833100.0)


def test_adapter_never_raises_when_bridge_missing(monkeypatch):
    """④ 桥接层不可用时全部返回空对象, 不抛异常 (否则会打死主链)"""
    monkeypatch.setattr(sap_source, "_get_bridge", lambda: None)
    df = sap_source.get_kline_df("600519", 3)
    assert isinstance(df, pd.DataFrame) and df.empty
    assert sap_source.get_limit_up_pool() is None
    assert sap_source.get_dragon_tiger() is None
    assert sap_source.get_margin("600519") is None
    assert sap_source.get_hot_stocks() is None
    assert sap_source.is_trading_day("2026-10-01") is None
    assert sap_source.available(force=True) is False
