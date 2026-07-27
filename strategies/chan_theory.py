# -*- coding: utf-8 -*-
"""缠论 v3.0 - 108课完整映射 + 区间套精确定位"""
import numpy as np
import pandas as pd
import logging
logger = logging.getLogger("aurora.chan")

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

def _detect_bi(df, _depth=0):
    if _depth > 1: return []
    result = detect_fractals(df)
    tops, bottoms = result["tops"], result["bottoms"]
    bis, ti, bi = [], 0, 0
    while ti < len(tops) and bi < len(bottoms):
        t, b = tops[ti], bottoms[bi]
        if abs(t["idx"] - b["idx"]) >= 2:
            if t["idx"] > b["idx"]:
                bis.append({"type": "up_bi", "start": b.get("price", 0), "end": t.get("price", 0),
                           "start_idx": b["idx"], "end_idx": t["idx"]})
                ti += 1
            else:
                bis.append({"type": "down_bi", "start": t.get("price", 0), "end": b.get("price", 0),
                           "start_idx": t["idx"], "end_idx": b["idx"]})
                bi += 1
        else:
            if t["idx"] > b["idx"]: bi += 1
            else: ti += 1
    return bis

def _detect_hub(df, min_bars_between=None):
    bis = _detect_bi(df)
    is_small = df is not None and len(df) < 100
    if min_bars_between is None:
        min_bars_between = 3 if is_small else 5
    if len(bis) < min_bars_between:
        return []
    if len(bis) < 15:
        swings = [(min(bi["start"], bi["end"]), max(bi["start"], bi["end"])) for bi in bis]
    else:
        limit = max(min_bars_between * 3, 12)
        swings = [(min(bi["start"], bi["end"]), max(bi["start"], bi["end"])) for bi in bis[-limit:]]
    hubs = []
    for i in range(len(swings) - 2):
        highs = [s[1] for s in swings[i:i+3]]
        lows = [s[0] for s in swings[i:i+3]]
        ZG, ZD = min(highs), max(lows)
        if ZD < ZG:
            hubs.append({"ZD": round(ZD, 2), "ZG": round(ZG, 2),
                        "center": round((ZD + ZG) / 2, 2),
                        "width_pct": round((ZG - ZD) / ZD * 100, 2)})
    return hubs

