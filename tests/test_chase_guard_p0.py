# -*- coding: utf-8 -*-
"""P0-1/P0-2/P1-1/P1-2 昨收战法选股修复单测 (2026-08-21)"""
import sys
sys.path.insert(0, r'D:\Hermes Agent CN Desktop\hunter-v2\backend')

import pytest

import auto_trader

# v14.49(2026-09-11): hunter-v2 的 auto_trader 已无 _entry_chase_guard(该护栏逻辑不在本模块),
# 本文件是跨项目过期测试 → 方法缺失时 skip, 避免全量 pytest 出现 5 条 AttributeError 噪音。
if not hasattr(auto_trader.AutoTrader, "_entry_chase_guard"):
    pytest.skip("hunter-v2 auto_trader.AutoTrader 无 _entry_chase_guard(过期测试)",
                allow_module_level=True)


class FakeTrader:
    """只测试 _entry_chase_guard 方法逻辑的最小桩"""
    _pool_items = {}
    _ts_cache = {}

    def __init__(self):
        self._pool_names = {}
        self._just_sold = set()

    def _trend_strong_meta(self, code):
        return self._ts_cache.get(code)

    def _record_signal(self, *a, **k):
        pass

    def _trend_target_pct(self, code):
        return 0.5


def test_chase_guard_normal_ok():
    """小涨(<5%) 放行"""
    t = FakeTrader()
    allow, reason = auto_trader.AutoTrader._entry_chase_guard(t, "000001", 3.0)
    assert allow, f"小涨应放行: {reason}"


def test_chase_guard_high_chase_blocked():
    """当日+8% 且 距60日高回撤>3%(非突破前夜) → 拦截 (P1-1 核心)"""
    t = FakeTrader()
    t._ts_cache["000002"] = {"dist_high60": -8.0, "atr20_pct": 9.0, "score": 40}
    allow, reason = auto_trader.AutoTrader._entry_chase_guard(t, "000002", 8.0)
    assert not allow, f"+8%非突破前夜应拦截: {reason}"
    assert "追高" in reason


def test_chase_guard_breakout_night_ok():
    """当日+6% 但 距60日高回撤≤3%(突破前夜) → 放行 (研究: 突破前夜次日涨停19.2%)"""
    t = FakeTrader()
    t._ts_cache["000003"] = {"dist_high60": -1.5, "atr20_pct": 9.0, "score": 55}
    allow, reason = auto_trader.AutoTrader._entry_chase_guard(t, "000003", 6.0)
    assert allow, f"突破前夜应放行: {reason}"


def test_chase_guard_5to7_chase_blocked():
    """当日+6% 且 距60日高回撤>3% → 拦截 (P1-1: 阈值从7%降到5%)"""
    t = FakeTrader()
    t._ts_cache["000004"] = {"dist_high60": -10.0, "atr20_pct": 8.5, "score": 40}
    allow, reason = auto_trader.AutoTrader._entry_chase_guard(t, "000004", 6.5)
    assert not allow, f"+6.5%非突破前夜应拦截: {reason}"


def test_chase_guard_desc_breakout_ok():
    """desc 含'突破' → 放行 (兼容打板形态票)"""
    t = FakeTrader()
    t._pool_items = {"000005": {"potential_desc": "高位突破型", "limitup_type": "缩量地量"}}
    allow, reason = auto_trader.AutoTrader._entry_chase_guard(t, "000005", 9.0)
    assert allow, f"突破desc应放行: {reason}"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                print(f"FAIL {name}: {e}")
