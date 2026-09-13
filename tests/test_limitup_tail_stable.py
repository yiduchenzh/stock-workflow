# -*- coding: utf-8 -*-
"""limitup_screener 尾盘企稳加分单测（2026-08-20 P2 A/B 实证落地）

A/B 结论(2年1884只全市场 92万逐日样本):
  守5/10日线×尾盘企稳(收盘位置≥0.7&上影比例≤0.3) → 次日涨停率 3.73% vs 全市场 1.58% (2.36倍)
  分年度 2024 3.5x / 2025 2.1x / 2026 1.8x 稳健; 收盘位置≥0.9 时 6.60%
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, r'D:\Hermes Agent CN Desktop\hunter-v2\backend')

import limitup_screener as ls


def _kline_for(close_pos, up_shadow, vol_ratio=0.5):
    """构造 40 根日K: 前段造60日高点→回落整理→最后一根尾盘形态(位置=上涨中途)。

    close_pos: 0~1 收盘位置; up_shadow: 0~1 上影比例(相对振幅)
    """
    rows = []
    # 阶段1 (i=0..9): 10 → 12 造60日高点(位置判定依赖)
    for i in range(10):
        c = 10.0 + i * 0.2
        rows.append({"day": f"2026-06-{i+1:02d}", "open": c - 0.05,
                     "high": c + 0.08, "low": c - 0.05, "close": c, "volume": 1e6})
    # 阶段2 (i=10..38): 11.8 → 10.4 回落整理(均线下来, 远离高点)
    for i in range(10, 39):
        c = 11.8 - (i - 10) * 0.04
        rows.append({"day": f"2026-06-{i+1:02d}", "open": c + 0.03,
                     "high": c + 0.06, "low": c - 0.03, "close": c, "volume": 1e6})
    # 最后一根: 微涨收高, 尾盘形态按 close_pos/up_shadow 反解
    prev_c = rows[-1]["close"]
    pc = prev_c
    o = pc * 1.005
    amp = 0.028 * pc              # 振幅 ~2.8%
    lo = min(o, pc * 1.01) - amp * 0.4
    hi = lo + amp
    close = lo + close_pos * (hi - lo)
    rows.append({"day": "2026-08-19", "open": o, "high": hi, "low": lo,
                 "close": close, "volume": 1e6 * vol_ratio})
    return ls.attach_prev_close(rows)


def test_tail_stable_bonus():
    """尾盘企稳(收盘位置0.85 上影0.15)应加分 +8, 且 detail 带 tail_stable"""
    rows = _kline_for(close_pos=0.85, up_shadow=0.15)
    sig = ls.score_signal(rows, len(rows) - 1)
    assert sig["type"] != "无形态", f"构造K线应判出形态: {sig}"
    det = sig["detail"]
    assert det.get("tail_stable") is True, f"tail_stable 应为 True: {det}"
    assert "尾盘企稳" in sig["logic"]
    # 缩量地量45 + 中途15 + 尾盘企稳8 = 68+ → B级及以上
    assert sig["score"] >= 60, f"尾盘企稳应显著加分: {sig['score']}"


def test_close_pos_09_extra_bonus():
    """收盘位置≥0.9(光头强收) 应额外 +4"""
    rows = _kline_for(close_pos=0.95, up_shadow=0.04)
    sig = ls.score_signal(rows, len(rows) - 1)
    assert sig["type"] != "无形态"
    det = sig["detail"]
    assert det.get("close_pos", 0) >= 0.9
    assert "光头强收" in sig["logic"]
    assert "+8" or "4" in sig["logic"]


def test_tail_not_stable_no_bonus():
    """尾盘不企稳(收盘位置0.4 上影0.5) 不加尾盘分"""
    rows = _kline_for(close_pos=0.4, up_shadow=0.5)
    sig = ls.score_signal(rows, len(rows) - 1)
    det = sig["detail"]
    assert det.get("tail_stable") is False
    assert "尾盘企稳" not in sig["logic"]


def test_attach_prev_close_works():
    """attach_prev_close 为每根补 prev_close（score_signal 依赖）"""
    rows = [{"day": "2026-08-01", "open": 10, "high": 10.5, "low": 9.8,
             "close": 10.2, "volume": 1e6},
            {"day": "2026-08-02", "open": 10.2, "high": 10.8, "low": 10.0,
             "close": 10.5, "volume": 1e6}]
    out = ls.attach_prev_close(rows)
    assert out[1]["prev_close"] == 10.2


def test_tail_stable_detail_fields_present():
    """所有评分路径 detail 都带 tail_stable 字段(前端可展示)"""
    rows = _kline_for(close_pos=0.7, up_shadow=0.2)
    cls = ls.classify_prev_volume(rows, len(rows) - 1)
    det = cls["detail"]
    assert "tail_stable" in det
    assert "close_pos" in det
    assert "tail_up_shadow" in det


# ═══ P3: 放量尾盘拉升加分 (2026-08-20 A/B: 放量收高涨停率16.75%, X∩A 23.85%) ═══

def _kline_for_volume(close_pos, up_shadow, vol_ratio):
    """构造放量尾盘拉升K线: 阶段1造高点→回落至10.6→回升至11.0(均线多头)→最后一根放量收高"""
    rows = []
    # 阶段1 (0-9): 10 → 12 造60日高点(位置判定依赖)
    for i in range(10):
        c = 10.0 + i * 0.2
        rows.append({"day": f"2026-06-{i+1:02d}", "open": c - 0.05,
                     "high": c + 0.08, "low": c - 0.05, "close": c, "volume": 1e6})
    # 阶段2 (10-24): 11.8 → 10.6 回落(远离高点, 均线下移)
    for i in range(10, 25):
        t = (i - 10) / 15.0
        c = 11.8 + (10.6 - 11.8) * t
        rows.append({"day": f"2026-06-{i+1:02d}", "open": c + 0.03,
                     "high": c + 0.06, "low": c - 0.03, "close": c, "volume": 1e6})
    # 阶段3 (25-38): 10.6 → 11.0 回升(ma5>ma10>ma20 多头排列)
    for i in range(25, 39):
        t = (i - 25) / 14.0
        c = 10.6 + (11.0 - 10.6) * t
        rows.append({"day": f"2026-06-{i+1:02d}", "open": c + 0.03,
                     "high": c + 0.06, "low": c - 0.03, "close": c, "volume": 1e6})
    # 最后一根: 微涨收高, 尾盘形态按 close_pos/up_shadow 反解
    prev_c = rows[-1]["close"]
    o = prev_c * 1.005
    amp = 0.028 * prev_c
    lo = min(o, prev_c * 1.01) - amp * 0.4
    hi = lo + amp
    close = lo + close_pos * (hi - lo)
    rows.append({"day": "2026-08-19", "open": o, "high": hi, "low": lo,
                 "close": close, "volume": 1e6 * vol_ratio})
    return ls.attach_prev_close(rows)


def test_volume_tail_raise_bonus():
    """尾盘企稳 + 放量(vol_ratio≥1.3) → 额外 +6 分"""
    rows = _kline_for_volume(close_pos=0.85, up_shadow=0.15, vol_ratio=1.5)
    sig = ls.score_signal(rows, len(rows) - 1)
    assert sig["type"] != "无形态", f"应判出形态: {sig}"
    assert sig["detail"].get("tail_stable") is True
    assert "放量尾盘拉升" in sig["logic"]


def test_volume_tail_raise_extra_higher_than_stable_only():
    """放量+企稳分数 > 仅企稳分数（加分真实叠加）"""
    rows_v = _kline_for_volume(close_pos=0.85, up_shadow=0.15, vol_ratio=1.5)
    rows_q = _kline_for_volume(close_pos=0.85, up_shadow=0.15, vol_ratio=0.5)
    sig_v = ls.score_signal(rows_v, len(rows_v) - 1)
    sig_q = ls.score_signal(rows_q, len(rows_q) - 1)
    assert sig_v["type"] != "无形态" and sig_q["type"] != "无形态"
    assert sig_v["score"] > sig_q["score"], f"放量应更高: {sig_v['score']} vs {sig_q['score']}"


def test_volume_tail_raise_no_bonus_without_stable():
    """放量但尾盘不企稳 → 不加放量拉升分"""
    rows = _kline_for_volume(close_pos=0.4, up_shadow=0.5, vol_ratio=1.5)
    sig = ls.score_signal(rows, len(rows) - 1)
    det = sig["detail"]
    assert det.get("tail_stable") is False
    assert "放量尾盘拉升" not in sig["logic"]
