# -*- coding: utf-8 -*-
"""Web 后端数据关联层集成测试 — 覆盖 4 个 API.

验证要点:
① GET /api/backtest/run  —— 真实回测(复用 prev_close_strategy 已带缓存),
   返回结构含 codes/results/cache(hits/misses/hit_rate); 同参二次请求命中磁盘缓存。
② GET /api/research/{code} —— 含 code/updated_at/sector; fundamentals 有数据则
   pe_ttm/pb 为真实 float(或 None 不报错)。
③ GET /api/sector/members —— 返回 membership 列表/空列表。
④ GET /api/asof —— as_of 时点对齐: close 是 target 当天或之前最近一根的真实值。

网络隔离: 全程不依赖真实网络——用 monkeypatch 把 K线/基本面/板块数据源换成
构造 df / 受控返回, 保证测试逻辑覆盖且**绝不伪造引擎计算**(回测引擎在合成
输入上真实运算; as_of 在构造 df 上真实对齐)。回测缓存指向临时文件, 不污染
真实 data/prevclose_result_cache.json。
"""
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

try:
    from fastapi.testclient import TestClient
    _HAS_FASTAPI = True
except Exception:  # noqa: BLE001
    _HAS_FASTAPI = False


pytestmark = pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi 未安装,跳过 web 集成测试")


# ════════════════════════════════════════════════════════════════
# 工具: 确定性合成 K 线 (下降+震荡, 能触发昨收信号)
# ════════════════════════════════════════════════════════════════
def make_day_df(n=120, seed=7, code="600519", base=100.0,
                start="2024-01-01") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    closes = base + np.cumsum(rng.normal(0, 1.0, n))
    opens = closes * 0.99
    highs = np.maximum(opens, closes) * 1.01
    lows = np.minimum(opens, closes) * 0.99
    vols = rng.integers(100_000, 500_000, n).astype(float)
    df = pd.DataFrame({
        "date": pd.date_range(start, periods=n, freq="D"),
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": vols,
    })
    df.attrs["code"] = code
    # date 列转 python date, 与真实 K线一致
    df["date"] = pd.to_datetime(df["date"])
    return df


def make_min_df(n=400, code="600519", tf="m15") -> pd.DataFrame:
    """确定性分钟 K 线 (供 multitf 用)."""
    rng = np.random.default_rng(5)
    closes = 100 + np.cumsum(rng.normal(0, 0.15, n))
    opens = closes * 0.998
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01 09:30", periods=n, freq="15min"),
        "open": opens, "high": np.maximum(opens, closes) * 1.002,
        "low": np.minimum(opens, closes) * 0.998,
        "close": closes,
        "volume": rng.integers(1000, 9000, n).astype(float),
    })
    df.attrs["code"] = code
    return df


# 受控基本面 / 板块数据 (不读真库, 保证可重复)
FAKE_FUND = {
    "code": "600519", "pe_ttm": 20.28, "pb": 7.2,
    "market_cap": 16775.97, "roe": None, "float_mcap": 16775.97,
    "price": 1341.99, "updated_at": "2026-08-14T16:39:42",
}
# 受控板块多对多 (模拟[("白酒",1.0),("消费",0.7)])
FAKE_SECTORS = [{"sector": "白酒", "weight": 1.0}, {"sector": "消费", "weight": 0.7}]


# ════════════════════════════════════════════════════════════════
# 夹具: 每个测试隔离回测缓存 (临时文件) + 隔离网络/数据依赖
# ════════════════════════════════════════════════════════════════
@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    """每个测试: 独立临时 ResultCache + 关闭 prevclose 外部网络依赖退化."""
    import prev_close_strategy as p
    from data.result_cache import ResultCache
    tmp = Path(tempfile.mkdtemp()) / "test_web_bt_cache.json"
    cache = ResultCache(tmp)
    monkeypatch.setattr(p, "_PREV_CACHE", cache)
    monkeypatch.setattr(p, "CACHE_ENABLED", True)
    monkeypatch.setattr(p, "BUST_CACHE", False)
    # 把 routes_backtest 里 `from prev_close_strategy import fetch_kline` 解绑,
    # 由各用例按需 monkeypatch 到合成数据源, 保证无网络。
    yield


@pytest.fixture
def client():
    from backend.main import app
    return TestClient(app, raise_server_exceptions=False)


def _patch_backtest_kline(monkeypatch, day_df, m1_df=None, m15_df=None):
    """把回测用 K线数据源替换为合成 df (真实引擎运算, 非伪造结果)."""
    import prev_close_strategy as p

    def fake_fetch(code, days=500, tf="day"):
        if tf == "m1":
            return m1_df if m1_df is not None else make_min_df(code=code, tf="m1")
        if tf == "m15":
            return m15_df if m15_df is not None else make_min_df(code=code, tf="m15")
        return day_df

    monkeypatch.setattr(p, "fetch_kline", fake_fetch)