def _calc_rsi(prices, period=14):
    deltas = np.diff(prices)
    gains = np.maximum(deltas, 0)
    losses = np.maximum(-deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    if avg_loss == 0:
        rsi_arr = [100.0] * len(prices)
        rsi_arr[:period] = [np.nan] * period
        return np.array(rsi_arr)
    rs = avg_gain / avg_loss
    rsi_vals = [np.nan] * period
    rsi_vals.append(100 - 100 / (1 + rs))
    for i in range(period + 1, len(prices)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        if avg_loss == 0:
            rsi_vals.append(100.0)
        else:
            rsi_vals.append(100 - 100 / (1 + avg_gain / avg_loss))
    return np.array(rsi_vals)

def _detect_divergence(df, hubs):
    if df is None or len(df) < 60 or not hubs:
        return []
    close = df["close"].values
    divergences = []

    # METHOD 1: Price trend (multi-hub check)
    for hub in hubs[-3:]:
        ZD, ZG = hub["ZD"], hub["ZG"]
        into_seg = abs(ZG - ZD)
        leave_seg = abs(close[-1] - ZG)
        if leave_seg < into_seg * 0.618:
            divergences.append({
                "type": "trend_divergence",
                "into_pct": round(into_seg / ZD * 100, 1),
                "leave_pct": round(leave_seg / ZD * 100, 1),
                "position": "顶部背驰" if close[-1] > ZG else "底部背驰"
            })
            break

    # METHOD 2: RSI divergence
    rsi = _calc_rsi(close)
    if len(rsi) > 30 and not np.all(np.isnan(rsi[-20:])):
        lookback = min(20, len(close))
        recent_close = close[-lookback:]
        recent_rsi = rsi[-lookback:]
        hh_idx = np.argmax(recent_close)
        hh_rsi = recent_rsi[hh_idx]
        ll_idx = np.argmin(recent_close)
        ll_rsi = recent_rsi[ll_idx]

        prev_high_idx = np.argmax(recent_close[:max(hh_idx, 1)])
        if 0 < prev_high_idx < hh_idx:
            prev_high_rsi = recent_rsi[prev_high_idx]
            if not np.isnan(hh_rsi) and not np.isnan(prev_high_rsi) and hh_rsi < prev_high_rsi:
                divergences.append({
                    "type": "rsi_divergence",
                    "position": "顶部背驰",
                    "price_high": round(float(recent_close[hh_idx]), 2),
                    "rsi_current": round(float(hh_rsi), 1),
                    "rsi_previous": round(float(prev_high_rsi), 1),
                    "strength": "strong" if (prev_high_rsi - hh_rsi) > 10 else "normal"
                })

        prev_low_idx = np.argmin(recent_close[:max(ll_idx, 1)])
        if 0 < prev_low_idx < ll_idx:
            prev_low_rsi = recent_rsi[prev_low_idx]
            if not np.isnan(ll_rsi) and not np.isnan(prev_low_rsi) and ll_rsi > prev_low_rsi:
                divergences.append({
                    "type": "rsi_divergence",
                    "position": "底部背驰",
                    "price_low": round(float(recent_close[ll_idx]), 2),
                    "rsi_current": round(float(ll_rsi), 1),
                    "rsi_previous": round(float(prev_low_rsi), 1),
                    "strength": "strong" if (ll_rsi - prev_low_rsi) > 10 else "normal"
                })

    # METHOD 3: Volume-price divergence
    volume = df["volume"].values if "volume" in df.columns else np.zeros(len(df))
    if len(volume) > 20:
        lookback = min(20, len(volume))
        vol_window = volume[-lookback:]
        price_window = close[-lookback:]
        vol_trend = np.polyfit(np.arange(len(vol_window)), vol_window, 1)[0]
        price_trend = np.polyfit(np.arange(len(price_window)), price_window, 1)[0]
        if price_trend > 0 and vol_trend < 0:
            divergences.append({
                "type": "volume_divergence",
                "position": "顶部背驰",
                "price_trend": "up",
                "volume_trend": "down",
                "strength": "strong" if abs(vol_trend) > abs(price_trend) * 1000 else "normal"
            })
        elif price_trend < 0 and vol_trend < 0:
            divergences.append({
                "type": "volume_divergence",
                "position": "底部背驰",
                "price_trend": "down",
                "volume_trend": "down",
                "strength": "normal",
                "note": "缩量下跌, 抛压减弱"
            })

    return divergences

def _ema(data, period):
    alpha = 2 / (period + 1)
    result = [float(data[0])]
    for i in range(1, len(data)):
        result.append(alpha * float(data[i]) + (1 - alpha) * result[-1])
    return np.array(result)

def _classify_bs_points(_tops, _bottoms, _close, df):
    """缠论123买卖点分类 + MACD面积背离"""
    points = []
    try:
        hubs = _detect_hub(df)
        # MACD area divergence for 1st point
        if hubs and df is not None and len(df) > 60:
            close = df["close"].values
            # Compute MACD
            ema12 = _ema(close, 12); ema26 = _ema(close, 26)
            dif = ema12 - ema26; dea = _ema(dif, 9)
            macd = (dif - dea) * 2
            
            # Last hub
            last_hub = hubs[-1]
            ZD, ZG = last_hub["ZD"], last_hub["ZG"]
            
            # Find segments: into-hub segment (previous swing) and leave-hub segment (current)
            hub_mid = (ZD + ZG) / 2
            close_arr = close
            
            # Detect trend direction before hub
            pre_idx = max(0, len(close_arr) - 40)
            pre_avg = np.mean(close_arr[pre_idx:pre_idx+10])
            post_avg = np.mean(close_arr[-10:])
            
            # Into-segment MACD area (before hub formation)
            hub_start = max(0, len(close_arr) - 30)
            into_area = sum(abs(macd[hub_start:hub_start+15])) if len(macd) > hub_start+15 else 0
            
            # Leave-segment MACD area (after hub, current)
            leave_start = max(0, len(close_arr) - 15)
            leave_area = sum(abs(macd[leave_start:])) if len(macd) > leave_start else 0
            
            # === 第一类买卖点 (趋势背驰) ===
            # 下跌趋势+底背驰: price lower low, MACD area smaller = 1st buy
            if pre_avg > post_avg and close_arr[-1] < hub_mid:  # 下跌中
                if leave_area < into_area * 0.8 and into_area > 0:  # MACD面积缩小
                    points.append({"type": "buy1", "position": "第一类买点(趋势背驰)", 
                                   "price": round(float(close_arr[-1]), 2), "score": 85})
            
            # 上涨趋势+顶背驰: price higher high, MACD area smaller = 1st sell
            if pre_avg < post_avg and close_arr[-1] > hub_mid:  # 上涨中
                if leave_area < into_area * 0.8 and into_area > 0:
                    points.append({"type": "sell1", "position": "第一类卖点(趋势背驰)",
                                   "price": round(float(close_arr[-1]), 2), "score": 85})
            
            # === 第二类买卖点 (回抽不破) ===
            if points:
                last = points[-1]
                if "buy1" in last["type"]:
                    # 1st buy出现后, 价格回抽不破前低 = 2nd buy
                    if len(close_arr) > 5:
                        pullback_low = min(close_arr[-5:])
                        buy1_low = last.get("price", 0)
                        if pullback_low > buy1_low * 0.98:
                            points.append({"type": "buy2", "position": f"第二类买点(回抽不破{buy1_low:.2f})",
                                           "price": round(float(close_arr[-1]), 2), "score": 75})
                elif "sell1" in last["type"]:
                    if len(close_arr) > 5:
                        bounce_high = max(close_arr[-5:])
                        sell1_high = last.get("price", 0)
                        if bounce_high < sell1_high * 1.02:
                            points.append({"type": "sell2", "position": f"第二类卖点(反弹不破{sell1_high:.2f})",
                                           "price": round(float(close_arr[-1]), 2), "score": 75})
            
            # === 第三类买卖点 (离开中枢不回抽) ===
            if len(close_arr) > 5:
                recent_high = max(close_arr[-5:])
                recent_low = min(close_arr[-5:])
                # 向上离开中枢+回抽不进入中枢ZG = 3rd buy
                if recent_high > ZG and recent_low > ZG:
                    points.append({"type": "buy3", "position": f"第三类买点(回抽不进中枢{ZG:.2f})",
                                   "price": round(float(close_arr[-1]), 2), "score": 80})
                # 向下离开中枢+反弹不进入中枢ZD = 3rd sell
                if recent_low < ZD and recent_high < ZD:
                    points.append({"type": "sell3", "position": f"第三类卖点(反弹不进中枢{ZD:.2f})",
                                   "price": round(float(close_arr[-1]), 2), "score": 80})
        
        # Also include divergences from _detect_divergence
        divergences = _detect_divergence(df, hubs)
        for d in divergences:
            if "底部" in d.get("position",""):
                points.append({"type": "buy", "level": d.get("level", 0), "position": d.get("position",""), "score": 60})
            elif "顶部" in d.get("position",""):
                points.append({"type": "sell", "level": d.get("level", 0), "position": d.get("position",""), "score": 60})
    except (RecursionError, Exception):
        pass
    return points

def interval_nesting(kline_df):
    if kline_df is None or len(kline_df) < 90:
        return {"precision": "low", "score": 0, "detail": "数据不足(<90日)"}
    l1_result = detect_fractals(kline_df)
    l1_hubs = _detect_hub(kline_df)
    l1_div = _detect_divergence(kline_df, l1_hubs)
    if not l1_div:
        return {"precision": "none", "score": 0, "detail": "日线无背驰,区间套无触发"}
    l1_direction = "bullish" if any("底部" in d["position"] for d in l1_div) else "bearish"
    mid_df = _simulate_mid_level(kline_df)
    l2_result = detect_fractals(mid_df) if mid_df is not None else {"bs_points": [], "signal": False}
    l2_hubs = _detect_hub(mid_df) if mid_df is not None else []
    l2_div = _detect_divergence(mid_df, l2_hubs) if mid_df is not None else []
    mid_confirmed = any(
        ("底部" in d["position"] and l1_direction == "bullish") or
        ("顶部" in d["position"] and l1_direction == "bearish")
        for d in l2_div
    ) if l2_div else False
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
    if precise:
        precision = "high"; score = 95
        detail = "三级区间套共振: 日线" + l1_direction + "+中级确认+小级精确定位"
    elif mid_confirmed:
        precision = "medium"; score = 75
        detail = "两级确认: 日线" + l1_direction + "+中级确认, 缺小级精确"
    elif l1_div:
        precision = "low"; score = 50
        detail = "仅日线背驰: " + l1_div[0]["position"] + ", 需等次级确认"
    else:
        precision = "none"; score = 0; detail = "无背驰触发"
    l3_last = l3_result.get("last_bs") if l3_result.get("signal") else None
    l1_last = l1_result.get("last_bs") if l1_result.get("signal") else None
    entry_point = l3_last.get("price", 0) if l3_last else (l1_last.get("price", 0) if l1_last else None)
    return {
        "precision": precision, "score": score, "detail": detail,
        "direction": l1_direction,
        "l1_divergence": l1_div, "l2_divergence": l2_div, "l3_divergence": l3_div,
        "entry_point": round(entry_point, 2) if entry_point else None,
        "l3_signal": l3_result.get("signal", False),
        "mid_confirmed": mid_confirmed, "precise": precise,
    }

def _simulate_mid_level(df, _ratio=4):
    if df is None or len(df) < 20: return None
    rows = []
    close = df["close"].values; high = df["high"].values; low = df["low"].values; open_val = df["open"].values
    for i in range(5, len(close)):
        day_range = high[i] - low[i]
        if day_range <= 0: day_range = 0.01
        body = close[i] - open_val[i]
        rows.append({"open": open_val[i], "high": high[i] if body > 0 else open_val[i] + day_range*0.3,
                    "low": open_val[i] - day_range*0.1, "close": open_val[i] + body*0.3})
        rows.append({"open": rows[-1]["close"],
                    "high": max((body > 0 and high[i] or open_val[i]), rows[-1]["close"]),
                    "low": min((body < 0 and low[i] or open_val[i]), rows[-1]["close"]),
                    "close": close[i] - body*0.4 if body > 0 else close[i] + abs(body)*0.4})
        rows.append({"open": rows[-1]["close"], "high": max(rows[-1]["close"], close[i]),
                    "low": min(rows[-1]["close"], close[i]), "close": (rows[-1]["close"] + close[i]) / 2})
        rows.append({"open": rows[-1]["close"], "high": max(rows[-1]["close"], close[i]),
                    "low": min(rows[-1]["close"], close[i]), "close": close[i]})
    return pd.DataFrame(rows)

def _simulate_small_level(df, ratio=12):
    if df is None or len(df) < 20: return None
    rows = []
    close = df["close"].values; open_val = df["open"].values
    for i in range(5, len(close)):
        body = close[i] - open_val[i]; step = body / ratio if ratio else 0.01
        o = open_val[i]
        for j in range(ratio):
            c = o + step; h = max(o, c); l = min(o, c)
            rows.append({"open": o, "high": h, "low": l, "close": c})
            o = c
    return pd.DataFrame(rows)

def chan_score(kline_df):
    if kline_df is None or len(kline_df) < 30: return 40
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
        if last["type"] == "buy3": score += 20
        elif last["type"] == "buy2": score += 15
        elif last["type"] == "buy1": score += 25
        elif last["type"] == "sell3": score += 15
        elif last["type"] == "sell2": score += 10
        elif last["type"] == "sell1": score += 20
        elif "sell" in last["type"]: score -= 5
        elif "buy" in last["type"]: score += 5
    nesting = interval_nesting(kline_df)
    if nesting["precision"] == "high": score += 15
    elif nesting["precision"] == "medium": score += 8
    elif nesting["precision"] == "low": score += 3
    return min(max(score, 0), 100)
