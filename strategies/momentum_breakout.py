"""动量突破策略 v1.0 — 20日新高+放量+RS强度+板块共振
与wave_point(趋势低吸)互补: wave_point买回调低点, 本策略买突破新高
理论依据: 欧奈尔CAN SLIM的带柄杯子突破 + 爱德华兹/迈吉的形态突破确认"""
import numpy as np
import logging
logger = logging.getLogger("aurora.momentum")


def check_momentum_breakout(kline_df, market_regime: str = None) -> dict:
    """动量突破检测

    条件:
    1. 价格 >= 20日新高 (突破近期阻力)
    2. 成交量 > 1.5x 20日均量 (放量确认)
    3. 收盘 > MA20 (上升趋势)
    4. MA20 > MA50 (中长期趋势确认)
    5. RS相对强度 > 60 (优于市场平均水平)

    Returns:
        {"signal": bool, "score": 0-100, "detail": str, ...}
    """
    result = {"signal": False, "score": 0, "detail": ""}
    if kline_df is None or len(kline_df) < 50:
        return result

    close = kline_df["close"].values.astype(np.float64)
    high = kline_df["high"].values.astype(np.float64)
    vol = kline_df["volume"].values.astype(np.float64)

    n = len(close)

    # 1. 价格 >= 20日新高
    high_20 = max(high[-20:])
    if close[-1] < high_20 * 0.99:  # 允许1%误差
        result["detail"] = f"收盘{close[-1]:.2f}<20日高{high_20:.2f},未突破"
        return result

    # 2. 成交量 > 1.5x 20日均量
    avg_vol_20 = np.mean(vol[-20:]) if len(vol) >= 20 else np.mean(vol)
    vol_ratio = vol[-1] / avg_vol_20 if avg_vol_20 > 0 else 1
    if vol_ratio < 1.5:
        result["detail"] = f"量比{vol_ratio:.1f}<1.5,放量不足"
        return result

    # 3. 收盘 > MA20 (在MA20之上)
    ma20 = np.mean(close[-20:])
    if close[-1] < ma20:
        result["detail"] = f"收盘{close[-1]:.2f}<MA20{ma20:.2f},不在上升趋势"
        return result

    # 4. MA20 > MA50 (中长期趋势向上)
    if len(close) >= 50:
        ma50 = np.mean(close[-50:])
        if ma20 < ma50:
            result["detail"] = f"MA20{ma20:.2f}<MA50{ma50:.2f},中期趋势向下"
            return result
    else:
        ma50 = ma20  # 数据不足时放宽

    # 5. RS相对强度 > 60 (相对于20日均价的比值)
    rs = (close[-1] / ma20 - 1) * 100  # 价格相对于均线的偏离度
    rs_norm = min(100, max(0, 50 + rs * 5))  # 归一化到0-100
    if rs_norm < 60:
        result["detail"] = f"RS强度{rs_norm:.0f}<60,相对强度不足"
        return result

    # ======= 全部条件通过 =======

    # 评分
    # 基础分: 50
    base = 50

    # 突破强度: 距离20日高的突破幅度
    breakout_pct = (close[-1] / high_20 - 1) * 100
    breakout_score = min(15, max(0, breakout_pct * 5))

    # 量能强度
    vol_score = min(15, max(0, (vol_ratio - 1.5) * 5))

    # 趋势强度: MA20 > MA50 的差值
    trend_strength = (ma20 / ma50 - 1) * 100 if ma50 > 0 else 0
    trend_score = min(10, max(0, trend_strength * 10))

    # RS强度
    rs_score = min(10, max(0, (rs_norm - 60) / 4))

    score = int(base + breakout_score + vol_score + trend_score + rs_score)
    score = min(100, score)

    return {
        "signal": True,
        "score": score,
        "detail": f"动量突破: 新高达{breakout_pct:.1f}% 量比{vol_ratio:.1f} RS={rs_norm:.0f}",
        "breakout_pct": round(breakout_pct, 2),
        "vol_ratio": round(vol_ratio, 2),
        "rs_norm": round(rs_norm, 0),
        "trend_strength": round(trend_strength, 2),
    }