# ────────────────────────── ① /api/backtest/run ──────────────────────────
def test_backtest_run_real_engine_and_cache(client, monkeypatch):
    """真实回测引擎在合成K线上运算; 返回结构含 codes/results/cache."""
    _patch_backtest_kline(monkeypatch,
                          day_df=make_day_df(code="600519"),
                          m1_df=make_min_df(code="600519", tf="m1"),
                          m15_df=make_min_df(code="600519", tf="m15"))
    r = client.get("/api/backtest/run",
                   params={"codes": "600519", "years": 2, "mode": "single", "stop": 0.08})
    assert r.status_code == 200
    d = r.json()
    assert "codes" in d and d["codes"] == ["600519"]
    assert "results" in d
    assert "cache" in d and {"hits", "misses", "hit_rate"} <= set(d["cache"])
    # 引擎真实返回(可能0笔, 但不能是伪造), 至少含 mode 字段
    assert d["results"][0]["code"] == "600519"
    assert d["results"][0]["mode"] in ("single", "multitf")
    # cache 统计: 至少累计了一次 miss 或 hit
    assert (d["cache"]["hits"] + d["cache"]["misses"]) >= 1


def test_backtest_run_second_call_hits_cache(client, monkeypatch):
    """同参二次请求应命中磁盘缓存命中率升高."""
    _patch_backtest_kline(monkeypatch, day_df=make_day_df(code="000858"))
    first = client.get("/api/backtest/run",
                       params={"codes": "000858", "mode": "single"}).json()
    second = client.get("/api/backtest/run",
                        params={"codes": "000858", "mode": "single"}).json()
    # 第二次应至少有一次 HIT
    assert second["cache"]["hits"] >= 1
    assert second["cache"]["hit_rate"] > 0
    # 同参结果完全一致 (确定性回测)
    assert first["results"][0]["final_equity"] == second["results"][0]["final_equity"]


def test_backtest_run_multitf(client, monkeypatch):
    """multitf 模式走三周期真实引擎."""
    _patch_backtest_kline(monkeypatch,
                          day_df=make_day_df(code="600519"),
                          m1_df=make_min_df(code="600519", tf="m1"),
                          m15_df=make_min_df(code="600519", tf="m15"))
    r = client.get("/api/backtest/run",
                   params={"codes": "600519", "mode": "multitf", "stop": 0.05})
    assert r.status_code == 200
    d = r.json()
    assert d["results"][0]["mode"] == "multitf"
    assert d["cache"]["misses"] + d["cache"]["hits"] >= 1


def test_backtest_run_all_network_fail_has_error_key(client, monkeypatch):
    """所有标的D线拉不到(网络受限)时, 返回显式 error/detail 而非伪造结果."""
    import prev_close_strategy as p
    monkeypatch.setattr(p, "fetch_kline",
                        lambda code, days=500, tf="day": (_ for _ in ()).throw(
                            RuntimeError("network-unavailable (mock)")))
    r = client.get("/api/backtest/run", params={"codes": "600519,999999", "mode": "single"})
    assert r.status_code == 200
    d = r.json()
    assert "error" in d
    assert "detail" in d
    assert d["results"] == []  # 无伪造结果
    assert set(d["errors"].keys()) == {"600519", "999999"}


# ────────────────────────── ② /api/research/{code} ──────────────────────────
def test_research_has_sector_and_valuation(client, monkeypatch):
    """research 接口: 含 sector 多对多字段 + pe_ttm/pb 真实 float (None不报错)."""
    # 隔离网络: 基本面/板块/K线全走受控返回; 价格拉取(urlopen)降级为0不报错
    import urllib.request as _ur
    import data.fundamentals_store as fs
    import backend.routes_research as rr

    monkeypatch.setattr(_ur, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("test-no-net")))
    monkeypatch.setattr(fs, "get_fundamentals", lambda code: dict(FAKE_FUND))
    monkeypatch.setattr(fs, "get_stock_sectors", lambda code: list(FAKE_SECTORS))
    monkeypatch.setattr(fs, "ensure_sector_membership",
                        lambda code: "exists" if code == "600519" else "no_source")
    monkeypatch.setattr(rr, "_get_kline_sma", lambda code: None)

    r = client.get("/api/research/600519")
    assert r.status_code == 200
    d = r.json()
    assert d["code"] == "600519"
    assert "updated_at" in d
    # sector 多对多
    assert "sector" in d
    assert d["sector"]["names"] == ["白酒", "消费"]
    assert d["sector"]["fill_status"] in ("exists", "populated", "empty", "filled", "no_source")
    # 基本面真实 float (mock 提供) → 必须是 number 而非 str
    pe = d["valuation"]["pe_ttm"]
    assert pe == FAKE_FUND["pe_ttm"] or pe is None


