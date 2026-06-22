
"""裸K v2.0 — 完整形态库: PinBar/InsideBar/Engulfing/Fakey/供需区/市场结构"""
import numpy as np
import pandas as pd
import logging
logger = logging.getLogger("aurora.nakedk")

# ═══ 市场结构分析 ═══
def analyze_market_structure(kline_df):
    """HH/HL/LH/LL + CHoCH 结构分析"""
    if kline_df is None or len(kline_df) < 20: return {"structure": "unknown", "confidence": 0}
    high, low, close = kline_df["high"].values, kline_df["low"].values, kline_df["close"].values
    # 找局部极值 (5周期窗口)
    pivots = []
    for i in range(5, len(close) - 5):
        if high[i] == max(high[i-5:i+6]): pivots.append({"type": "HH_candidate", "idx": i, "price": high[i]})
        if low[i] == min(low[i-5:i+6]): pivots.append({"type": "LL_candidate", "idx": i, "price": low[i]})
    
    if len(pivots) < 2: return {"structure": "range", "confidence": 0.3}
    
    # 趋势判断
    last_highs = [p for p in pivots if "HH" in p["type"]][-3:]
    last_lows = [p for p in pivots if "LL" in p["type"]][-3:]
    higher_highs = len(last_highs) >= 2 and last_highs[-1]["price"] > last_highs[-2]["price"]
    higher_lows = len(last_lows) >= 2 and last_lows[-1]["price"] > last_lows[-2]["price"]
    lower_lows = len(last_lows) >= 2 and last_lows[-1]["price"] < last_lows[-2]["price"]
    lower_highs = len(last_highs) >= 2 and last_highs[-1]["price"] < last_highs[-2]["price"]
    
    if higher_highs and higher_lows:
        return {"structure": "uptrend", "confidence": 0.7, "detail": "HH+HL"}
    elif lower_lows and lower_highs:
        return {"structure": "downtrend", "confidence": 0.7, "detail": "LH+LL"}
    else:
        # 检查结构破坏 (CHoCH)
        if higher_lows and not higher_highs:
            return {"structure": "range_bullish", "confidence": 0.45, "detail": "HL无HH"}
        elif lower_highs and not lower_lows:
            return {"structure": "range_bearish", "confidence": 0.45, "detail": "LH无LL"}
        return {"structure": "range", "confidence": 0.3, "detail": "无方向"}

# ═══ 关键位强度评分 ═══
def find_key_levels(kline_df):
    """水平支撑阻力 + 强度评分"""
    if kline_df is None or len(kline_df) < 30: return []
    high, low = kline_df["high"].values, kline_df["low"].values
    levels = {}
    # 找所有转折点
    for i in range(5, len(high) - 5):
        is_pivot_h = high[i] == max(high[i-5:i+6])
        is_pivot_l = low[i] == min(low[i-5:i+6])
        if is_pivot_h:
            p = round(high[i], 2)
            levels[p] = levels.get(p, {"touches": 0, "strength": 0})
            levels[p]["touches"] += 1; levels[p]["strength"] += 10
        if is_pivot_l:
            p = round(low[i], 2)
            levels[p] = levels.get(p, {"touches": 0, "strength": 0})
            levels[p]["touches"] += 1; levels[p]["strength"] += 10
    # 合并邻近位(0.5%范围内)
    merged = []
    sorted_lvls = sorted(levels.items())
    for price, info in sorted_lvls:
        if not merged or abs(price - merged[-1]["price"]) / max(price, 1) > 0.005:
            merged.append({"price": price, **info})
        elif info["strength"] > merged[-1]["strength"]:
            merged[-1] = {"price": price, **info}
    return sorted(merged, key=lambda x: x["strength"], reverse=True)[:10]

def price_at_key_level(price, levels, tolerance_pct=0.02):
    """检查价格是否在关键位附近"""
    if not levels: return False, None
    for lvl in levels:
        if abs(price - lvl["price"]) / max(lvl["price"], 1) < tolerance_pct:
            return True, lvl
    return False, None

