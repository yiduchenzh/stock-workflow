# -*- coding: utf-8 -*-
"""mainrise_screener 主升浪四步筛选单测（2026-08-21 老陈新战法落地）"""
import sys
sys.path.insert(0, r'D:\Hermes Agent CN Desktop\hunter-v2\backend')
import mainrise_screener as ms


def _kline(mode="zsl", n_days=150, base=10.0):
    """构造日K:
    mode=zsl: 下跌→低位横盘→温和放量突破(主升浪形态)
    mode=down: 持续下跌(趋势不达标)
    mode=high: 高位(距60日高<5%)
    """
    rows = []
    if mode == "down":
        c = base
        for i in range(n_days):
            day = f"2026-{(i//28)+1:02d}-{(i%28)+1:02d}"
            c *= 0.99
            rows.append({"day": day, "open": c * 1.01, "high": c * 1.02,
                         "low": c * 0.98, "close": c, "volume": 800_000})
        return rows
    # 阶段0 (0..49): 下跌 12 → 8 (造更早高点, 让60日窗口内主要是横盘区)
    c = base * 1.2
    for i in range(50):
        day = f"2026-{(i//28)+1:02d}-{(i%28)+1:02d}"
        c *= 0.99
        rows.append({"day": day, "open": c * 1.005, "high": c * 1.01,
                     "low": c * 0.99, "close": c, "volume": 600_000})
    # 阶段1 (50..149): 低位横盘蓄力 100 天 (缩量, 筹码集中; 60日窗口全在横盘区)
    for i in range(50, 150):
        day = f"2026-{(i//28)+1:02d}-{(i%28)+1:02d}"
        c = rows[-1]["close"]
        rows.append({"day": day, "open": c * 0.998, "high": c * 1.005,
                     "low": c * 0.994, "close": c * 1.0008, "volume": 250_000})
    # 阶段2 最后: 温和放量突破 (量比~2, 收阳 +2.5%)
    c = rows[-1]["close"]
    rows.append({"day": "2026-08-21", "open": c * 1.005, "high": c * 1.03,
                 "low": c * 1.0, "close": c * 1.025, "volume": 1_200_000})
    return rows


def test_zsl_signal():
    """主升浪形态 → 类型=主升浪, 得分高 (趋势+筹码+量价+节奏达标)"""
    rows = _kline("zsl")
    sig = ms.score_signal(rows, len(rows) - 1, "000001")
    assert sig["type"] == "主升浪", f"应判主升浪: {sig['logic']}"
    assert sig["score"] >= 60, f"四步达标应高分: {sig['score']} {sig['logic']}"
    det = sig["detail"]
    assert det["ma20"] > det["ma60"], "MA20应>MA60"
    assert det["vol_ratio"] >= 1.2, f"放量突破: {det['vol_ratio']}"


def test_down_not_zsl():
    """下跌趋势 → 非主升浪 (趋势不达标)"""
    rows = _kline("down")
    sig = ms.score_signal(rows, len(rows) - 1, "000002")
    assert sig["type"] == "非主升浪", f"下跌应判非主升浪: {sig['logic']}"
    assert sig["level"] == "D"


def test_high_position_penalty():
    """高位(距60日高<5%) → 节奏降权, 不得A级"""
    rows = _kline("zsl")
    # 人为把最后K线推到60日高点附近 (高位鱼尾)
    hi60 = max(r["high"] for r in rows[:-1])
    c = rows[-1]["close"]
    rows[-1] = {"day": "2026-08-21", "open": c, "high": hi60 * 1.001,
                "low": c * 0.99, "close": hi60 * 1.0005, "volume": 1_200_000}
    sig = ms.score_signal(rows, len(rows) - 1, "000003")
    det = sig["detail"]
    assert det["dist60"] < 5, f"应判高位: dist60={det['dist60']}"
    assert "鱼尾" in sig["logic"] or "高位" in sig["logic"], "高位应有鱼尾风险提示"


def test_chip_concentration():
    """筹码集中度计算: 横盘票集中度高, 波动票分散"""
    rows = _kline("zsl")
    conc = ms.chip_concentration(rows, len(rows) - 1)
    assert conc is not None and conc > 0, f"集中度应有效: {conc}"
    # 横盘票集中度应相对低(窄)
    assert conc < 30, f"横盘蓄力票集中度应较窄: {conc}%"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                print(f"FAIL {name}: {e}")
