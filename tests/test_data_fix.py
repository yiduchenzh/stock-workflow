# -*- coding: utf-8 -*-
"""数据层 3 个 P0 修复验证 — D-1 基本面自动补拉 / D-2 DCF 去硬编码 / D-3 风险真实计算.

覆盖:
(a) research 首次访问某 code 且落库无该股时, 自动调 refresh_fundamentals 补拉真实值并落库;
    网络受限则返回 None + 日志, 不报错不伪造。
(b) DCF 字段: dcf_value_high/low 必须为 None(未接入真实 DCF 模型), 不再硬编码 round(p*1.3)。
    通过断言接口返回值 + 源码不再含伪造倍率验证。
(c) 风险字段: volatility_20d/var_95/score 基于真实收益/分位算出。
    用确定性合成收盘价调用 _compute_risk_metrics, 断言 volatility==手工 std,
    var≈历史5%分位×价格, score 落在 0-100 且对不同数据非恒定。数据不足返回 None。
(d) refresh_fundamentals 测试用临时 DB(monkeypatch fundamentals_store.DB_PATH), 不污染真实库。
"""
import sys
import os
import math
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pytest

try:
    from fastapi.testclient import TestClient
    _HAS_FASTAPI = True
except Exception:  # noqa: BLE001
    _HAS_FASTAPI = False


@pytest.fixture
def client():
    from backend.main import app
    return TestClient(app, raise_server_exceptions=False)


# ═══════════════════════════════════════════════════════════════════
# (c) 风险指标: 真实计算单元测试 —— 直接测 pure 函数
# ═══════════════════════════════════════════════════════════════════
def _close_series_from_returns(first, daily_returns):
    """按给定日收益率(旧→新)构造收盘价序列(旧→新)."""
    closes = [first]
    for r in daily_returns:
        closes.append(closes[-1] * (1.0 + r))
    return closes


def test_risk_metrics_matches_manual_std_and_percentile():
    """已知收益率序列 → volatility == 手工20日std, var≈历史5%分位×价格."""
    from backend.routes_research import _compute_risk_metrics

    rng = np.random.default_rng(5)
    rets = rng.normal(0, 0.02, 30).tolist()          # 30个日收益, 取最近20算
    closes = _close_series_from_returns(100.0, rets)  # 31根 → 30个收益
    price = 100.0

    out = _compute_risk_metrics(closes, price)
    assert out is not None
    # volatility_20d == 最近20个收益(样本)std × 100
    ret_20 = rets[-20:]
    manual_std = float(np.std(ret_20, ddof=1)) * 100.0
    assert abs(out["volatility_20d"] - round(manual_std, 2)) < 1e-6
    assert out["volatility_20d"] > 0

    # var_95 == max(0, -p5分位) × price(手工5%分位)
    p5 = float(np.percentile(ret_20, 5))
    manual_var = round(max(0.0, -p5) * price, 2)
    assert abs(out["var_95"] - manual_var) < 1e-6
    assert out["var_95"] >= 0

    # score 0-100 且真实非恒定
    assert 0 <= out["score"] <= 100
    assert out["score"] != 65  # 不再是旧硬编码常数


def test_risk_metrics_score_non_constant_across_data():
    """不同波动/回撤数据 → 不同 score(证明非硬编码)."""
    from backend.routes_research import _compute_risk_metrics

    low_vol = _close_series_from_returns(100.0, [0.001] * 40)
    high_vol = _close_series_from_returns(100.0, [0.06, -0.05] * 30)

    s_low = _compute_risk_metrics(low_vol, 100.0)["score"]
    s_high = _compute_risk_metrics(high_vol, 100.0)["score"]
    assert s_low != s_high
    assert 0 <= s_low <= 100 and 0 <= s_high <= 100
    # 高波动风险分应更高
    assert s_high > s_low


def test_risk_metrics_insufficient_data_returns_none():
    """数据不足(收盘价<21 / price<=0) → 各字段 None, 不硬编码."""
    from backend.routes_research import _compute_risk_metrics

    short = _close_series_from_returns(100.0, [0.01, 0.02, 0.015])  # 仅4根
    out = _compute_risk_metrics(short, 100.0)
    assert out["volatility_20d"] is None
    assert out["var_95"] is None
    assert out["score"] is None

    # 空输入 → None
    out2 = _compute_risk_metrics([], 100.0)
    assert out2["score"] is None
    # price<=0 → None
    out3 = _compute_risk_metrics(_close_series_from_returns(100.0, [0.001] * 30), 0)
    assert out3["score"] is None


