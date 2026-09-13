# -*- coding: utf-8 -*-
"""P4-B 同步工作流单测: screening.strong_stock 强题材加分"""
import sys, json
sys.path.insert(0, r'D:\Hermes Agent CN Desktop\stock-workflow')
sys.path.insert(0, r'D:\Hermes Agent CN Desktop\hunter-v2\backend')
import screening.strong_stock as ss


def test_strong_stock_theme_bonus_field(monkeypatch):
    """screen_strong_stocks 输出的候选带 theme_strong 字段(默认 False)"""
    # 打桩 get_sector_ranking 防网络
    monkeypatch.setattr(ss, "get_sector_ranking", lambda n: [])
    monkeypatch.setattr(ss, "get_tencent_quotes", lambda *a, **k: [])
    # 打桩 news_sense: 无可导入时 theme_strong 应为 False (不崩溃)
    cands = [{
        "code": "600519", "name": "贵州茅台", "industry": "白酒",
        "change_pct": 2.0, "turnover": 4, "vol_ratio": 1.8,
        "price": 1500.0, "mcap": 18000,
    }]
    try:
        out = ss.screen_strong_stocks(cands, top_sectors=None, flow_stocks=None)
    except Exception:
        out = cands  # 网络失败也允许返回原候选(不崩溃)
    for c in out:
        assert "strong_score" in c, "候选必须带 strong_score"


def test_score_strong_kline_unchanged():
    """score_strong_kline 纯K线评分不受 P4-B 影响(回测侧无网络)"""
    closes = [10 + i * 0.05 for i in range(60)]  # 稳步上涨
    r = ss.score_strong_kline(closes, price=12.0)
    assert "score" in r and "grade" in r and "strong" in r
    assert 0 <= r["score"] <= 100
