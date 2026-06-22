
"""艾略特波浪 — 5浪推动+3浪调整 + 斐波那契 · 弗罗斯特/普莱切特"""
import numpy as np
import logging
logger = logging.getLogger("aurora.elliott")

def detect_impulse_wave(kline_df) -> dict:
    """检测推动浪结构: 5浪=3推进+2回调"""
    if kline_df is None or len(kline_df) < 90:
        return {"wave_detected": False, "current_wave": "unknown", "confidence": 0}
    close = kline_df["close"].values
    # 简化: 找局部极值点
    swings = _find_swings(close, min_bars=8)
    if len(swings) < 3:
        return {"wave_detected": False, "current_wave": "unknown", "confidence": 0}
    
    # 判断当前浪型
    last_swing = swings[-1]
    current = "wave5" if len(swings) >= 5 and swings[-1]["type"] == "high" else (
        "wave3" if len(swings) >= 3 and swings[-1]["type"] == "high" else "corrective")
    
    # 斐波那契扩展
    if len(swings) >= 3:
        wave1 = abs(swings[1]["price"] - swings[0]["price"]) if swings[0]["type"] != swings[1]["type"] else 0
        if wave1 > 0:
            target_1618 = swings[-1]["price"] + wave1 * 1.618 * (1 if swings[-1]["type"] == "low" else -1)
        else:
            target_1618 = None
    else:
        wave1 = 0; target_1618 = None
    
    return {
        "wave_detected": len(swings) >= 3,
        "current_wave": current,
        "confidence": min(len(swings) * 15, 80),
        "swings": len(swings),
        "target_1618": round(target_1618, 2) if target_1618 else None,
    }

def _find_swings(close, min_bars=8):
    swings = []
    window = min_bars
    for i in range(window, len(close) - window):
        if close[i] == max(close[i-window:i+window+1]):
            swings.append({"type": "high", "idx": i, "price": float(close[i])})
        elif close[i] == min(close[i-window:i+window+1]):
            swings.append({"type": "low", "idx": i, "price": float(close[i])})
    # 去重: 连续同向只保留最后一个
    filtered = []
    for s in swings:
        if not filtered or s["type"] != filtered[-1]["type"]:
            filtered.append(s)
    return filtered

def elliott_score(kline_df) -> float:
    result = detect_impulse_wave(kline_df)
    if not result["wave_detected"]: return 0
    if result["current_wave"] in ("wave3", "wave5"):
        return result["confidence"]
    return result["confidence"] * 0.5
