
"""多周期共振 — Elder三重滤网 + Murphy多时间框架"""
import numpy as np
import pandas as pd
import logging
logger = logging.getLogger("aurora.mtf")

def check_mtf_resonance(kline_df) -> dict:
    """周线趋势→日线信号→60分入场 三重滤网"""
    if kline_df is None or len(kline_df) < 60:
        return {"resonance": False, "score": 0, "detail": "数据不足(<60日)"}
    close = kline_df["close"].values
    vol = kline_df["volume"].values if "volume" in kline_df.columns else np.ones(len(close))
    
    # 第一重: 周线趋势 (用60日代理~12周)
    ma60 = np.mean(close[-60:])
    weekly_trend = 1 if close[-1] > ma60 else (-1 if close[-1] < ma60 * 0.95 else 0)
    if weekly_trend <= 0:
        return {"resonance": False, "score": 0, "detail": "周线无上升趋势", "weekly": "flat/down"}
    
    # 第二重: 日线MADC/RSI确认
    ema12 = _ema(close, 12); ema26 = _ema(close, 26)
    macd = ema12[-1] - ema26[-1]
    macd_signal = _ema(np.array([ema12[i] - ema26[i] for i in range(len(ema12))]), 9)
    macd_up = macd > macd_signal[-1]
    rsi = _rsi(close, 14)
    daily_ok = macd_up and 40 <= rsi <= 70
    
    # 第三重: 60分入场 (用5日代理)
    ma5 = np.mean(close[-5:])
    ma10 = np.mean(close[-10:])
    vol_ratio = vol[-1] / np.mean(vol[-20:]) if np.mean(vol[-20:]) > 0 else 1
    trigger = close[-1] > ma5 and vol_ratio > 1.0
    
    score = 0
    if weekly_trend > 0: score += 40
    if daily_ok: score += 35
    if trigger: score += 25
    
    return {
        "resonance": score >= 60,
        "score": score,
        "detail": f"周{'↑' if weekly_trend>0 else '→'}日{'OK' if daily_ok else 'NO'}60{'↑' if trigger else '↓'}",
        "weekly": "up",
        "daily_macd": macd_up,
        "trigger": trigger,
        "rsi": round(rsi, 1),
    }

def _ema(data, period):
    alpha = 2 / (period + 1)
    result = [data[0]]
    for i in range(1, len(data)):
        result.append(alpha * data[i] + (1 - alpha) * result[-1])
    return np.array(result)

def _rsi(close, period=14):
    deltas = np.diff(close)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    return 100 - 100 / (1 + avg_gain / avg_loss) if avg_loss > 0 else 100
