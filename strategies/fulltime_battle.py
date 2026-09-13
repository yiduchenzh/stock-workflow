"""
全职短线客 — 6种入场战法 + 4层瀑布止损 v1.0
来源: data/strategy_fulltime.md 第6章
"""
import numpy as np
import pandas as pd
import logging
logger = logging.getLogger("aurora.fulltime_battle")


def check_a_mode(code, kline_m5, kline_m15, morning_data) -> dict:
    """战法A: 开盘30分钟突破 + 量比>2

    Args:
        code: 股票代码
        kline_m5: 5分钟K线 DataFrame
        kline_m15: 15分钟K线 DataFrame
        morning_data: 早盘市场状态 dict (hour, score, ...)

    Returns:
        dict or None: 信号字典 / 无信号
    """
    hour = morning_data.get("hour", 0)
    if hour < 9.5 or hour >= 10.0:
        return None  # 仅09:30-10:00有效

    # 开盘前15分钟最高价 (09:30 - 09:45)
    high_0930_0945 = kline_m5[
        kline_m5["time"].between("09:30", "09:45")
    ]["high"].max()

    current_price = kline_m5.iloc[-1]["close"]
    current_vol = kline_m5.iloc[-1]["volume"]
    avg_vol_m5 = kline_m5.tail(20)["volume"].mean()
    vol_ratio = current_vol / avg_vol_m5 if avg_vol_m5 > 0 else 0

    ma20_m15 = kline_m15["close"].rolling(20).mean().iloc[-1]
    ma20_m15_prev = kline_m15["close"].rolling(20).mean().iloc[-5]
    ma20_direction = 1 if ma20_m15 > ma20_m15_prev else -1

    # 条件A1: 突破前15分高点
    cond_breakout = current_price > high_0930_0945
    # 条件A2: 量比>2
    cond_volume = vol_ratio > 2.0
    # 条件A3: M15 MA20向上
    cond_trend = ma20_direction > 0 and current_price > ma20_m15

    if not all([cond_breakout, cond_volume, cond_trend]):
        return None

    # 信号强度
    signal_strength = (
        (vol_ratio * 10)
        + ((current_price / high_0930_0945 - 1) * 500)
        + (60 if ma20_direction > 0 else 30)
    )
    if signal_strength < 60:
        return None

    return {
        "code": code,
        "mode": "A",
        "name": "开盘30分钟突破+量比>2",
        "signal_strength": min(signal_strength, 100),
        "entry_price": current_price,
        "stop_loss": high_0930_0945 * 0.995,
        "take_profit_1": current_price * 1.03,
        "take_profit_2": current_price * 1.06,
        "position_pct": 0.25 if signal_strength >= 80 else 0.125,
        "direction": "long",
    }


def check_b_mode(code, tick_data) -> dict:
    """战法B: 首板回封 + 封单比确认

    Args:
        code: 股票代码
        tick_data: tick行情 dict, 包含:
            is_first_board, has_broken, refill_price, first_board_price,
            refill_order_ratio, broken_duration_minutes, turnover_rate,
            refill_speed_seconds

    Returns:
        dict or None
    """
    if not tick_data.get("is_first_board", False):
        return None  # 仅首板
    if not tick_data.get("has_broken", False):
        return None  # 必须炸板过

    refill_price = tick_data.get("refill_price", 0)
    first_board_price = tick_data.get("first_board_price", 0)
    refill_order_ratio = tick_data.get("refill_order_ratio", 0)
    broken_duration = tick_data.get("broken_duration_minutes", 999)
    turnover_rate = tick_data.get("turnover_rate", 0)
    refill_speed = tick_data.get("refill_speed_seconds", 999)

    cond_price = refill_price >= first_board_price * 0.995
    cond_order = refill_order_ratio >= 0.6
    cond_duration = broken_duration <= 30
    cond_turnover = 5 <= turnover_rate <= 20
    if not all([cond_price, cond_order, cond_duration, cond_turnover]):
        return None

    # 回封形态评分
    score_order = (
        40 if refill_order_ratio >= 0.8
        else (25 if refill_order_ratio >= 0.6 else 0)
    )
    score_speed = (
        30 if refill_speed <= 60
        else (20 if refill_speed <= 180
              else (10 if refill_speed <= 600 else 0))
    )
    score_turnover = (
        30 if 8 <= turnover_rate <= 15
        else (15 if 5 <= turnover_rate <= 8 or 15 < turnover_rate <= 20
              else 0)
    )
    total_score = score_order + score_speed + score_turnover
    if total_score < 60:
        return None

    return {
        "code": code,
        "mode": "B",
        "name": "首板回封+封单比确认",
        "signal_strength": total_score,
        "entry_price": refill_price,
        "stop_loss": first_board_price * 0.98,
        "take_profit_1": refill_price * 1.03,  # 次日冲高
        "take_profit_2": None,  # 博连板, 无固定止盈
        "position_pct": 0.20,
        "direction": "long",
    }


