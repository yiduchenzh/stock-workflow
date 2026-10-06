# -*- coding: utf-8 -*-
"""主力缩量信号 (vol_signal) 单元测试

覆盖：主板判定 / 距20日高口径 / enabled 开关 / 命中与拒绝路径 / 打分单调性
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from screening.vol_signal import (  # noqa: E402
    VOL_SIGNAL_DEFAULTS,
    _is_main_board,
    compute_dist_hi,
    scan_vol_signal,
    score_vol_signal,
)


def _kl(close=10.0, high=10.0, n=25):
    return [{"close": close, "high": high} for _ in range(n)]


def _q(code="600519", name="贵州茅台", pct=6.0, vr=0.8, amt=5e9, price=1500.0):
    return {code: {"code": code, "name": name, "pct_chg": pct, "vol_ratio": vr,
                   "amount": amt, "price": price}}


# ── 主板判定 ──
def test_main_board_true():
    assert _is_main_board("600519")
    assert _is_main_board("000001")
    assert _is_main_board("601398")


def test_main_board_false():
    for c in ("300319", "301001", "688111", "689009", "830799", "430047", "920001"):
        assert not _is_main_board(c), c


# ── 距20日高 ──
def test_dist_hi_at_high():
    """T-1 收盘 = 20 日最高 → 距离 0%"""
    kl = [{"close": 10.0, "high": 10.0} for _ in range(25)]
    assert abs(compute_dist_hi(kl) - 0.0) < 1e-6


def test_dist_hi_below():
    """T-1 收盘 9.0，20 日高 10.0 → -10%"""
    kl = [{"close": 9.0, "high": 10.0} for _ in range(20)]
    kl += [{"close": 9.0, "high": 9.0} for _ in range(5)]
    d = compute_dist_hi(kl)
    assert -11.0 < d < -9.0


def test_dist_hi_insufficient():
    assert compute_dist_hi(_kl(n=5)) is None
    assert compute_dist_hi([]) is None


# ── enabled 开关（铁律：默认关）──
def test_default_disabled():
    assert VOL_SIGNAL_DEFAULTS["enabled"] is False
    assert scan_vol_signal(_q(), lambda c, n: _kl(), {}) == []
    assert scan_vol_signal(_q(), lambda c, n: _kl()) == []


# ── 命中 / 拒绝 ──
def test_hit():
    r = scan_vol_signal(_q(), lambda c, n: _kl(), {"enabled": True})
    assert len(r) == 1
    assert r[0]["code"] == "600519"
    assert "缩量" in r[0]["reason"]


def test_reject_high_vol_ratio():
    """量比 >= 1（放量）→ 拒绝（核心：缩量才是信号）"""
    r = scan_vol_signal(_q(vr=2.0), lambda c, n: _kl(), {"enabled": True})
    assert r == []


def test_reject_low_pct():
    r = scan_vol_signal(_q(pct=2.0), lambda c, n: _kl(), {"enabled": True})
    assert r == []


def test_reject_far_from_high():
    kl = [{"close": 8.0, "high": 10.0} for _ in range(25)]
    r = scan_vol_signal(_q(), lambda c, n: kl, {"enabled": True})
    assert r == []


def test_reject_st():
    r = scan_vol_signal(_q(name="ST某某"), lambda c, n: _kl(), {"enabled": True})
    assert r == []


def test_reject_cyb_by_default():
    """主板限定：创业板默认排除（实证胜率仅 49%、中位数为负）"""
    r = scan_vol_signal(_q(code="300319", name="麦捷科技"),
                        lambda c, n: _kl(), {"enabled": True})
    assert r == []


def test_allow_cyb_when_configured():
    r = scan_vol_signal(_q(code="300319", name="麦捷科技"), lambda c, n: _kl(),
                        {"enabled": True, "main_board_only": False})
    assert len(r) == 1


def test_reject_new_stock():
    r = scan_vol_signal(_q(), lambda c, n: _kl(), {"enabled": True},
                        listed_days={"600519": 10})
    assert r == []


def test_reject_low_amount():
    r = scan_vol_signal(_q(amt=1e7), lambda c, n: _kl(), {"enabled": True})
    assert r == []


# ── 打分单调性 ──
def test_score_monotonic_in_vol_ratio():
    hi = score_vol_signal(6.0, 0.3, 0.0, {})
    lo = score_vol_signal(6.0, 0.9, 0.0, {})
    assert hi > lo > 0


def test_score_zero_outside_zone():
    assert score_vol_signal(2.0, 0.5, 0.0, {}) == 0.0     # 涨幅不足
    assert score_vol_signal(6.0, 2.0, 0.0, {}) == 0.0     # 放量
    assert score_vol_signal(6.0, 0.5, -20.0, {}) == 0.0   # 离高点太远
