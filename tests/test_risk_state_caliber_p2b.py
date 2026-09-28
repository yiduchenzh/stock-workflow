"""P2b 熔断/净值口径统一 — 回归测试 (2026-09-28)

覆盖:
  ① 净值口径: peak_value/prev_day_value 必须来自真实净值序列(_sane_value 限幅), 不再是 0
  ② 日口径: daily_pnl/consec 跨日自动归零(原实现跨日累加)
  ③ 单位口径: daily_pnl_pct(百分数) 与 daily_pnl(金额) 自洽, 熔断用同单位比较
  ④ 熔断口径: 24h 自动恢复 + record_trade 生产接线
  ⑤ 测试隔离: AURORA_RISK_STATE 指向 tmp, 不碰生产 data/risk_state.json
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import risk.controls as rc


@pytest.fixture(autouse=True)
def _isolate_risk_state(tmp_path, monkeypatch):
    """本文件全部用例只写 tmp 文件(生产 data/risk_state.json 一律不动)"""
    p = tmp_path / "risk_state_test.json"
    monkeypatch.setenv("AURORA_RISK_STATE", str(p))
    yield p


def _read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def test_sane_value_bounds():
    assert rc._sane_value(0, 1_000_000) is None
    assert rc._sane_value(-5, 1_000_000) is None
    assert rc._sane_value(20_529_521.75, 1_000_000) is None      # 08-07 污染点
    assert rc._sane_value(1_000_000, 1_000_000) == 1_000_000
    assert rc._sane_value(953_575.21, 1_000_000) == 953_575.21


def test_net_value_series_is_chronological_and_drops_polluted_point():
    s = rc.net_value_series(1_000_000)
    assert len(s) > 10, f"真实净值样本不足: {len(s)}"
    dates = [d for d, _ in s if d]
    assert dates == sorted(dates), "必须保持时间顺序(否则 prev_day 会取到历史最高点)"
    top = max(v for _, v in s)
    assert top <= 5_000_000, f"污染点未被剔除: {top}"
    assert top >= 900_000


def test_sync_net_value_writes_real_values_not_zero(_isolate_risk_state):
    out = rc.sync_net_value(capital=1_000_000)
    assert out["peak_value"] >= 900_000, out
    assert out["prev_day_value"] > 0, out
    assert out["current_value"] > 0
    assert out["drawdown_pct"] <= 0
    st = _read(_isolate_risk_state)
    assert st["peak_value"] > 0 and st["prev_day_value"] > 0
    assert st["net_value_n_sample"] > 10


def test_reset_no_longer_writes_zero_peak(_isolate_risk_state):
    rc.reset(sync_value=True)
    st = _read(_isolate_risk_state)
    assert st["breaker"] is False and st["consec"] == 0
    assert st["peak_value"] > 0, "reset 不应再把 peak_value 写成 0"


def test_check_all_repairs_zero_peak_from_real_series(_isolate_risk_state):
    """复现事故文件(peak_value=0.0) → check_all 必须现场修好并记录来源"""
    _isolate_risk_state.write_text(json.dumps({
        "breaker": False, "consec": 0, "daily_pnl": -0.1,
        "peak_value": 0.0, "prev_day_value": 0.0}), encoding="utf-8")
    plans, alerts = rc.check_all([{"code": "000001"}], {}, {"risk": {"max_positions": 5}})
    st = _read(_isolate_risk_state)
    assert st["peak_value"] > 0 and st["prev_day_value"] > 0
    assert st["net_value_source"].startswith("pnl_tracker")
    assert len(plans) == 1


def test_daily_pnl_unit_is_self_consistent(_isolate_risk_state):
    rc.record_trade(-0.49, capital=1_000_000)
    rc.record_trade(-0.39)
    st = _read(_isolate_risk_state)
    assert st["daily_pnl_pct"] == pytest.approx(-0.88, abs=1e-6)
    assert st["daily_pnl"] == pytest.approx(-8800.0, abs=1.0)     # 金额 = pct/100×capital
    assert st["consec"] == 2


def test_consec_and_daily_pnl_reset_on_new_day(_isolate_risk_state):
    rc.record_trade(-0.5)
    rc.record_trade(-0.5)
    st = _read(_isolate_risk_state)
    assert st["consec"] == 2
    st["daily_pnl_date"] = "2000-01-01"          # 模拟跨日后的旧状态
    _isolate_risk_state.write_text(json.dumps(st), encoding="utf-8")
    rc.check_all([{"code": "000001"}], {}, {"risk": {"max_positions": 5}})
    st2 = _read(_isolate_risk_state)
    assert st2["consec"] == 0, "跨日必须归零(原实现跨日累加 → 越累越容易熔断)"
    assert st2["daily_pnl"] == 0.0 and st2["daily_pnl_pct"] == 0.0
    assert st2["daily_pnl_date"] != "2000-01-01"


def test_daily_loss_breaker_uses_same_unit(_isolate_risk_state):
    rc.reset()
    rc.record_trade(-5.0, capital=1_000_000)     # -5% 超过画像 daily_loss_limit_pct=-3%
    plans, alerts = rc.check_all([{"code": "000001"}], {},
                                 {"risk": {"max_positions": 5, "daily_loss_limit_pct": -3.0,
                                           "capital": 1_000_000}})
    assert any(a["type"] == "daily_loss" for a in alerts), alerts
    assert _read(_isolate_risk_state)["breaker"] is True


def test_consecutive_loss_breaker_and_24h_auto_recovery(_isolate_risk_state):
    rc.reset()
    for _ in range(3):
        rc.record_trade(-0.3)                     # 当日3连亏 → max_consecutive_losses=3
    plans, alerts = rc.check_all([{"code": "000001"}], {},
                                 {"risk": {"max_positions": 5, "max_consecutive_losses": 3}})
    assert alerts and any(a["type"] == "consec" for a in alerts), alerts
    assert _read(_isolate_risk_state)["breaker"] is True
    # 24h 后自动恢复(事故文件 breaker_time=测试时刻, 超 24h 应自愈)
    st = _read(_isolate_risk_state)
    st["breaker_time"] = time.time() - 90000
    _isolate_risk_state.write_text(json.dumps(st), encoding="utf-8")
    plans2, alerts2 = rc.check_all([{"code": "000001"}], {},
                                   {"risk": {"max_positions": 5, "max_consecutive_losses": 3}})
    assert len(plans2) == 1, f"24h 后应自动恢复: {alerts2}"
    assert _read(_isolate_risk_state)["breaker"] is False


def test_production_risk_state_untouched_by_this_file():
    """本文件不得写生产 data/risk_state.json(路径隔离验证)"""
    prod = Path(__file__).resolve().parent.parent / "data" / "risk_state.json"
    before = prod.read_bytes() if prod.exists() else None
    rc.record_trade(-1.0)
    rc.sync_net_value(capital=1_000_000)
    after = prod.read_bytes() if prod.exists() else None
    assert before == after, "生产 risk_state.json 被测试写入了"
