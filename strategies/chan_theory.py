
"""缠论 — 分型检测 + 中枢识别 + 买卖点 · 缠中说禅"""
import numpy as np
import pandas as pd
import logging
logger = logging.getLogger("aurora.chan")

def detect_fractals(kline_df) -> dict:
    """顶分型/底分型检测"""
    if kline_df is None or len(kline_df) < 5:
        return {"tops": [], "bottoms": [], "bs_points": []}
    high = kline_df["high"].values
    low = kline_df["low"].values
    close = kline_df["close"].values
    tops, bottoms = [], []
    # 标准分型: 中间K线高/低点为局部极值
    for i in range(2, len(high) - 2):
        if high[i] > high[i-1] and high[i] > high[i-2] and high[i] > high[i+1] and high[i] > high[i+2]:
            tops.append({"idx": i, "price": float(high[i])})
        if low[i] < low[i-1] and low[i] < low[i-2] and low[i] < low[i+1] and low[i] < low[i+2]:
            bottoms.append({"idx": i, "price": float(low[i])})
    
    # 买卖点分类
    bs_points = _classify_bs_points(tops, bottoms, close)
    
    return {
        "tops": tops[-5:] if tops else [],
        "bottoms": bottoms[-5:] if bottoms else [],
        "bs_points": bs_points,
        "fractal_count": len(tops) + len(bottoms),
        "signal": len(bs_points) > 0,
        "last_bs": bs_points[-1] if bs_points else None,
    }

def _classify_bs_points(tops, bottoms, close):
    """缠论三类买卖点简化"""
    points = []
    # 一买: 底分型+后一根阳线确认 (底部转折)
    for b in bottoms[-3:]:
        idx = b["idx"]
        if idx + 1 < len(close) and close[idx+1] > close[idx]:
            points.append({"type": "buy1", "price": b["price"], "idx": idx, "desc": "一买(底转折)"})
    # 三买: 突破前高后回踩 (最安全)
    if len(tops) >= 2 and len(bottoms) >= 1:
        last_top = tops[-2]["price"]
        last_bottom = bottoms[-1]
        if last_bottom["price"] > last_top:
            points.append({"type": "buy3", "price": last_bottom["price"], "idx": last_bottom["idx"], "desc": "三买(突破回踩)"})
    return points

def chan_score(kline_df) -> float:
    """缠论综合评分 0-100"""
    result = detect_fractals(kline_df)
    if not result["signal"]:
        return 40  # 无买卖点: 中性
    last = result.get("last_bs")
    if not last:
        return 45
    if last["type"] == "buy3":
        return 75  # 三买: 最可靠
    elif last["type"] == "buy1":
        return 65  # 一买: 利润大但风险高
    return 50