def check_c_mode(code, kline_m15, williams) -> dict:
    """战法C: 威廉姆斯超卖反转 + 15分钟K线背离

    Args:
        code: 股票代码
        kline_m15: 15分钟K线 DataFrame (含macd列)
        williams: 威廉姆斯数据 dict, 含 r 键

    Returns:
        dict or None
    """
    if williams.get("r", 0) > -80:
        return None  # 未超卖

    # MACD底背离检测
    macd = kline_m15["macd"]
    price = kline_m15["close"]
    macd_divergence = False
    lowest_idx = price.idxmin()

    if lowest_idx >= 5 and lowest_idx < len(price) - 3:
        prev_low_idx = price[:lowest_idx].idxmin()
        if prev_low_idx >= 3:
            price_lower = price[lowest_idx] < price[prev_low_idx]
            macd_higher = macd[lowest_idx] > macd[prev_low_idx]
            macd_divergence = price_lower and macd_higher

    if not macd_divergence:
        return None

    # 间距距离限制
    current_price = kline_m15["close"].iloc[-1]

    # 底背离强度评分
    div_magnitude = (
        (macd[prev_low_idx] - macd[lowest_idx])
        / abs(macd[prev_low_idx]) * 100
    )
    score_div = 40 if div_magnitude > 5 else (20 if div_magnitude > 1 else 0)

    vol_ratio = (
        kline_m15["volume"].iloc[lowest_idx]
        / kline_m15["volume"].rolling(5).mean().iloc[lowest_idx]
    )
    score_vol = 30 if vol_ratio > 1.2 else 0

    score_total = score_div + score_vol
    if score_total < 50:
        return None

    return {
        "code": code,
        "mode": "C",
        "name": "威廉姆斯超卖反转+M15底背离",
        "signal_strength": score_total,
        "entry_price": current_price * 1.005,
        "stop_loss": kline_m15["low"].iloc[lowest_idx] * 0.99,
        "take_profit_1": current_price * 1.04,
        "take_profit_2": current_price * 1.07,
        "position_pct": 0.15,
        "direction": "long",
    }


