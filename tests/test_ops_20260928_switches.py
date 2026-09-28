# -*- coding: utf-8 -*-
"""2026-09-28 操作清单 #1/#2 — 两个"显式开关"护栏回归测试

覆盖:
  ① 熔断开关三态 (cfg.risk.breaker_override): auto / freeze / release
     - freeze: 即使 breaker=false 也一律禁开新仓(显式冻结)
     - release: breaker=true 时显式解除并清零 consec/breaker_time
     - auto:   保持现状(未超24h → 拦截)
     - 开关值落盘到 state, 便于事后审计
  ② 提曝光护栏 (cfg.exposure.allow_raise, 默认 false):
     - scale/kelly_scale > 1 且未显式放行 → 钳制回 1.0(防静默放大 1.8~5 倍风险)
     - allow_raise: true → 按配置生效
     - 默认(空 cfg) → 与 2026-09-28 现状逐值一致(历史可比)

隔离: AURORA_RISK_STATE 指向 tmp, 生产 data/risk_state.json 一律不动 (与 test_risk_state_caliber_p2b 同法)
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import risk.controls as rc
from risk.exposure import DEFAULT_TREND_TARGET_PCT, load_policy


@pytest.fixture(autouse=True)
def _isolate_risk_state(tmp_path, monkeypatch):
    p = tmp_path / "risk_state_test.json"
    monkeypatch.setenv("AURORA_RISK_STATE", str(p))
    yield p


def _write_state(p, **kw):
    base = {"breaker": False, "consec": 0, "daily_pnl": 0.0, "daily_pnl_pct": 0.0,
            "breaker_time": 0, "capital": 1_000_000,
            "peak_value": 1_005_097.88, "prev_day_value": 953_575.21}
    base.update(kw)
    Path(p).write_text(json.dumps(base), encoding="utf-8")


def _read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


# ═══════════ ① 熔断开关三态 ═══════════
def test_breaker_freeze_blocks_even_when_not_triggered(_isolate_risk_state):
    _write_state(_isolate_risk_state, breaker=False)
    plans = [{"code": "600000", "shares": 100}]
    ok, alerts = rc.check_all(plans, cfg={"risk": {"breaker_override": "freeze"}})
    assert ok == [] and alerts and alerts[0]["type"] == "breaker"
    assert "freeze" in alerts[0]["msg"]
    assert _read(_isolate_risk_state)["breaker_override"] == "freeze"


def test_breaker_release_clears_stale_breaker(_isolate_risk_state):
    _write_state(_isolate_risk_state, breaker=True, consec=3,
                 breaker_time=time.time() - 3600)          # 1h 前触发 → 未到24h
    plans = [{"code": "600000", "shares": 100}]
    ok, alerts = rc.check_all(plans, cfg={"risk": {"breaker_override": "release"}})
    assert not [a for a in alerts if a.get("type") == "breaker"]      # 不再拦截
    st = _read(_isolate_risk_state)
    assert st["breaker"] is False and st["consec"] == 0 and st["breaker_time"] == 0
    assert st["breaker_override"] == "release"


def test_breaker_auto_keeps_current_behavior(_isolate_risk_state):
    _write_state(_isolate_risk_state, breaker=True, consec=3,
                 breaker_time=time.time() - 3600)
    ok, alerts = rc.check_all([{"code": "600000", "shares": 100}],
                              cfg={"risk": {"breaker_override": "auto"}})
    assert alerts and alerts[0]["type"] == "breaker"                  # 现状: 未超24h → 拦
    assert _read(_isolate_risk_state)["breaker_override"] == "auto"


def test_breaker_override_defaults_to_auto(_isolate_risk_state):
    _write_state(_isolate_risk_state)
    rc.check_all([], cfg={})
    assert _read(_isolate_risk_state)["breaker_override"] == "auto"
    rc.check_all([], cfg={"risk": {"breaker_override": "garbage"}})   # 非法值 → auto
    assert _read(_isolate_risk_state)["breaker_override"] == "auto"


# ═══════════ ② 提曝光护栏 ═══════════
def test_exposure_raise_guard_clamps_by_default():
    pol = load_policy({"exposure": {"scale": 2.0, "kelly_scale": 3.0}})
    assert pol.scale == 1.0 and pol.kelly_scale == 1.0                # 未放行 → 钳制


def test_exposure_raise_allowed_when_explicit():
    pol = load_policy({"exposure": {"scale": 2.0, "kelly_scale": 3.0, "allow_raise": True}})
    assert pol.scale == 2.0 and pol.kelly_scale == 3.0


def test_exposure_defaults_equal_20260928_baseline():
    """缺省必须等于现状(历史可比) —— 这是"默认行为不变"的回归锁

    口径: trend_target_pct 是"原始目标", target_exposure() 会再受单票上限截断 →
          默认 0.8/0.5/0.3 三个趋势值全部被 28% 上限截断为 0.28(与干跑打印一致)。
    """
    pol = load_policy({})
    assert pol.scale == 1.0 and pol.kelly_scale == 1.0
    assert pol.enforce_plan_cap is False and pol.min_cash_reserve_pct == 0.0
    # 原始目标值(未被截断)
    for _t, _v in DEFAULT_TREND_TARGET_PCT.items():
        assert pol.trend_target_pct[_t] == pytest.approx(_v)
    # 生效目标 = min(原始目标, 单票上限)  ← 上限属性名是 gate_pct(_cap)
    assert pol.gate_pct == pytest.approx(0.28)
    for _t in DEFAULT_TREND_TARGET_PCT:
        assert pol.target_exposure(_t) == pytest.approx(min(DEFAULT_TREND_TARGET_PCT[_t], pol.gate_pct))
    assert load_policy({"exposure": {}}).target_exposure("up") == pytest.approx(pol.target_exposure("up"))


def test_exposure_guard_does_not_block_risk_reduction():
    """收紧类旋钮(现金保留/计划层截断)不该被放行护栏挡住"""
    pol = load_policy({"exposure": {"enforce_plan_cap": True, "min_cash_reserve_pct": 0.2}})
    assert pol.enforce_plan_cap is True and pol.min_cash_reserve_pct == pytest.approx(0.2)