# ═══ Pin Bar 完整检测 ═══
def detect_pin_bar(kline_df, idx=-1):
    """标准Pin Bar: 影线>=实体2倍 + 鼻尖突出 + 关键位验证"""
    if kline_df is None or abs(idx) > len(kline_df): return None
    o = kline_df["open"].values[idx]; c = kline_df["close"].values[idx]
    h = kline_df["high"].values[idx]; l = kline_df["low"].values[idx]
    body_h = max(o, c); body_l = min(o, c)
    body = body_h - body_l; upper_wick = h - body_h; lower_wick = body_l - l
    total = h - l
    if total <= 0: return None
    
    # 锤头 (看涨Pin Bar)
    if lower_wick >= body * 2 and upper_wick < body * 0.5:
        nose_standout = (idx == -1 or l < min(kline_df["low"].values[idx-3:idx] or [l+1]))
        at_key, key_lvl = price_at_key_level(l, find_key_levels(kline_df))
        quality = "A" if (nose_standout and at_key) else ("B" if at_key else "C")
        prev_candle = kline_df["close"].values[idx-1] if abs(idx) > 1 else c
        return {"type": "hammer", "dir": "bullish", "quality": quality,
                "nose": round(l, 2), "body_center": round((body_h+body_l)/2, 2),
                "at_key_level": at_key, "nose_standout": nose_standout,
                "score": 75 if quality == "A" else (60 if quality == "B" else 40)}
    
    # 射击之星 (看跌Pin Bar)
    if upper_wick >= body * 2 and lower_wick < body * 0.5:
        nose_standout = (idx == -1 or h > max(kline_df["high"].values[idx-3:idx] or [h-1]))
        at_key, key_lvl = price_at_key_level(h, find_key_levels(kline_df))
        quality = "A" if (nose_standout and at_key) else ("B" if at_key else "C")
        return {"type": "shooting_star", "dir": "bearish", "quality": quality,
                "nose": round(h, 2), "body_center": round((body_h+body_l)/2, 2),
                "at_key_level": at_key, "nose_standout": nose_standout,
                "score": 65 if quality == "A" else (50 if quality == "B" else 30)}
    return None

# ═══ Inside Bar 检测 ═══
def detect_inside_bar(kline_df, idx=-1):
    """Inside Bar: 当前K线完全被母K线包含"""
    if kline_df is None or len(kline_df) < 2: return None
    cur_h = kline_df["high"].values[idx]; cur_l = kline_df["low"].values[idx]
    mom_h = kline_df["high"].values[idx-1]; mom_l = kline_df["low"].values[idx-1]
    if cur_h <= mom_h and cur_l >= mom_l:
        bar_range = cur_h - cur_l; mom_range = mom_h - mom_l
        compression = 1 - bar_range / max(mom_range, 0.001)
        return {"type": "inside_bar", "compression": round(compression, 2),
                "mother_high": round(mom_h, 2), "mother_low": round(mom_l, 2),
                "score": 60 if compression > 0.5 else 45}
    return None

# ═══ Engulfing 检测 ═══
def detect_engulfing(kline_df, idx=-1):
    """吞没形态: 当前K线完全吞没前一根"""
    if kline_df is None or len(kline_df) < 2: return None
    co, cc = kline_df["open"].values[idx], kline_df["close"].values[idx]
    po, pc = kline_df["open"].values[idx-1], kline_df["close"].values[idx-1]
    ch, cl = max(co, cc), min(co, cc)
    ph, pl = max(po, pc), min(po, pc)
    
    # 看涨吞没: 前阴后阳, 完全吞没
    if pc < po and cc > co and ch > ph and cl < pl:
        at_key, _ = price_at_key_level(cl, find_key_levels(kline_df))
        return {"type": "bullish_engulfing", "score": 70 if at_key else 55,
                "body_ratio": round(abs(cc-co)/max(abs(pc-po), 0.001), 1)}
    # 看跌吞没
    if pc > po and cc < co and ch > ph and cl < pl:
        at_key, _ = price_at_key_level(ch, find_key_levels(kline_df))
        return {"type": "bearish_engulfing", "score": 65 if at_key else 50,
                "body_ratio": round(abs(cc-co)/max(abs(pc-po), 0.001), 1)}
    return None

