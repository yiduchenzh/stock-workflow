# -*- coding: utf-8 -*-
"""幽灵持仓修复单测: 涨停基因硬门槛 (2026-08-21)

背景: 工商银行(601398)缩量被"缩量地量"误判A/B级进强势池 → 09:41换股买入被套(T+1锁定刷屏)。
修复: limitup_screener.analyze + strong_pool 加"近60日有涨停(≥9.5%)"硬门槛, 防御股/横盘股直接排除。
"""
import sys, os
sys.path.insert(0, r'D:\Hermes Agent CN Desktop\hunter-v2\backend')
sys.path.insert(0, r'D:\Hermes Agent CN Desktop\limitup-system')
import limitup_screener as ls


def _kline(limit_days: list, base: float = 10.0, n_days: int = 70):
    """构造日K: base 起逐步小涨, limit_days 指定索引处放 +10% 涨停"""
    rows = []
    c = base
    for i in range(n_days):
        day = f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}"
        if i in limit_days:
            rows.append({"day": day, "open": c, "high": c * 1.1, "low": c * 0.98,
                         "close": c * 1.10, "volume": 1_000_000})
            c *= 1.10
        else:
            rows.append({"day": day, "open": c, "high": c * 1.01, "low": c * 0.99,
                         "close": c * 1.005, "volume": 100_000})
            c *= 1.005
    return rows


def test_analyze_blocks_no_limit_gene():
    """无涨停基因(防御股模拟): 近60日无涨停 → 返回"无形态"拦截"""
    rows = _kline(limit_days=[])  # 全程无涨停
    kline_getter = lambda code, period="daily", count=120: rows
    sig = ls.analyze(kline_getter, "601398", 120)
    assert sig is not None
    assert sig["type"] == "无形态"
    assert "无涨停" in str(sig.get("logic") or "")
    assert sig["level"] == "D"


def test_analyze_allows_with_limit_gene():
    """有涨停基因(近60日涨停): 正常进入形态评分(不拦截)"""
    rows = _kline(limit_days=[65])  # 近60日内有1次涨停
    kline_getter = lambda code, period="daily", count=120: rows
    sig = ls.analyze(kline_getter, "000017", 120)
    # 有涨停基因 → 不会被"无涨停基因"拦截; 形态可能仍为无形态(取决于构造), 但 logic 不应含"无涨停"
    assert sig is not None
    logic = str(sig.get("logic") or "")
    assert "无涨停" not in logic


def test_limit_gene_uses_recent60():
    """涨停发生在60日外(更早) → 仍拦截 (基因须近期有)"""
    rows = _kline(limit_days=[10])  # 60日前(索引10)有涨停
    kline_getter = lambda code, period="daily", count=120: rows
    sig = ls.analyze(kline_getter, "601398", 120)
    assert sig is not None
    assert "无涨停" in str(sig.get("logic") or "")
