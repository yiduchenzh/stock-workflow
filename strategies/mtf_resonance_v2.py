"""多周期共振 v2.0 — 新增Scheme B: 日线→小时→15分钟 对比方案"""
import numpy as np

def check_mtf_resonance_v2(kline_df, code=None):
    """方案B: 日线定方向→小时找买点→15分精入场 (对比方案A的周线→日线→60分)
    
    周期关系: 日线(4h×6天) → 小时(60min) → 15分钟
    适用: 短线交易, 持股1-3天
    """
    if kline_df is None or len(kline_df) < 30:
        return {"resonance": False, "score": 0, "scheme": "B", "detail": "数据不足(<30日)"}
    
    close = kline_df["close"].values
    vol = kline_df["volume"].values if "volume" in kline_df.columns else np.ones(len(close))
    
    # 第一重: 日线趋势 (定方向) — MACD柱+MA排列
    ema12 = _ema(close, 12); ema26 = _ema(close, 26)
    dif = np.array([ema12[i] - ema26[i] for i in range(len(ema12))])
    dea = _ema(dif, 9)
    macd_hist = dif - dea
    
    ma20 = np.mean(close[-20:]) if len(close) >= 20 else np.mean(close)
    ma60 = np.mean(close[-60:]) if len(close) >= 60 else ma20
    
    # 日线方向评分 (0-40分)
    daily_score = 0
    if macd_hist[-1] > 0 and macd_hist[-1] > macd_hist[-2]:
        daily_score = 35  # MACD多头+发散
    elif macd_hist[-1] > 0:
        daily_score = 25  # MACD多头但收敛
    elif macd_hist[-1] > macd_hist[-2] and macd_hist[-1] > -1:
        daily_score = 15  # MACD回升中
    else:
        daily_score = 5   # MACD空头
    
    # MA排列加分
    if close[-1] > ma20 > ma60:
        daily_score = min(40, daily_score + 5)
    
    if daily_score < 20:
        return {"resonance": False, "score": 0, "scheme": "B",
                "detail": f"日线无上升趋势({daily_score})", "daily_score": daily_score}
    
    # 第二重: 60分钟(小时)级别 — 找买点
    hour_score = 0
    try:
        # 用分钟K线API获取小时线 (60分钟K线)
        hour_k = None
        if code:
            from data.sources import get_kline_period
            hour_k = get_kline_period(code, "60min", 48)
        if hour_k is not None and not hour_k.empty and len(hour_k) >= 20:
            h_close = hour_k["close"].values
            h_vol = hour_k["volume"].values
            h_ema12 = _ema(h_close, 12)
            h_ema26 = _ema(h_close, 26)
            h_dif = np.array([h_ema12[i] - h_ema26[i] for i in range(len(h_ema12))])
            h_dea = _ema(h_dif, 9)
            h_rsi = _rsi(h_close, 14)
            h_ma20 = np.mean(h_close[-20:])
            
            # 小时级别买入条件
            hour_ok = h_dif[-1] > h_dea[-1] and 35 <= h_rsi <= 65
            h_vol_ratio = h_vol[-1] / (np.mean(h_vol[-20:]) or 1)
            h_trigger = h_close[-1] > h_ma20 and h_vol_ratio > 1.2
            
            if hour_ok: hour_score = 20
            if h_trigger: hour_score += 10
        else:
            # 降级到日线内部判断
            if macd_hist[-1] > 0: hour_score = 15
    except:
        hour_score = 10
    
    # 第三重: 15分钟级别 — 精入场
    min15_score = 0
    try:
        m15_k = None
        if code:
            from data.sources import get_kline_period
            m15_k = get_kline_period(code, "15min", 48)
        if m15_k is not None and not m15_k.empty and len(m15_k) >= 20:
            m_close = m15_k["close"].values
            m_vol = m15_k["volume"].values
            m_ma10 = np.mean(m_close[-10:])
            m_vol_ratio = m_vol[-1] / (np.mean(m_vol[-20:]) or 1)
            m_up = m_close[-1] > m_close[-3]
            
            if m_close[-1] > m_ma10 and m_vol_ratio > 1.5 and m_up:
                min15_score = 25  # 放量突破10均线
            elif m_close[-1] > m_ma10 and m_up:
                min15_score = 15  # 站上均线
            elif m_up:
                min15_score = 8   # 小幅上涨
            else:
                min15_score = 3   # 下跌
        else:
            # 降级: 用小时线近似
            min15_score = 10 if hour_score > 15 else 5
    except:
        min15_score = 5
    
    # MACD底背离检查 (日线级别)
    from strategies.indicator_system import detect_macd_divergence
    try:
        macd = detect_macd_divergence(kline_df)
        div_bonus = 15 if macd.get("direction") == "bullish" else 0
    except:
        div_bonus = 0
    
    # 综合评分
    total = daily_score + hour_score + min15_score + div_bonus
    resonance = total >= 55
    
    return {
        "resonance": resonance,
        "score": min(total, 100),
        "scheme": "B",
        "detail": f"日{daily_score}小{hour_score}15{min15_score}背{div_bonus}",
        "daily_score": daily_score,
        "hour_score": hour_score,
        "min15_score": min15_score,
        "div_bonus": div_bonus,
    }


def _ema(arr, period):
    """EMA计算 (纯numpy)"""
    if len(arr) < 1: return np.array([])
    result = np.zeros(len(arr))
    multiplier = 2 / (period + 1)
    result[0] = arr[0]
    for i in range(1, len(arr)):
        result[i] = (arr[i] - result[i-1]) * multiplier + result[i-1]
    return result

def _rsi(close, period=14):
    """RSI计算"""
    if len(close) < period + 1: return 50
    deltas = np.diff(close)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0: return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
