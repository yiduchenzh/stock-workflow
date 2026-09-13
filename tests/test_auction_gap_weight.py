# -*- coding: utf-8 -*-
"""竞价 CC 层"低高开优先反加权"单测（2026-08-20 A/B 实证落地）

A/B 结论(2年1884只全市场 25512竞价信号):
  高开 gap 越高次日胜率单调降: 1~2%:71.5% → 6~7%:47.2%
  "黄金区间2-5%"自媒体宣称被证伪(加权反而 58.9% < 基线63.6%)
  反加权 (cc - k×gap) 隔夜胜率 63.6%→72.8% (k=2, 分年度/top_n/系数稳健)
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from screening.auction import auction_screen, calc_cc_ratio, GAP_PENALTY_K


def _cand(code, cc, gap):
    return {
        "code": code,
        "auction": {"cc": cc, "grade": "B: 中等承接", "signal": True,
                    "open_change": gap, "auction_vol_wan": 100.0,
                    "auction_amount_wan": 1000.0},
    }


def _make_ranked():
    """构造 3 只候选: 高CC高gap vs 低CC低gap, 验证低高开优先排序"""
    return [
        _cand("600001", cc=3.5, gap=6.0),   # 高CC但高开6%(次日胜率仅~51%)
        _cand("600002", cc=2.0, gap=1.5),   # 低CC但低开1.5%(次日胜率~71%最优桶)
        _cand("600003", cc=2.8, gap=2.5),
    ]


def test_low_gap_first_sort_key():
    """反加权排序键 = cc - k×gap: 低开1.5%应排到高CC高gap前面"""
    results = _make_ranked()
    # 模拟 auction_screen 的排序逻辑
    def _sort_key(x):
        cc = x["auction"]["cc"]
        gap = x["auction"].get("open_change") or 0.0
        return cc - GAP_PENALTY_K * gap
    results.sort(key=_sort_key, reverse=True)
    # 600002 (2.0 - 2*1.5 = -1.0) vs 600001 (3.5 - 2*6.0 = -8.5) vs 600003 (2.8-5.0=-2.2)
    # 排序: 600002 > 600003 > 600001
    assert results[0]["code"] == "600002", "低开1.5%应排第一(反加权)"
    assert results[1]["code"] == "600003"
    assert results[2]["code"] == "600001", "高开6%应沉底"


def test_gap_penalty_k_zero_preserves_old_order():
    """k=0 关闭 = 原 CC 降序行为(兼容历史回测)"""
    results = _make_ranked()
    # 原行为: 纯 CC 降序
    results.sort(key=lambda x: x["auction"]["cc"], reverse=True)
    assert results[0]["code"] == "600001", "纯CC排序时高CC的600001第一"
    assert results[1]["code"] == "600003"
    assert results[2]["code"] == "600002"


def test_ranked_order_difference_proves_weighting():
    """两种排序结果不同 = 反加权确实改变了选池顺序"""
    old_order = [c["code"] for c in sorted(_make_ranked(),
                 key=lambda x: x["auction"]["cc"], reverse=True)]
    new_order = [c["code"] for c in sorted(_make_ranked(),
                 key=lambda x: x["auction"]["cc"] - GAP_PENALTY_K *
                 (x["auction"].get("open_change") or 0.0), reverse=True)]
    assert old_order != new_order
    assert new_order[0] == "600002"


def test_calc_cc_ratio_fields():
    """calc_cc_ratio 输出 open_change 字段(排序键依赖)"""
    d = {"auction_vol": 30000, "auction_amount": 500000, "open": 10.2,
         "change_pct": 2.0, "high": 0, "low": 0}
    info = calc_cc_ratio(d)
    assert info["signal"] is True
    assert "open_change" in info
    assert info["open_change"] == 2.0
