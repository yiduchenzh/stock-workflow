"""均值回归策略 v1.0 — RSI<30+BOLL下轨+连续下跌+放量恐慌
与wave_point(趋势跟随)低相关, 独立正期望验证"""
import numpy as np
import logging
logger = logging.getLogger("aurora.mean_rev")

def check_mean_reversion(kline_df) -> dict:
    """均值回归检测

    条件:
    1. 连续下跌≥3日 (短期超卖)
    2. RSI(14) < 35 (经典超卖区)
    3. 收盘价 < BOLL下轨 (统计极端)
    4. 量比 > 1.2 (恐慌放量或承接放量)
    5. 价格 > 5日均量均价*0.5 (非仙股流动性过滤)

    Returns:
        {"signal": bool, "score": 0-100, "detail": str}
    """
    result = {"signal": False, "score": 0, "detail": ""}
    if kline_df is None or len(kline_df) < 30:
        return result

    close = kline_df["close"].values.astype(np.float64)
    high = kline_df["high"].values.astype(np.float64)
    low = kline_df["low"].values.astype(np.float64)
    vol = kline_df["volume"].values.astype(np.float64)

    # 1. 连续下跌≥3日
    chg = np.diff(close) / close[:-1] * 100
    recent_chg = chg[-5:]  # 最近5日涨跌幅
    consec_days = 0
    for c in reversed(recent_chg):
        if c < -0.5:
            consec_days += 1
        else:
            break
    if consec_days < 3:
        result["detail"] = f"连续下跌{consec_days}日<3"
        return result

    # 2. RSI(14) < 35
    delta = np.diff(close)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    if len(gain) >= 14:
        avg_gain = np.mean(gain[-14:])
        avg_loss = np.mean(loss[-14:])
    else:
        avg_gain = np.mean(gain)
        avg_loss = np.mean(loss)
    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - 100 / (1 + rs)

    if rsi > 35:
        result["detail"] = f"RSI={rsi:.0f}>35,未超卖"
        return result

    # 3. 收盘价 < BOLL下轨 (20日均线-2σ)
    ma20 = np.mean(close[-20:])
    std20 = np.std(close[-20:])
    lower_band = ma20 - 2 * std20
    if close[-1] > lower_band:
        result["detail"] = f"收盘{close[-1]:.2f}>BOLL下轨{lower_band:.2f},未极端"
        return result

    # 4. 量比 > 1.2
    avg_vol = np.mean(vol[-20:]) if len(vol) >= 20 else np.mean(vol)
    vol_ratio = vol[-1] / avg_vol if avg_vol > 0 else 1
    if vol_ratio < 1.2:
        result["detail"] = f"量比{vol_ratio:.1f}<1.2,无放量"
        return result

    # 5. 流动性过滤
    avg_dollar_vol = np.mean(close[-20:] * vol[-20:]) if len(close) >= 20 else close[-1] * vol[-1]
    if avg_dollar_vol < 5_000_000:
        result["detail"] = f"日均成交额{avg_dollar_vol/1e4:.0f}万<500万"
        return result

    # 评分: 超卖程度+量比+下跌天数
    rsi_score = max(0, 35 - rsi) * 2  # RSI越低分越高
    vol_score = min(int((vol_ratio - 1.0) * 15), 20)
    consec_score = min(consec_days * 8, 24)
    # BOLL偏离越深分越高
    dev_pct = (lower_band - close[-1]) / close[-1] * 100
    boll_score = min(max(0, dev_pct * 10), 16)
    score = min(100, 30 + rsi_score + vol_score + consec_score + boll_score)

    return {
        "signal": True,
        "score": int(score),
        "detail": f"均值回归: RSI={rsi:.0f} BOLL偏离={dev_pct:.1f}% 连跌{consec_days}日 量比{vol_ratio:.1f}",
        "rsi": round(rsi, 1),
        "boll_dev_pct": round(dev_pct, 2),
        "consec_days": consec_days,
        "vol_ratio": round(vol_ratio, 2),
    }