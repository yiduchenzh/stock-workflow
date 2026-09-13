# -*- coding: utf-8 -*-
"""昨收战法盘中执行器单测（v14.47 与 web auto_trader 执行层一致）"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies.prev_close_executor import (
    analyze_hold, check_entry, trend_state,
    buy_priority_score, rank_buy_priority)


def _bar(hh, mm, o, h, l, c, v=1e6):
    return {"day": f"2026-08-09 {hh}:{mm:02d}", "open": o, "high": h, "low": l, "close": c, "volume": v}


PC = 10.0


def test_check_entry_strong_open():
    m5 = [_bar(9, 30 + i, 10.0, 10.3, 9.9, 10.1) for i in range(3)]
    ok, price = check_entry(m5, PC)
    assert ok and price == 10.1


def test_check_entry_weak_open_rejected():
    m5 = [_bar(9, 30 + i, 10.0, 10.1, 9.8, 9.9) for i in range(3)]
    ok, _ = check_entry(m5, PC)
    assert not ok


def test_trend_state_three_modes():
    up = [10.0 + i * 0.02 for i in range(30)]
    down = [10.6 - i * 0.02 for i in range(30)]
    assert trend_state(up) == "up"
    assert trend_state(down) == "down"
    assert trend_state([10.0] * 30) == "range"


def test_break_clear_5_consecutive_below():
    m5 = [_bar(10, i, 9.8, 9.9, 9.6, 9.7) for i in range(20, 30)]
    sigs, _ = analyze_hold(m5, PC, "range", 1000, 1000, 10.0, True, 0)
    assert "清仓" in [s["action"] for s in sigs]


def test_t0_high_sell_30pct():
    m5 = [_bar(10, i, 10.0, 10.5, 9.95, 10.3) for i in range(12)]
    sigs, t0 = analyze_hold(m5, PC, "up", 1000, 1000, 10.0, True, 0)
    acts = [s["action"] for s in sigs]
    assert "T0高抛" in acts
    assert [s["shares"] for s in sigs if s["action"] == "T0高抛"][0] == 300


def test_add_forbidden_in_down_trend():
    m5 = [_bar(14, i, 10.0, 10.2, 9.98, 10.1, 2e6) for i in range(30)]
    sigs_d, _ = analyze_hold(m5, PC, "down", 1000, 1000, 10.0, True, 0)
    assert "加仓" not in [s["action"] for s in sigs_d]
    sigs_u, _ = analyze_hold(m5, PC, "up", 1000, 1000, 10.0, True, 0)
    assert "加仓" in [s["action"] for s in sigs_u]


def test_stop_loss_9pct_tail():
    # 昨收=10.0, 成本=13.0(浮亏-15.4%≤-9%), 收盘11.0>昨收(不破位), 14:50后
    # 注: 这里显式关跳空熔断(gap_down_stop_pct=0), 专注验证"尾盘止损"路径;
    #     若用默认8%会被开盘跳空(-13.85%)熔断抢先, 那是另一条路径(test_gap_down_*).
    m5 = [_bar(14, 50 + i, 11.2, 11.5, 10.8, 11.0) for i in range(5)]
    sigs, _ = analyze_hold(m5, PC, "range", 1000, 1000, 13.0, True, 0, False, 0)
    assert "止损清仓" in [s["action"] for s in sigs]


def test_add_forbidden_outside_pool():
    m5 = [_bar(14, i, 10.0, 10.2, 9.98, 10.1, 2e6) for i in range(30)]
    sigs, _ = analyze_hold(m5, PC, "up", 1000, 1000, 10.0, False, 0)
    assert "加仓" not in [s["action"] for s in sigs]


# ═══════════ 当时择优分单测（v14.48）═══════════

def _cand(code, score=80, cc=1.5, trend="range", heat=0.0, leader=False,
          industry="半导体", chg=2.0):
    return {
        "code": code, "name": code, "best_score": score,
        "auction": {"cc": cc}, "trend": trend, "sector_heat": heat,
        "is_leader": leader, "industry": industry, "change_pct": chg,
    }


def test_buy_priority_score_weights():
    # 满分样本: 信号95 + CC2.5 + up趋势 + 板块涨5% + 龙头
    s = buy_priority_score(_cand("600000", score=95, cc=2.5, trend="up",
                                 heat=5.0, leader=True))
    # 0.35*0.95 + 0.20*(2.5/3) + 0.15*1 + 0.15*((5+3)/8) + 0.15*1 = 0.3325+0.1667+0.15+0.15+0.15
    assert s == pytest.approx(0.9492, abs=1e-3)
    # 弱样本: 信号60 + CC0.8 + down + 板块跌3% + 非龙头
    w = buy_priority_score(_cand("600001", score=60, cc=0.8, trend="down",
                                 heat=-3.0, leader=False))
    # 0.35*0.6 + 0.20*(0.8/3) + 0.15*0 + 0.15*0 + 0.15*0 = 0.21+0.0533
    assert w == pytest.approx(0.2633, abs=1e-3)
    assert s > w


def test_buy_priority_missing_fields_neutral():
    # 缺 auction/trend/sector_heat/leader 时中性处理, 不崩溃
    c = {"code": "600002", "best_score": 80}
    s = buy_priority_score(c)
    assert 0.0 <= s <= 1.0
    # 缺 best_score 用 score 兜底
    c2 = {"code": "600003", "score": 90, "auction": {"cc": 2.0}}
    s2 = buy_priority_score(c2)
    assert s2 > s


def test_rank_buy_priority_leader_and_cc_win():
    # 同板块两只: 龙头+CC高(即便信号分略低) 应排前
    pool = [
        _cand("600010", score=90, cc=1.2, heat=2.0, industry="半导体", chg=1.5),
        _cand("600011", score=85, cc=2.5, heat=2.0, industry="半导体", chg=4.0),
    ]
    ranked = rank_buy_priority(pool)
    assert ranked[0]["code"] == "600011"          # CC2.5+板块龙头(涨幅4%最高) 胜
    assert ranked[0]["is_leader"] is True
    assert ranked[0]["buy_priority"] > ranked[1]["buy_priority"]
    # 原候选不被修改（返回副本: 新字段只加在副本, 原 is_leader 不被改成 True）
    assert "buy_priority" not in pool[0] and "buy_priority" not in pool[1]
    assert pool[0].get("is_leader") is False


def test_rank_buy_priority_trend_tiebreak():
    # 其余同分时 up 趋势 > down
    pool = [
        _cand("600020", score=80, cc=1.5, trend="up", industry="医药"),
        _cand("600021", score=80, cc=1.5, trend="down", industry="医药"),
    ]
    ranked = rank_buy_priority(pool)
    assert ranked[0]["code"] == "600020"


def test_rank_buy_priority_empty():
    assert rank_buy_priority([]) == []


# ═══════════ P0-② 开盘跳空熔断单测（2026-08-16 治 600363 -19.5%）═══════════

def test_gap_down_open_forces_stop_at_open():
    """开盘价相对成本向下跳空≥8% → 第一根5分K立即触发开盘跳空止损(开盘价成交)."""
    # 成本10.0, 开盘9.0 → 开盘跳空 -10% ≤ -8% → 立即止损(不再等盘中/尾盘)
    m5 = [_bar(9, 30, 9.0, 9.2, 8.8, 9.1) for _ in range(6)]
    sigs, _ = analyze_hold(m5, PC, "range", 1000, 1000, 10.0, True, 0)
    assert [s["action"] for s in sigs] == ["开盘跳空止损"]
    assert sigs[0]["price"] == 9.0          # 按开盘价成交
    assert sigs[0]["shares"] == 1000        # 全部可卖股清仓


def test_gap_down_within_threshold_no_stop():
    """开盘跳空未超阈值(如 -5% < -8%) → 不触发开盘熔断, 走正常盘中逻辑."""
    m5 = [_bar(9, 30, 9.5, 9.7, 9.3, 9.6) for _ in range(6)]
    sigs, _ = analyze_hold(m5, PC, "range", 1000, 1000, 10.0, True, 0)
    acts = [s["action"] for s in sigs]
    assert "开盘跳空止损" not in acts


def test_gap_down_stop_configurable_threshold():
    """阈值可配置: gap_down_stop_pct=6 时 -7% 触发; gap_down_stop_pct=0 关闭."""
    m5 = [_bar(9, 30, 9.3, 9.5, 9.1, 9.4) for _ in range(6)]  # 开盘-7%
    sigs_6, _ = analyze_hold(m5, PC, "range", 1000, 1000, 10.0, True, 0,
                             gap_down_stop_pct=6.0)
    assert "开盘跳空止损" in [s["action"] for s in sigs_6]
    sigs_0, _ = analyze_hold(m5, PC, "range", 1000, 1000, 10.0, True, 0,
                             gap_down_stop_pct=0.0)
    assert "开盘跳空止损" not in [s["action"] for s in sigs_0]