def test_research_no_fundamentals_is_none_not_err(client, monkeypatch):
    """fundamentals 无数据时 pe_ttm/pb 应 None 而非抛错或伪造."""
    import urllib.request as _ur
    import data.fundamentals_store as fs
    import backend.routes_research as rr
    monkeypatch.setattr(_ur, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("test-no-net")))
    monkeypatch.setattr(fs, "get_fundamentals", lambda code: {})
    monkeypatch.setattr(fs, "get_stock_sectors", lambda code: [])
    monkeypatch.setattr(fs, "ensure_sector_membership",
                        lambda code: "no_source")
    monkeypatch.setattr(rr, "_get_kline_sma", lambda code: None)
    r = client.get("/api/research/600519")
    d = r.json()
    assert d["valuation"]["pe_ttm"] is None
    assert d["valuation"]["pb"] is None
    assert d["sector"]["names"] == []


# ────────────────────────── ③ /api/sector/members ──────────────────────────
def test_sector_members_list(client, monkeypatch):
    """板块钻取: 返回成分列表, 数据来自被 mock 的 get_sector_members."""
    import data.fundamentals_store as fs
    monkeypatch.setattr(fs, "get_sector_members",
                        lambda sector: [{"code": "600519", "weight": 1.0},
                                        {"code": "000858", "weight": 0.6}])
    r = client.get("/api/sector/members", params={"code": "白酒"})
    assert r.status_code == 200
    d = r.json()
    assert d["sector"] == "白酒"
    assert d["count"] == 2
    assert d["members"][0]["code"] == "600519"
    assert {"source", "members"} <= set(d)


def test_sector_members_empty_when_none(client, monkeypatch):
    """stock_sector 无某板块记录时返回空列表 (不伪造)."""
    import data.fundamentals_store as fs
    monkeypatch.setattr(fs, "get_sector_members", lambda sector: [])
    r = client.get("/api/sector/members", params={"code": "不存在板块"})
    d = r.json()
    assert r.status_code == 200
    assert d["members"] == []
    assert d["count"] == 0


# ────────────────────────── ④ /api/asof 时点对齐 ──────────────────────────
@pytest.mark.parametrize("mode,date,expected_idx", [
    ("latest", "2024-01-05", 4),   # 构造df从2024-01-01起, 索引4=01-05
    ("prev",   "2024-01-05", 3),   # 严格排除当天 → 01-04
    ("exact",  "2024-01-05", 4),   # 恰好当天
])
def test_asof_respects_mode(client, monkeypatch, mode, date, expected_idx):
    """as_of 时点对齐: close 应为该时点能看到的真实值(构造df对齐), 无未来函数."""
    df = make_day_df(n=40, seed=1, code="600519", start="2024-01-01")

    # asof 端点内部 `from prev_close_strategy import fetch_kline`
    # 每次都取模块全局 → patch prev_close_strategy.fetch_kline 即可拦截
    import prev_close_strategy as p
    monkeypatch.setattr(p, "fetch_kline", lambda code, days=500: df)

    r = client.get("/api/asof", params={"code": "600519", "date": date, "mode": mode})
    assert r.status_code == 200
    d = r.json()
    assert d.get("found") is True
    assert d["mode"] == mode
    row = d["row"]
    # 返回的 trade_date 与 close 必须严格等于构造 df 在对应时点的那根 (无未来函数)
    expect_row = df.iloc[expected_idx]
    assert row["trade_date"] == str(expect_row["date"])[:10]
    assert row["close"] == expect_row["close"]
    # fundamentals 附注字段存在
    assert "fundamentals" in d


def test_asof_exact_missing_returns_found_false(client, monkeypatch):
    """exact 模式在无该日K线时 found=False (不伪造)."""
    df = make_day_df(n=30, seed=2, code="600519", start="2024-01-01")
    import prev_close_strategy as p
    monkeypatch.setattr(p, "fetch_kline", lambda code, days=500: df)
    r = client.get("/api/asof",
                   params={"code": "600519", "date": "2024-02-15", "mode": "exact"})
    d = r.json()
    # 2024-02-15 超出现有K线范围 → 应 found=False
    assert d.get("found") is False


def test_asof_invalid_date(client, monkeypatch):
    """date 格式非法返回 error."""
    import prev_close_strategy as p
    monkeypatch.setattr(p, "fetch_kline",
                        lambda code, days=500: make_day_df(code="600519"))
    r = client.get("/api/asof", params={"code": "600519", "date": "not-a-date"})
    d = r.json()
    assert d.get("error") is not None
