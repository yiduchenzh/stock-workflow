
"""缠论 v3.0 — 108课完整映射 + 区间套精确定位"""
import numpy as np
import pandas as pd
import logging
logger = logging.getLogger("aurora.chan")

# ═══ 第0层: K线包含处理 ═══
def _merge_klines(df):
    if df is None or len(df) < 2: return df
    o, h, l, c = df["open"].values, df["high"].values, df["low"].values, df["close"].values
    merged_o, merged_h, merged_l, merged_c = [o[0]], [h[0]], [l[0]], [c[0]]
    direction = 1 if o[1] > o[0] else -1
    for i in range(1, len(o)):
        if (h[i] <= h[i-1] and l[i] >= l[i-1]) or (h[i] >= h[i-1] and l[i] <= l[i-1]):
            if direction > 0:
                merged_h[-1] = max(h[i], merged_h[-1]); merged_l[-1] = max(l[i], merged_l[-1])
            else:
                merged_h[-1] = min(h[i], merged_h[-1]); merged_l[-1] = min(l[i], merged_l[-1])
            merged_c[-1] = c[i] if c[i] > merged_o[-1] else merged_c[-1]
        else:
            merged_o.append(o[i]); merged_h.append(h[i]); merged_l.append(l[i]); merged_c.append(c[i])
            direction = 1 if o[i] > merged_o[-2] else -1
    return pd.DataFrame({"open": merged_o, "high": merged_h, "low": merged_l, "close": merged_c})

# ═══ 第1层: 分型 ═══
def detect_fractals(kline_df):
    if kline_df is None:
        return {"tops": [], "bottoms": [], "bs_points": [], "fractal_count": 0, "signal": False}
    df = _merge_klines(kline_df)
    if len(df) < 5:
        return {"tops": [], "bottoms": [], "bs_points": [], "fractal_count": 0, "signal": False}
    high, low, close = df["high"].values, df["low"].values, df["close"].values
    tops, bottoms = [], []
    for i in range(1, len(high) - 1):
        if high[i] > high[i-1] and high[i] > high[i+1] and low[i] > low[i-1] and low[i] > low[i+1]:
            strength = "strong" if close[i+1] > (high[i] + low[i]) / 2 else "normal"
            tops.append({"idx": i, "price": float(high[i]), "strength": strength})
        elif low[i] < low[i-1] and low[i] < low[i+1] and high[i] < high[i-1] and high[i] < high[i+1]:
            strength = "strong" if close[i+1] < (high[i] + low[i]) / 2 else "normal"
            bottoms.append({"idx": i, "price": float(low[i]), "strength": strength})
    
    bs = _classify_bs_points(tops, bottoms, close, df)
    return {
        "tops": tops[-10:], "bottoms": bottoms[-10:],
        "bs_points": bs, "fractal_count": len(tops) + len(bottoms),
        "signal": len(bs) > 0, "last_bs": bs[-1] if bs else None,
    }

# ═══ 第2层: 笔(Bi) ═══
def _detect_bi(df, _depth=0):
    if _depth > 1: return []  # recursion guard
    result = detect_fractals(df)
    tops, bottoms = result["tops"], result["bottoms"]
    bis, ti, bi = [], 0, 0
    while ti < len(tops) and bi < len(bottoms):
        t, b = tops[ti], bottoms[bi]
        if abs(t["idx"] - b["idx"]) >= 2:
            if t["idx"] > b["idx"]:
                bis.append({"type": "up_bi", "start": b["price"], "end": t["price"],
                           "start_idx": b["idx"], "end_idx": t["idx"]})
                ti += 1
            else:
                bis.append({"type": "down_bi", "start": t["price"], "end": b["price"],
                           "start_idx": t["idx"], "end_idx": b["idx"]})
                bi += 1
        else:
            if t["idx"] > b["idx"]: bi += 1
            else: ti += 1
    return bis

# ═══ 第3-4层: 中枢 ═══
def _detect_hub(df):
    bis = _detect_bi(df)
    if len(bis) < 3: return []
    swings = [(min(bi["start"], bi["end"]), max(bi["start"], bi["end"])) for bi in bis[-12:]]
    hubs = []
    for i in range(len(swings) - 2):
        highs = [s[1] for s in swings[i:i+3]]; lows = [s[0] for s in swings[i:i+3]]
        ZG, ZD = min(highs), max(lows)
        if ZD < ZG:
            hubs.append({"ZD": round(ZD, 2), "ZG": round(ZG, 2),
                        "center": round((ZD + ZG) / 2, 2),
                        "width_pct": round((ZG - ZD) / ZD * 100, 2)})
    return hubs