def check_d_mode(code, kline_h1, kline_m15, key_levels=None) -> dict:
    """战法D: Naked Pin Bar + 关键位共振

    Args:
        code: 股票代码
        kline_h1: 60分钟K线 DataFrame
        kline_m15: 15分钟K线 DataFrame
        key_levels: 关键位列表 [float, ...]

    Returns:
        dict or None
    """
    if key_levels is None:
        key_levels = []
    last_h1 = kline_h1.iloc[-1]
    body = abs(last_h1["close"] - last_h1["open"])
    upper_shadow = last_h1["high"] - max(last_h1["close"], last_h1["open"])
    lower_shadow = min(last_h1["close"], last_h1["open"]) - last_h1["low"]

    is_bullish_pin = lower_shadow >= body * 2 if body > 0 else False
    is_bearish_pin = upper_shadow >= body * 2 if body > 0 else False
    if not (is_bullish_pin or is_bearish_pin):
        return None

    # 关键位检测
    near_key_level = any(
        abs(last_h1["low"] - level) / level < 0.005
        if is_bullish_pin
        else abs(last_h1["high"] - level) / level < 0.005
        for level in key_levels
    ) if key_levels else True  # 无关键位则不限制

    if not near_key_level:
        return None

    # M15吞噬确认
    last_m15 = kline_m15.iloc[-1]
    prev_m15 = kline_m15.iloc[-2]
    engulf = (
        (is_bullish_pin and last_m15["close"] > prev_m15["high"])
        or (is_bearish_pin and last_m15["close"] < prev_m15["low"])
    )
    if not engulf:
        return None

    avg_vol_h1 = kline_h1["volume"].rolling(20).mean().iloc[-1]
    vol_ratio = last_h1["volume"] / avg_vol_h1 if avg_vol_h1 > 0 else 0

    # 评分
    ratio = (
        lower_shadow / body if is_bullish_pin
        else upper_shadow / body
    )
    score_ratio = 30 if ratio >= 3 else (20 if ratio >= 2 else 10)
    score_level = 30 if near_key_level else 0
    score_vol = 20 if vol_ratio >= 1.5 else (10 if vol_ratio >= 1.3 else 0)
    score_total = score_ratio + score_level + score_vol

    if score_total < 60:
        return None

    return {
        "code": code,
        "mode": "D",
        "name": "Naked Pin Bar+关键位共振",
        "signal_strength": score_total,
        "entry_price": last_h1["close"],
        "stop_loss": (
            last_h1["low"] * 0.995 if is_bullish_pin
            else last_h1["high"] * 1.005
        ),
        "take_profit_1": (
            last_h1["high"] * 1.03 if is_bullish_pin
            else last_h1["low"] * 0.97
        ),
        "position_pct": 0.15,
        "direction": "long" if is_bullish_pin else "short",
    }


def check_e_mode(code, tick_data, kline_m5) -> dict:
    """战法E: 分时W底 + 量价背离 + M5突破

    Args:
        code: 股票代码
        tick_data: tick行情 dict, 含 hour 字段
        kline_m5: 5分钟K线 DataFrame

    Returns:
        dict or None
    """
    hour = tick_data.get("hour", 0)
    if hour < 10.0 or hour >= 14.5:
        return None  # 仅10:00-14:30有效

    # 使用M1级别的W底检测 — 从M5近似
    intraday_lows = kline_m5["low"].rolling(3).min()
    troughs = []
    for i in range(3, len(intraday_lows) - 3):
        if (
            intraday_lows[i] < intraday_lows[i - 1]
            and intraday_lows[i] < intraday_lows[i + 1]
        ):
            troughs.append((i, intraday_lows[i]))

    if len(troughs) < 2:
        return None

    left_bottom = troughs[-2]
    right_bottom = troughs[-1]

    # 右底抬高或持平
    cond_bottom = right_bottom[1] >= left_bottom[1]

    # 量价背离: 右底量 < 左底量
    vol_left = kline_m5["volume"].iloc[left_bottom[0]]
    vol_right = kline_m5["volume"].iloc[right_bottom[0]]
    cond_vol_div = vol_right < vol_left

    if not all([cond_bottom, cond_vol_div]):
        return None

    # 颈线 = 两底之间的高点
    neck_line = kline_m5["high"].iloc[left_bottom[0]:right_bottom[0] + 1].max()

    # M5突破确认
    last_m5 = kline_m5.iloc[-1]
    last_m5_open = last_m5["open"]
    avg_vol_m5 = kline_m5["volume"].rolling(5).mean().iloc[-1]
    vol_ratio_m5 = last_m5["volume"] / avg_vol_m5 if avg_vol_m5 > 0 else 0

    cond_break = last_m5["close"] > neck_line and last_m5["close"] > last_m5_open
    cond_vol = vol_ratio_m5 > 1.5

    if not all([cond_break, cond_vol]):
        return None

    return {
        "code": code,
        "mode": "E",
        "name": "分时W底+量价背离+M5突破",
        "signal_strength": 65,
        "entry_price": last_m5["close"],
        "stop_loss": right_bottom[1] * 0.995,
        "take_profit_1": neck_line + (neck_line - right_bottom[1]),
        "take_profit_2": neck_line + (neck_line - right_bottom[1]) * 1.618,
        "position_pct": 0.15,
        "direction": "long",
    }


