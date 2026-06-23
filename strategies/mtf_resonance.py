
"""多周期共振 v2.0 — 真实周线/日线/60分K线 · Elder+Murphy"""
import numpy as np
import logging
logger = logging.getLogger("aurora.mtf")

def check_mtf_resonance(kline_df, code=None):
    """周线趋势(真实周K via Tencent)→日线MACD/RSI→60分入场"""
    if kline_df is None or len(kline_df) < 60:
        return {"resonance": False, "score": 0, "detail": "数据不足(<60日)"}
    close = kline_df["close"].values
    vol = kline_df["volume"].values if "volume" in kline_df.columns else np.ones(len(close))
    
    # 第一重: 周线趋势 (真实周K线数据)
    real_weekly = None
    if code:
        from data.sources import get_kline_period
        real_weekly = get_kline_period(code, "week", 52)
    weekly_kl = real_weekly if (real_weekly is not None and not real_weekly.empty) else _daily_to_weekly(kline_df)
    weekly_score = _score_weekly(weekly_kl) if weekly_kl is not None else 0
    if code and real_weekly is not None and not real_weekly.empty:
        logger.debug(f"[MTF] {code}: real weekly {len(real_weekly)} bars")
    if weekly_score < 30:
        return {"resonance": False, "score": 0, "detail": "周线无上升趋势", "weekly_score": weekly_score}
    
    # 第二重: 日线MACD/RSI/KDJ确认
    from strategies.indicator_system import detect_macd_divergence, detect_kdj_signal
    macd = detect_macd_divergence(kline_df)
    kdj = detect_kdj_signal(kline_df)
    ema12 = _ema(close, 12); ema26 = _ema(close, 26)
    dif = np.array([ema12[i] - ema26[i] for i in range(len(ema12))])
    dea_signal = _ema(dif, 9)
    macd_up = dif[-1] > dea_signal[-1]
    rsi = _rsi(close, 14)
    daily_ok = macd_up and 40 <= rsi <= 70
    # MACD底背离加成
    div_bonus = 15 if macd.get("direction") == "bullish" else (0)
    # KDJ超卖金叉加成
    kdj_bonus = 10 if kdj.get("type") == "oversold_golden_cross" else (5 if kdj.get("signal") else 0)

    # Monthly MACD bonus (真实月K)
    monthly_bonus = 0
    if code:
        from data.sources import get_kline_period
        mdf = get_kline_period(code, "month", 24)
        if not mdf.empty and len(mdf) >= 3:
            mclose = mdf["close"].values
            mema12 = _ema(mclose, 6); mema26 = _ema(mclose, 13)
            if mema12[-1] > mema26[-1]: monthly_bonus = 10
    
    # 第三重: 60分入场 (5日代理+量比)
    ma5 = np.mean(close[-5:]); ma10 = np.mean(close[-10:])
    vol_ratio = vol[-1] / np.mean(vol[-20:]) if np.mean(vol[-20:]) > 0 else 1
    trigger = close[-1] > ma5 > ma10 and vol_ratio > 1.0
    
    score = weekly_score * 0.4 + (30 if daily_ok else 10) + div_bonus + kdj_bonus + monthly_bonus + (25 if trigger else 5)
    return {
        "resonance": score >= 60, "score": min(score, 100),
        "detail": f"周{weekly_score}日{'OK' if daily_ok else 'WAIT'}60{'↑' if trigger else '→'}",
        "weekly_score": weekly_score, "daily_macd": macd_up, "trigger": trigger, "monthly_bonus": monthly_bonus,
        "rsi": round(rsi, 1), "macd_div": macd.get("type", "none"),
        "kdj_signal": kdj.get("type", "none"),
    }

def _daily_to_weekly(df):
    """日K线聚合为周K线"""
    if df is None or len(df) < 5: return None
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]) if "date" in df.columns else None
    weekly = []
    i = 0
    while i + 4 < len(df):
        chunk = df.iloc[i:i+5]
        weekly.append({
            "open": float(chunk["open"].iloc[0]),
            "high": float(chunk["high"].max()),
            "low": float(chunk["low"].min()),
            "close": float(chunk["close"].iloc[-1]),
            "volume": float(chunk["volume"].sum()) if "volume" in df.columns else 0,
        })
        i += 5
    return pd.DataFrame(weekly) if weekly else None

def _score_weekly(wk_df):
    """周线评分: MACD柱方向+MA排列"""
    if wk_df is None or len(wk_df) < 8: return 0
    close = wk_df["close"].values
    score = 0
    # MACD柱方向
    if _ema(close, 12)[-1] > _ema(close, 26)[-1]: score += 30
    # MA排列
    ma5 = np.mean(close[-5:]); ma10 = np.mean(close[-10:]) if len(close) >= 10 else ma5
    if close[-1] > ma5: score += 15
    if ma5 > ma10: score += 10
    # 价格位置
    ma20 = np.mean(close[-min(20, len(close)):])
    if close[-1] > ma20: score += 10
    return min(score, 65)

import pandas as pd
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
