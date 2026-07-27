"""
[Soul] 市场直觉量化器 — 情绪指数合成 + 异常检测
- 情绪指数: 涨跌比(30%)+涨停数(15%)+量能比(25%)+北向(15%)+波动率(15%)
- 异常检测: 量能突变(>3σ)、价格加速度异常、宽幅震荡
"""
import logging
import numpy as np

logger = logging.getLogger("aurora.soul.market_intuition")

SENTIMENT_WEIGHTS = {
    "breadth": 0.30,
    "limit_up": 0.15,
    "volume": 0.25,
    "northbound": 0.15,
    "volatility": 0.15,
}

def calc_market_anomaly(kline_df) -> dict:
    """
    检测市场异常状态
    Args:
        kline_df: DataFrame with columns ['close','high','low','volume']
    Returns:
        dict: {anomaly_detected: bool, volume_anomaly: str, accel_anomaly: str,
               range_anomaly: str, details: dict}
    """
    result = {
        "anomaly_detected": False,
        "volume_anomaly": "normal",
        "accel_anomaly": "normal",
        "range_anomaly": "normal",
        "details": {},
    }
    try:
        if kline_df is None or len(kline_df) < 20:
            return result

        close = np.asarray(kline_df["close"].values, dtype=np.float64)
        volume = np.asarray(kline_df["volume"].values, dtype=np.float64)
        high = np.asarray(kline_df["high"].values, dtype=np.float64)
        low = np.asarray(kline_df["low"].values, dtype=np.float64)
        n = len(close)

        # --- 量能突变检测(>3σ) ---
        vol_mean = np.mean(volume[-20:])
        vol_std = np.std(volume[-20:]) or 1e-10
        vol_z = (volume[-1] - vol_mean) / vol_std
        if vol_z > 3.0:
            result["volume_anomaly"] = "surge"
            result["anomaly_detected"] = True
        elif vol_z < -3.0:
            result["volume_anomaly"] = "drought"
            result["anomaly_detected"] = True
        elif vol_z > 2.0:
            result["volume_anomaly"] = "elevated"
        result["details"]["vol_z_score"] = round(float(vol_z), 2)

        # --- 价格加速度异常 ---
        if n >= 10:
            ret_1d = close[-1] / close[-2] - 1 if close[-2] != 0 else 0
            ret_5d = close[-1] / close[-6] - 1 if n >= 6 and close[-6] != 0 else 0
            ret_10d = close[-1] / close[-11] - 1 if n >= 11 and close[-11] != 0 else 0
            accel = ret_5d - ret_10d if ret_10d != 0 else 0
            # 加速度: 最近5日涨幅 vs 前5日涨幅的超额
            if abs(accel) > 0.08:
                result["accel_anomaly"] = "sharp_acceleration" if accel > 0 else "sharp_deceleration"
                result["anomaly_detected"] = True
            elif abs(accel) > 0.04:
                result["accel_anomaly"] = "mild_acceleration" if accel > 0 else "mild_deceleration"
            result["details"]["ret_1d"] = round(float(ret_1d * 100), 2)
            result["details"]["ret_5d"] = round(float(ret_5d * 100), 2)
            result["details"]["accel"] = round(float(accel * 100), 2)

        # --- 宽幅震荡检测 ---
        if n >= 20:
            ranges = (high[-20:] - low[-20:]) / close[-20:] * 100
            recent_range = (high[-1] - low[-1]) / close[-1] * 100
            range_mean = np.mean(ranges)
            range_std = np.std(ranges) or 1e-10
            range_z = (recent_range - range_mean) / range_std
            if range_z > 3.0:
                result["range_anomaly"] = "wide_oscillation"
                result["anomaly_detected"] = True
            elif range_z > 2.0:
                result["range_anomaly"] = "elevated_oscillation"
            result["details"]["range_z_score"] = round(float(range_z), 2)
            result["details"]["recent_range_pct"] = round(float(recent_range), 2)

        logger.info(f"[Soul] market_anomaly: vol={result['volume_anomaly']} "
                     f"accel={result['accel_anomaly']} range={result['range_anomaly']} "
                     f"anomaly={result['anomaly_detected']}")
    except Exception as e:
        logger.warning(f"[Soul] calc_market_anomaly 异常: {e}")

    return result


def calc_sentiment_index(breadth: float, limit_up: int, volume: float, northbound: float) -> float:
    """
    合成情绪指数 (0-100)
    Args:
        breadth: 涨跌比(0~1, 如0.6表示60%个股上涨)
        limit_up: 涨停家数
        volume: 量能比(今日成交额/20日均值, 1.5=放量50%)
        northbound: 北向资金评分(0-100)
    Returns:
        float: 情绪指数 0-100
    """
    try:
        # 涨跌比分(30%): breadth 0~1 → 0~100
        breadth_score = min(100, max(0, breadth * 100))

        # 涨停数分(15%): 50只涨停=100分
        limit_up_score = min(100, limit_up / 50 * 100) if limit_up >= 0 else 0

        # 量能比分(25%): 1.0=50分, 2.0=100分, 0.5=0分
        volume_score = min(100, max(0, (volume - 0.5) / 1.5 * 100)) if volume > 0 else 50

        # 北向分(15%): 直接使用(0-100)
        nb_score = min(100, max(0, northbound))

        # 波动率分(15%): 偏低波动加分(平稳), 过高波动减分(恐慌)
        vol_score = 50  # 默认中性

        sentiment = (
            breadth_score * SENTIMENT_WEIGHTS["breadth"]
            + limit_up_score * SENTIMENT_WEIGHTS["limit_up"]
            + volume_score * SENTIMENT_WEIGHTS["volume"]
            + nb_score * SENTIMENT_WEIGHTS["northbound"]
            + vol_score * SENTIMENT_WEIGHTS["volatility"]
        )

        sentiment = min(100, max(0, round(sentiment, 1)))
        logger.info(f"[Soul] sentiment={sentiment:.1f} "
                     f"(breadth={breadth_score:.0f} lu={limit_up_score:.0f} "
                     f"vol={volume_score:.0f} nb={nb_score:.0f})")
        return sentiment
    except Exception as e:
        logger.warning(f"[Soul] calc_sentiment_index 异常: {e}")
        return 50.0