# ═══ Fakey 假突破检测 ═══
def detect_fakey(kline_df, idx=-1):
    """Fakey: 短暂突破关键位后反转 + Inside Bar确认"""
    if kline_df is None or len(kline_df) < 4: return None
    close, high, low = kline_df["close"].values, kline_df["high"].values, kline_df["low"].values
    levels = find_key_levels(kline_df)
    # 检查前2根K线是否假突破
    for i in range(idx - 2, idx + 1):
        if i < 2: continue
        at_key_h, lvl_h = price_at_key_level(high[i], levels, 0.01)
        at_key_l, lvl_l = price_at_key_level(low[i], levels, 0.01)
        # 假突破高点(上冲后迅速回落)
        if at_key_h and close[i] < lvl_h["price"] * 0.99:
            ib = detect_inside_bar(kline_df, idx)
            if ib:
                return {"type": "fakey_bearish", "score": 75 if ib["compression"] > 0.5 else 60,
                        "fake_level": round(lvl_h["price"], 2), "inside_bar": ib}
        # 假跌破低点
        if at_key_l and close[i] > lvl_l["price"] * 1.01:
            ib = detect_inside_bar(kline_df, idx)
            if ib:
                return {"type": "fakey_bullish", "score": 80 if ib["compression"] > 0.5 else 65,
                        "fake_level": round(lvl_l["price"], 2), "inside_bar": ib}
    return None

# ═══ 供需区检测 ═══
def detect_supply_demand_zones(kline_df):
    """RBR/DBD/DBR/RBD 供需区"""
    if kline_df is None or len(kline_df) < 20: return []
    close, volume = kline_df["close"].values, kline_df["volume"].values if "volume" in kline_df.columns else np.ones(len(kline_df))
    zones = []
    i = 3
    while i < len(close) - 3:
        # RBR (Rally-Base-Rally) = 需求区
        if close[i] > close[i-3] and abs(close[i] - close[i-1]) / close[i] < 0.01 and close[i+3] > close[i]:
            zone_low = min(kline_df["low"].values[i-1:i+2])
            zone_high = max(kline_df["high"].values[i-1:i+2])
            zones.append({"type": "demand", "zone": (round(zone_low, 2), round(zone_high, 2)),
                         "freshness": "high" if i > len(close) - 10 else "medium",
                         "score": 65})
            i += 4
        # DBD (Drop-Base-Drop) = 供给区
        elif close[i] < close[i-3] and abs(close[i] - close[i-1]) / close[i] < 0.01 and close[i+3] < close[i]:
            zone_low = min(kline_df["low"].values[i-1:i+2])
            zone_high = max(kline_df["high"].values[i-1:i+2])
            zones.append({"type": "supply", "zone": (round(zone_low, 2), round(zone_high, 2)),
                         "freshness": "high" if i > len(close) - 10 else "medium",
                         "score": 60})
            i += 4
        else:
            i += 1
    return zones[-5:] if zones else []

# ═══ 综合裸K评分 ═══
def naked_k_score(kline_df):
    """裸K综合评分: 结构+形态+关键位+供需区"""
    if kline_df is None or len(kline_df) < 10: return 35
    score = 35  # 基准
    # 市场结构 (25%)
    ms = analyze_market_structure(kline_df)
    if ms["structure"] in ("uptrend", "range_bullish"): score += 15
    elif ms["structure"] in ("downtrend", "range_bearish"): score -= 5
    # Pin Bar 质量 (20%)
    pb = detect_pin_bar(kline_df)
    if pb: score += pb.get("score", 0) * 0.2
    # Inside Bar (15%)
    ib = detect_inside_bar(kline_df)
    if ib: score += ib.get("score", 0) * 0.15
    # Engulfing (15%)
    eg = detect_engulfing(kline_df)
    if eg: score += eg.get("score", 0) * 0.15
    # Fakey (15%)
    fy = detect_fakey(kline_df)
    if fy: score += fy.get("score", 0) * 0.15
    # 供需区 (10%)
    zones = detect_supply_demand_zones(kline_df)
    if zones: score += 10
    return min(score, 100)