def check_f_mode(code, kline_m15, morning_data, kline_m5=None) -> dict:
    """战法F: ORB(开盘区间突破) + 加速确认

    Args:
        code: 股票代码
        kline_m15: 15分钟K线 DataFrame (含time列)
        morning_data: 早盘数据 dict
        kline_m5: 5分钟K线 DataFrame (备用)

    Returns:
        dict or None
    """
    hour = morning_data.get("hour", 0)
    if hour < 9.75 or hour > 10.5:
        return None  # 仅09:45-10:30

    # ORB区间从M5获取
    df_m5 = kline_m5 if kline_m5 is not None else kline_m15
    orb_high = df_m5[df_m5["time"].between("09:30", "09:45")]["high"].max()
    orb_low = df_m5[df_m5["time"].between("09:30", "09:45")]["low"].min()
    orb_vol_avg = df_m5[df_m5["time"].between("09:30", "09:45")]["volume"].mean()

    current_price = df_m5.iloc[-1]["close"]
    current_vol = df_m5.iloc[-1]["volume"]
    current_open = df_m5.iloc[-1]["open"]

    if current_price <= orb_high:
        return None  # 未突破

    vol_ratio = current_vol / orb_vol_avg if orb_vol_avg > 0 else 0

    # 不回撤确认
    prev_m5 = df_m5.iloc[-2]
    cond_no_retrace = prev_m5["low"] > orb_high or current_open > orb_high

    cond_vol = vol_ratio > 1.5
    if not all([cond_vol, cond_no_retrace]):
        return None

    signal_strength = min(vol_ratio * 35 + 65, 100)

    return {
        "code": code,
        "mode": "F",
        "name": "ORB+加速确认",
        "signal_strength": signal_strength,
        "entry_price": current_price,
        "stop_loss": orb_high * 0.995,
        "take_profit_1": current_price + (orb_high - orb_low) * 1.5,
        "take_profit_2": None,  # M60前高
        "position_pct": 0.20,
        "direction": "long",
    }


def waterfall_stop(code, pos, price, kline_m1) -> dict:
    """4层瀑布止损检查

    第4层: 硬止损 -5%
    第1层: 正常止损 -3%
    第3层: M1破位+量比>2 (浮亏>-2%触发)
    第2层: M15连续3根阴线 (浮亏>-2%触发)

    Args:
        code: 股票代码
        pos: 持仓信息 dict, 含 avg_cost
        price: 当前价格
        kline_m1: 1分钟K线 DataFrame

    Returns:
        dict: {"action": "force_sell"/"sell_all"/None, "reason": str}
    """
    cost = pos.get("avg_cost", pos.get("cost", 0))
    if cost <= 0:
        return None

    loss_pct = (price / cost - 1) * 100

    # 第4层: 硬止损 -5%
    if loss_pct <= -5:
        return {"action": "force_sell", "reason": "硬止损-5%", "priority": 0}

    # 第1层: 正常止损 -3%
    if loss_pct <= -3:
        return {"action": "sell_all", "reason": f"瀑布止损-3%", "priority": 1}

    # 第3层: M1破位+量比>2
    if loss_pct <= -2 and kline_m1 is not None and len(kline_m1) > 5:
        m1_break = kline_m1["close"].iloc[-1] < kline_m1["low"].iloc[-2]
        m1_vol_ratio = (
            kline_m1["volume"].iloc[-1]
            / kline_m1["volume"].rolling(5).mean().iloc[-1]
        )
        if m1_break and m1_vol_ratio > 2:
            return {
                "action": "sell_all",
                "reason": "M1放量破位",
                "priority": 1,
            }

    # 第2层: M15连续3根阴线
    if loss_pct <= -2 and kline_m1 is not None and len(kline_m1) >= 3:
        # 将M1重采样为M15近似判断
        last_3 = kline_m1.tail(3)
        if all(last_3["close"] < last_3["open"]):
            return {
                "action": "sell_all",
                "reason": "M1三连阴加速",
                "priority": 2,
            }

    return None