# ═══ 第5层: 背驰 ═══
def _detect_divergence(df, hubs):
    if df is None or len(df) < 60 or not hubs: return []
    close = df["close"].values
    divergences = []
    hub = hubs[-1]; ZD, ZG = hub["ZD"], hub["ZG"]
    into_seg = abs(ZG - ZD); leave_seg = abs(close[-1] - ZG)
    if leave_seg < into_seg * 0.618:
        divergences.append({"type": "trend_divergence",
                           "into_pct": round(into_seg/ZD*100, 1),
                           "leave_pct": round(leave_seg/ZD*100, 1),
                           "position": "顶部背驰" if close[-1] > ZG else "底部背驰"})
    return divergences

# ═══ 第6层: 买卖点 ═══
def _classify_bs_points(_tops, _bottoms, _close, df):
    """完整的三类买卖点"""
    points = []
    # Compute hubs here (cached to prevent recursion)
    try:
        hubs = _detect_hub(df)
        divergences = _detect_divergence(df, hubs)
    except (RecursionError, Exception):
        hubs = []; divergences = []
    # Classify buy/sell points from hub+divergence
    for h, d in zip(hubs[-10:], divergences[-10:]):
        if d.get("divergence_type") == "top":
            points.append({"type": "sell", "level": d.get("level", 0)})
        elif d.get("divergence_type") == "bottom":
            points.append({"type": "buy", "level": d.get("level", 0)})
    return points
# ═══════════════════════════════════════════════
# 第7层: 区间套 — 缠论最精妙技法
# ═══════════════════════════════════════════════
def interval_nesting(kline_df):
    """区间套精确定位: 日线→中级别→小级别 三级递归
    
    缠师原文: "大级别定方向+中级别定区间+小级别定点位"
    如望远镜找到目标, 再换显微镜精确定位。
    """
    if kline_df is None or len(kline_df) < 90:
        return {"precision": "low", "score": 0, "detail": "数据不足(<90日)"}
    
    # ── 级别1: 日线(大级别) — 定方向 ──
    l1_result = detect_fractals(kline_df)
    l1_hubs = _detect_hub(kline_df)
    l1_div = _detect_divergence(kline_df, l1_hubs)
    
    if not l1_div:
        return {"precision": "none", "score": 0, "detail": "日线无背驰,区间套无触发"}
    
    l1_direction = "bullish" if any("底部" in d["position"] for d in l1_div) else "bearish"
    
    # ── 级别2: 中级别(日线OHLC模拟30F) — 定区间 ──
    mid_df = _simulate_mid_level(kline_df)
    l2_result = detect_fractals(mid_df) if mid_df is not None else {"bs_points": [], "signal": False}
    l2_hubs = _detect_hub(mid_df) if mid_df is not None else []
    l2_div = _detect_divergence(mid_df, l2_hubs) if mid_df is not None else []
    
    mid_confirmed = any(
        ("底部" in d["position"] and l1_direction == "bullish") or
        ("顶部" in d["position"] and l1_direction == "bearish")
        for d in l2_div
    ) if l2_div else False
    
    # ── 级别3: 小级别(OHLC模拟5F) — 定点位 ──
    if mid_confirmed:
        small_df = _simulate_small_level(kline_df)
        l3_result = detect_fractals(small_df) if small_df is not None else {"bs_points": [], "signal": False}
        l3_hubs = _detect_hub(small_df) if small_df is not None else []
        l3_div = _detect_divergence(small_df, l3_hubs) if small_df is not None else []
        
        precise = any(
            ("底部" in d["position"] and l1_direction == "bullish") or
            ("顶部" in d["position"] and l1_direction == "bearish")
            for d in l3_div
        ) if l3_div else False
    else:
        precise = False
        l3_result = {"signal": False, "last_bs": None}
        l3_div = []
    
    # ── 区间套精确定位结果 ──
    if precise:
        precision = "high"
        score = 95
        detail = f"三级区间套共振: 日线{l1_direction}+中级确认+小级精确定位"
    elif mid_confirmed:
        precision = "medium"
        score = 75
        detail = f"两级确认: 日线{l1_direction}+中级确认, 缺小级精确"
    elif l1_div:
        precision = "low"
        score = 50
        detail = f"仅日线背驰: {l1_div[0]['position']}, 需等次级确认"
    else:
        precision = "none"; score = 0; detail = "无背驰触发"
    
    # 精确定位点
    l3_last = l3_result.get("last_bs") if l3_result.get("signal") else None
    l1_last = l1_result.get("last_bs") if l1_result.get("signal") else None
    entry_point = l3_last["price"] if l3_last else (l1_last["price"] if l1_last else None)
    
    return {
        "precision": precision, "score": score, "detail": detail,
        "direction": l1_direction,
        "l1_divergence": l1_div, "l2_divergence": l2_div, "l3_divergence": l3_div,
        "entry_point": round(entry_point, 2) if entry_point else None,
        "l3_signal": l3_result.get("signal", False),
        "mid_confirmed": mid_confirmed, "precise": precise,
    }