# ═══════════════════════════════════════════════════════════════════
# (b) DCF 去硬编码
# ═══════════════════════════════════════════════════════════════════
def test_research_dcf_fields_are_none(client, monkeypatch):
    """research 接口的 dcf_value_high/low 必须为 None, 不得再伪造 round(p*1.3)."""
    import urllib.request as _ur
    import data.fundamentals_store as fs
    import backend.routes_research as rr

    monkeypatch.setattr(_ur, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("test-no-net")))
    monkeypatch.setattr(fs, "get_fundamentals", lambda code: {})
    monkeypatch.setattr(fs, "refresh_fundamentals", lambda codes: {})  # 网络受限→空
    monkeypatch.setattr(fs, "get_stock_sectors", lambda code: [])
    monkeypatch.setattr(fs, "ensure_sector_membership", lambda code: "no_source")
    monkeypatch.setattr(rr, "_get_kline_sma", lambda code: None)

    r = client.get("/api/research/600519")
    assert r.status_code == 200
    d = r.json()
    assert d["valuation"]["dcf_value_high"] is None
    assert d["valuation"]["dcf_value_low"] is None
    assert d["valuation"]["pe_ttm"] is None  # 落库无数据 + 网络受限 → 如实 None


def test_dcf_hardcode_removed_from_source():
    # 源码中不得再出现把 DCF 伪装成模型估值输出的硬编码倍率 round(p*1.3/X).
    import backend.routes_research as rr
    src = Path(rr.__file__).read_text(encoding="utf-8")
    compact = src.replace(" ", "").replace("\t", "")
    assert "dcf_value_high" in src                      # 字段仍在(向前兼容前端)
    assert "round(p * 1.3" not in src
    assert "round(p * 0.85" not in src
    # DCF 两字段应被赋值为 None
    assert "dcf_value_high\":None" in compact
    assert "dcf_value_low\":None" in compact


# ═══════════════════════════════════════════════════════════════════
# (a) research 首次访问 → 自动 refresh_fundamentals 补拉并落库
# ═══════════════════════════════════════════════════════════════════
def test_research_first_access_triggers_refresh_and_persists(client, monkeypatch, tmp_path):
    """首次访问: 落库无该股 → 自动 refresh_fundamentals; 拉到则 pe_ttm/pb 为真实 float;
    拉不到(网络受限)则 None, 不报错不伪造."""
    import urllib.request as _ur
    import data.fundamentals_store as fs
    import backend.routes_research as rr

    # 用独立临时 DB, 不污染真实 fundamentals.db
    tmp_db = tmp_path / "fundamentals_fix.db"
    monkeypatch.setattr(fs, "DB_PATH", tmp_db)
    fs.init()

    monkeypatch.setattr(_ur, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("test-no-net")))
    monkeypatch.setattr(fs, "get_stock_sectors", lambda code: [])
    monkeypatch.setattr(fs, "ensure_sector_membership", lambda code: "no_source")
    monkeypatch.setattr(rr, "_get_kline_sma", lambda code: None)

    # 场景1: 网络受限 → refresh_fundamentals 内部降级返回空, 接口 pe_ttm=None 不报错
    def _fail_refresh(codes):
        return {}
    monkeypatch.setattr(fs, "_pull_from_tencent", _fail_refresh)
    r = client.get("/api/research/600519")
    assert r.status_code == 200
    d = r.json()
    assert d["valuation"]["pe_ttm"] in (None,)

    # 场景2: 拉到真实值 → 接口返回真实 float, 且已落库可从 get_fundamentals 读回
    def _ok_refresh(codes):
        return {"600519": {"code": "600519", "pe_ttm": 20.28, "pb": 7.2, "market_cap": 16775.97,
                           "roe": None, "float_mcap": 16775.97, "price": 1341.99}}
    monkeypatch.setattr(fs, "_pull_from_tencent", _ok_refresh)
    r2 = client.get("/api/research/600519")
    assert r2.status_code == 200
    d2 = r2.json()
    assert isinstance(d2["valuation"]["pe_ttm"], float)
    assert isinstance(d2["valuation"]["pb"], float)
    # 已落库: 直接从 store 读回(证明 refresh 已把真实值持久化)
    from_db = fs.get_fundamentals("600519")
    assert from_db and from_db["pe_ttm"] == 20.28


def test_refresh_fundamentals_isolated_tmp_db(monkeypatch, tmp_path):
    """refresh_fundamentals 用临时 DB, 不与真实 fundamentals.db 冲突(test (d))."""
    import data.fundamentals_store as fs

    tmp_db = tmp_path / "fundamentals_iso.db"
    monkeypatch.setattr(fs, "DB_PATH", tmp_db)
    fs.init()

    # 网络受限 → 返回空 dict, 不抛错; 库中无该股
    def _fail(codes):
        return {}
    monkeypatch.setattr(fs, "_pull_from_tencent", _fail)
    out = fs.refresh_fundamentals(["000001"])
    assert out == {}
    assert fs.get_fundamentals("000001") == {}

    # 拉到真实值 → 落库后可读回
    def _ok(codes):
        return {"000001": {"code": "000001", "pe_ttm": 5.01, "pb": 0.47, "market_cap": 2155.96,
                           "roe": None, "float_mcap": 2156.0, "price": 11.11}}
    monkeypatch.setattr(fs, "_pull_from_tencent", _ok)
    out2 = fs.refresh_fundamentals(["000001"])
    assert out2["000001"]["pe_ttm"] == 5.01
    assert fs.get_fundamentals("000001")["pb"] == 0.47
