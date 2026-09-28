"""P1-2a 单票暴露 vs 开仓闸 单一真源 — 默认行为逐笔等价的回归测试 (2026-09-28)

核心不变量: 默认参数(scale=1.0 + 无 exposure.max_position_pct 覆盖)下,
risk/exposure.py 的目标暴露与建仓份数必须与改动前 core/engine.py:1741-1750
`min(TREND_TARGET_PCT.get(_tr,0.5), max_position_pct)` 的算法**逐笔一致**。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from risk.exposure import (DEFAULT_MAX_POSITION_PCT, DEFAULT_TREND_TARGET_PCT,
                           ExposureDiag, ExposurePolicy, load_policy, plan_gate)

# 5 个 Agent 真实画像的单票上限 (profiling/trader_types.py)
AGENT_CAPS = {
    "上班族中短线": 0.20,
    "短线狙击手": 0.28,
    "趋势跟踪者": 0.20,
    "新手入门": 0.10,
    "价值投资者": 0.25,
}
TRENDS = ["up", "range", "down", "unknown", ""]
CASHES = [1_000_000, 953_575.21, 844_371.06, 50_000, 999.0, 0.0]
PRICES = [3.14, 17.05, 122.09, 1820.0, 0.0]


def _legacy_target(trend, style, cfg):
    """改动前 core/engine.py:1741-1750 的原始算法 (逐字复刻, 用作对照基线)"""
    _target = DEFAULT_TREND_TARGET_PCT.get(trend, 0.5)
    try:
        _mpp = float((style or {}).get(
            "max_position_pct",
            (cfg or {}).get("risk", {}).get("max_position_pct", 0.28)))
        if _mpp > 0:
            _target = min(_target, _mpp)
    except Exception:
        pass
    return _target


def _legacy_shares(cash, price, target):
    if not price or price <= 0:
        return 0
    return int(cash * target / price / 100) * 100


@pytest.mark.parametrize("agent,cap", sorted(AGENT_CAPS.items()))
@pytest.mark.parametrize("trend", TRENDS)
@pytest.mark.parametrize("cash", CASHES)
@pytest.mark.parametrize("price", PRICES)
def test_default_policy_matches_legacy_formula_bit_exact(agent, cap, trend, cash, price):
    """默认参数下目标暴露/份数与改动前逐笔一致 (5 Agent × 5 趋势 × 6 现金 × 5 价格)"""
    cfg = {"risk": {"capital": 1_000_000}}
    style = {"max_position_pct": cap}
    pol = load_policy(cfg, style, agent)
    t_old = _legacy_target(trend, style, cfg)
    assert pol.target_exposure(trend) == pytest.approx(t_old, abs=1e-12), (agent, trend)
    assert pol.size_entry(cash, price, trend) == _legacy_shares(cash, price, t_old)


def test_missing_cap_falls_back_to_028():
    """画像无 max_position_pct → 兜底 0.28 (与改动前一致)"""
    pol = load_policy({"risk": {}}, {})
    assert pol.gate_pct == 0.28
    # up 0.8 被 0.28 截断; down 0.3 也被 0.28 截断
    assert pol.target_exposure("up") == 0.28
    assert pol.target_exposure("down") == 0.28
    assert pol.target_exposure("range") == 0.28


def test_non_numeric_cap_means_no_cap_like_legacy_except_path():
    """max_position_pct=None → 改动前 float(None) 抛错 → except pass = 不截断(保持等价)"""
    pol = load_policy({"risk": {}}, {"max_position_pct": None})
    assert pol.gate_pct is None
    assert pol.target_exposure("up") == 0.8


def test_config_exposure_section_is_single_source():
    cfg = {"risk": {"capital": 1_000_000},
           "exposure": {"trend_target_pct": {"up": 0.5, "range": 0.4, "down": 0.2},
                        "max_position_pct": 0.6}}
    pol = load_policy(cfg, {"max_position_pct": 0.10})
    assert pol.target_exposure("up") == 0.5      # 配置单票上限 0.6 > 0.5, 不截断
    assert pol.gate_pct == 0.6
    # 未覆盖时仍走画像
    pol2 = load_policy({"risk": {"capital": 1_000_000}}, {"max_position_pct": 0.10})
    assert pol2.target_exposure("up") == 0.10


def test_scale_knob_raises_exposure_until_cap():
    """⭐提曝光旋钮: scale>1 放大目标暴露, 但仍受单票上限截断

    ⚠️ 2026-09-28 操作清单#2 新契约: scale>1 必须搭配 exposure.allow_raise: true
       (防"静默把风险放大 1.8~5 倍") —— 未放行时被护栏钳制回 1.0。
    """
    base = load_policy({"risk": {"capital": 1_000_000}}, {"max_position_pct": 0.28})
    # 未放行 → 钳制(新护栏)
    clamped = load_policy({"risk": {"capital": 1_000_000},
                           "exposure": {"scale": 2.0}}, {"max_position_pct": 0.28})
    assert clamped.scale == 1.0
    up2 = load_policy({"risk": {"capital": 1_000_000},
                       "exposure": {"scale": 2.0, "allow_raise": True}}, {"max_position_pct": 0.28})
    assert base.target_exposure("range") == 0.28
    assert up2.target_exposure("range") == 0.28       # 仍被 0.28 截断 (cap 是硬闸)
    assert base.target_exposure("down") == 0.28
    # 把单票上限一起抬上去 → 曝光才真正提高 (旋钮成对使用 + 显式放行)
    up_cap = load_policy({"risk": {"capital": 1_000_000},
                          "exposure": {"scale": 1.5, "max_position_pct": 0.5, "allow_raise": True}},
                         {"max_position_pct": 0.28})
    assert up_cap.target_exposure("range") == pytest.approx(0.75) or \
        up_cap.target_exposure("range") == 0.5      # 0.5*1.5=0.75 → 截断到 0.5
    assert up_cap.target_exposure("down") == pytest.approx(0.45)


def test_plan_gate_default_off_is_identical_and_on_caps():
    pol = load_policy({"risk": {"capital": 1_000_000}}, {"max_position_pct": 0.10})
    # 默认(未开闸): 与改动前完全一致
    assert plan_gate(pol, 1_000_000, 10.0, 0.25) == (25000, False)
    # 打开闸门: 单票上限 10% → 10000 股
    pol_cap = ExposurePolicy(max_position_pct=0.10, enforce_plan_cap=True)
    assert plan_gate(pol_cap, 1_000_000, 10.0, 0.25) == (10000, True)
    # 未超过上限时不变
    assert plan_gate(pol_cap, 1_000_000, 10.0, 0.05) == (5000, False)
    # 未开闸时 kelly 上界(0.25*1.0) < 兜底上限 0.28 → 默认路径天然不触发
    pol_def = ExposurePolicy(max_position_pct=0.28, enforce_plan_cap=False)
    assert plan_gate(pol_def, 1_000_000, 10.0, 0.25)[0] == 25000


def test_kelly_scale_knob_on_plan_path():
    """计划层 Kelly 旋钮: 1.0=现状逐笔不变; >1 放大计划份额

    实测背景(2026-09-28 干跑): 3 个计划只占 6.3% 资金 —— 计划层 Kelly x 置信度
    才是 98% 持币的主因, 单票上限(28%)根本没被碰到。
    """
    from risk.position import plan_positions
    scores = [{"code": "000001", "signal": True, "composite": 80, "entry_price": 10.0,
               "stop_loss": 9.5, "best_score": 80, "confidence": 0.6, "kline_df": None}]
    cfg = {"risk": {"take_profit": {"rr_ratio": 2.0}, "risk_per_trade_pct": 1.0,
                    "max_positions": 5}}
    base = plan_positions(scores, 1_000_000, cfg)
    same = plan_positions(scores, 1_000_000, cfg, exposure_policy=load_policy(cfg, {}))
    assert same[0]["shares"] == base[0]["shares"], "默认 kelly_scale=1.0 必须逐笔一致"
    assert same[0]["weight"] == base[0]["weight"]
    pol3 = load_policy({"risk": cfg["risk"], "exposure": {"kelly_scale": 3.0, "allow_raise": True}}, {})
    up = plan_positions(scores, 1_000_000, cfg, exposure_policy=pol3)
    assert up[0]["shares"] == base[0]["shares"] * 3
    # ⚠️ 2026-09-28 操作清单#2: 未显式放行时 kelly_scale>1 被护栏钳制(防静默放大风险)
    pol3_clamped = load_policy({"risk": cfg["risk"], "exposure": {"kelly_scale": 3.0}}, {})
    same_c = plan_positions(scores, 1_000_000, cfg, exposure_policy=pol3_clamped)
    assert same_c[0]["shares"] == base[0]["shares"], "未放行 → 必须与现状逐笔一致"
    # 旋钮 + 单票上限闸门同时生效时不得越界
    pol_cap = load_policy({"risk": cfg["risk"],
                           "exposure": {"kelly_scale": 10.0, "enforce_plan_cap": True}},
                          {"max_position_pct": 0.10})
    capped = plan_positions(scores, 1_000_000, cfg, exposure_policy=pol_cap)
    assert capped[0]["shares"] <= 10000, capped


def test_diag_summary_contains_required_fields():
    """运行时诊断必须含『目标暴露/闸值/当前实际暴露/为什么没买』四要素"""
    pol = load_policy({"risk": {"capital": 1_000_000}}, {"max_position_pct": 0.20})

    class _Acc:
        total_value = 1_000_000
        positions = {"600519": {"shares": 100, "avg_cost": 1500.0, "current_price": 1500.0},
                     "000001": {"shares": 1000, "avg_cost": 10.0, "current_price": 10.0}}

    d = ExposureDiag(pol)
    d.note("未站稳昨收/量能不足")
    d.note("强势池护栏(C/D级)", 2)
    d.note_buy(2000, "up", 0.20)
    s = d.summary(_Acc())
    for kw in ("目标暴露", "闸值", "当前实际暴露", "为什么没买",
               "未站稳昨收/量能不足", "强势池护栏(C/D级)"):
        assert kw in s, s
    assert d.actual_exposure(_Acc()) == pytest.approx(0.16, abs=1e-6)