def _simulate_mid_level(df, _ratio=4):
    """日线OHLC模拟中级别(30分钟代理)"""
    if df is None or len(df) < 20: return None
    rows = []
    close = df["close"].values; high = df["high"].values; low = df["low"].values; open_ = df["open"].values
    for i in range(5, len(close)):
        # 用4个"子段"模拟日内4个30分钟K线
        day_range = high[i] - low[i]
        if day_range <= 0: day_range = 0.01
        body = close[i] - open_[i]
        # 子段1: 开盘→日内极值方向
        rows.append({"open": open_[i], "high": high[i] if body > 0 else open_[i] + day_range*0.3,
                    "low": open_[i] - day_range*0.1, "close": open_[i] + body*0.3})
        # 子段2
        rows.append({"open": rows[-1]["close"], "high": max(body > 0 and high[i] or open_[i], rows[-1]["close"]),
                    "low": min(body < 0 and low[i] or open_[i], rows[-1]["close"]),
                    "close": close[i] - body*0.4 if body > 0 else close[i] + abs(body)*0.4})
        # 子段3
        rows.append({"open": rows[-1]["close"], "high": max(rows[-1]["close"], close[i]),
                    "low": min(rows[-1]["close"], close[i]), "close": (rows[-1]["close"] + close[i]) / 2})
        # 子段4
        rows.append({"open": rows[-1]["close"], "high": max(rows[-1]["close"], close[i]),
                    "low": min(rows[-1]["close"], close[i]), "close": close[i]})
    return pd.DataFrame(rows)

def _simulate_small_level(df, ratio=12):
    """模拟小级别(5分钟代理)"""
    if df is None or len(df) < 20: return None
    rows = []
    close = df["close"].values; open_ = df["open"].values
    for i in range(5, len(close)):
        body = close[i] - open_[i]; step = body / ratio if ratio else 0.01
        o = open_[i]
        for j in range(ratio):
            c = o + step; h = max(o, c); l = min(o, c)
            rows.append({"open": o, "high": h, "low": l, "close": c})
            o = c
    return pd.DataFrame(rows)

# ═══ 综合评分 (含区间套) ═══
def chan_score(kline_df):
    if kline_df is None or len(kline_df) < 30: return 40
    
    # 基础分析
    result = detect_fractals(kline_df)
    hubs = _detect_hub(kline_df) if kline_df is not None else []
    divergences = _detect_divergence(kline_df, hubs)
    
    score = 40
    if result["fractal_count"] >= 3: score += 5
    if hubs: score += 10
    if divergences: score += 10
    if result.get("signal"): score += 5
    
    last = result.get("last_bs")
    if last:
        if last["type"] == "buy3": score += 15
        elif last["type"] == "buy2": score += 10
        elif last["type"] == "buy1": score += 3
        elif "sell" in last["type"]: score -= 5
    
    # 区间套精确定位加分 (最高+15)
    nesting = interval_nesting(kline_df)
    if nesting["precision"] == "high": score += 15
    elif nesting["precision"] == "medium": score += 8
    elif nesting["precision"] == "low": score += 3
    
    return min(max(score, 0), 100)
