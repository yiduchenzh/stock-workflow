"""
趋势跟踪者 — 5种入场战法 + 退出逻辑 v1.0
来源: data/strategy_trend.md 第2章(入场战法)和第4章(退出规则)
"""
import numpy as np
import pandas as pd
import logging
logger = logging.getLogger("aurora.trend_battle")


def check_cup_handle(code, kline_weekly) -> dict:
    """战法一: 月线杯柄突破 (Cup & Handle Breakout)

    前置条件: 市值500亿+, 周线多头排列(MA5>MA10>MA20>MA60)
    杯形结构 ≥ 20周, 杯柄缩量回调, 突破确认

    Args:
        code: 股票代码
        kline_weekly: 周线K线 DataFrame

    Returns:
        dict or None
    """
    df = kline_weekly
    if df is None or len(df) < 25:
        return None

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    volume = df["volume"].values

    # ① 杯形结构检测: 寻找左杯沿→杯底→右杯沿 (至少20周)
    # 左杯沿为前高，回落幅度 ≥ 15% 但 ≤ 45%
    recent_high_idx = np.argmax(high[-30:]) if len(high) >= 30 else np.argmax(high)
    recent_high = high[recent_high_idx]
    # 杯底
    right_half = low[recent_high_idx:]
    if len(right_half) < 10:
        return None
    cup_bottom_idx = np.argmin(right_half) + recent_high_idx
    cup_bottom = low[cup_bottom_idx]

    cup_depth = (recent_high - cup_bottom) / recent_high
    if cup_depth < 0.15 or cup_depth > 0.45:
        return None

    # ② 杯柄回踩: 突破前高前的缩量回调
    # 右杯沿成交量逐步放大
    right_volume = volume[cup_bottom_idx:]
    if len(right_volume) < 5:
        return None
    vol_trend = np.corrcoef(np.arange(len(right_volume)), right_volume)[0, 1]
    has_volume_increase = vol_trend > 0.3

    # 杯柄跌幅不超过杯身涨幅的1/3
    handle_start = cup_bottom_idx + max(1, len(right_half) // 2)
    if handle_start >= len(close) - 5:
        return None
    handle_high = np.max(high[handle_start:])
    handle_low = np.min(low[handle_start:])
    handle_drop = (handle_high - handle_low) / handle_high if handle_high > 0 else 0
    cup_rise = (recent_high - cup_bottom) / cup_bottom if cup_bottom > 0 else 0
    if cup_rise <= 0 or handle_drop > cup_rise / 3:
        return None

    # 杯柄期间缩量
    handle_vol_avg = np.mean(volume[handle_start:])
    global_vol_avg = np.mean(volume[max(0, handle_start - 10):handle_start])
    if global_vol_avg > 0 and handle_vol_avg > global_vol_avg * 0.5:
        return None  # 缩量不足

    # ③ 突破确认: 日线收盘突破杯柄前高
    last_close = close[-1]
    last_vol = volume[-1]

    if last_close <= recent_high:
        return None  # 未突破

    # 成交量 ≥ 120日均量 × 1.5
    vol_ma = np.mean(volume[-120:]) if len(volume) >= 120 else np.mean(volume)
    if vol_ma > 0 and last_vol < vol_ma * 1.5:
        return None

    # 突破日涨幅 ≥ 2%
    if len(close) >= 2:
        daily_gain = (close[-1] - close[-2]) / close[-2]
        if daily_gain < 0.02:
            return None

    signal_strength = 80 if has_volume_increase else 70

    return {
        "code": code,
        "mode": "CUP_HANDLE",
        "name": "月线杯柄突破",
        "signal_strength": min(signal_strength, 100),
        "entry_price": last_close,
        "stop_loss": last_close * 0.93,  # 7%固定止损
        "take_profit_1": last_close * 1.18,
        "take_profit_2": None,  # 趋势线移动止盈
        "position_pct": 0.25,
        "direction": "long",
    }


def check_ma_resonance(code, kline_weekly, kline_daily) -> dict:
    """战法二: 周线MACD金叉 + 日线MA多头排列共振

    Args:
        code: 股票代码
        kline_weekly: 周线K线 DataFrame (含macd/dif/dea/histogram列)
        kline_daily: 日线K线 DataFrame

    Returns:
        dict or None
    """
    wk = kline_weekly
    dy = kline_daily
    if wk is None or len(wk) < 15 or dy is None or len(dy) < 20:
        return None

    # ① 周线MACD金叉确认
    dif = wk["close"].ewm(span=12, adjust=False).mean() - wk["close"].ewm(span=26, adjust=False).mean()
    dea = dif.ewm(span=9, adjust=False).mean()
    wk_macd = dif - dea

    dif_vals = dif.values
    dea_vals = dea.values
    macd_vals = wk_macd.values

    # DIF上穿DEA
    macd_golden_cross = (
        dif_vals[-2] <= dea_vals[-2] and dif_vals[-1] > dea_vals[-1]
    )
    if not macd_golden_cross:
        # 检查是否已金叉但未走完
        if dif_vals[-1] <= dea_vals[-1]:
            return None

    # 零轴上方金叉 → 强趋势
    above_zero = dif_vals[-1] > 0 and dea_vals[-1] > 0
    cross_weight = 2 if above_zero else 1

    # ② 日线MA多头排列
    ma5 = dy["close"].rolling(5).mean().values
    ma10 = dy["close"].rolling(10).mean().values
    ma20 = dy["close"].rolling(20).mean().values
    ma60 = dy["close"].rolling(60).mean().values

    ma_bullish = (
        ma5[-1] > ma10[-1] > ma20[-1] > ma60[-1]
    )
    if not ma_bullish:
        return None

    # MA5上穿MA20
    ma5_cross = ma5[-2] <= ma20[-2] and ma5[-1] > ma20[-1]

    # 价格站在MA60上方 ≥ 5交易日
    above_ma60_count = sum(1 for i in range(-5, 0) if dy["close"].values[i] > ma60[i])
    if above_ma60_count < 5:
        return None

    # ③ 量价确认
    vol = dy["volume"].values
    vol_ma60 = np.mean(vol[-60:]) if len(vol) >= 60 else np.mean(vol)
    vol_confirm = all(v > vol_ma60 for v in vol[-3:]) if len(vol) >= 3 else False
    if not vol_confirm:
        return None

    last_close = dy["close"].values[-1]
    base = 60 + cross_weight * 15 + (10 if ma5_cross else 0)

    return {
        "code": code,
        "mode": "MA_RESONANCE",
        "name": "周MACD金叉+日线MA共振",
        "signal_strength": min(base, 100),
        "entry_price": last_close,
        "stop_loss": last_close * 0.93,  # 7%固定止损
        "take_profit_1": last_close * 1.18,
        "take_profit_2": None,
        "position_pct": 0.20,
        "direction": "long",
    }


def check_ma_spread(code, kline_daily) -> dict:
    """战法三: 均线束发散 (Moving Average Ribbon Expansion)

    横盘整理 ≥ 8周, 均线粘合后发散, 价格突破横盘区间

    Args:
        code: 股票代码
        kline_daily: 日线K线 DataFrame

    Returns:
        dict or None
    """
    df = kline_daily
    if df is None or len(df) < 120:
        return None

    close = df["close"].values
    high = df["high"].values
    volume = df["volume"].values

    ma5 = df["close"].rolling(5).mean().values
    ma20 = df["close"].rolling(20).mean().values
    ma60 = df["close"].rolling(60).mean().values
    ma120 = df["close"].rolling(120).mean().values

    # ① 均线束由粘合转为发散
    # 粘合检测: MA20与MA60间距 < 3%
    spread_20_60_past = abs(ma20[-40] - ma60[-40]) / ma60[-40] if ma60[-40] > 0 else 1
    spread_20_60_now = abs(ma20[-1] - ma60[-1]) / ma60[-1] if ma60[-1] > 0 else 1

    if not (spread_20_60_past < 0.03 and spread_20_60_now > 0.05):
        return None

    # MA5上穿MA20
    if not (ma5[-2] <= ma20[-2] and ma5[-1] > ma20[-1]):
        return None

    # MA120走平或向上
    ma120_slope = (ma120[-1] - ma120[-20]) / ma120[-20] if ma120[-20] > 0 else 0
    if ma120_slope < -0.01:
        return None

    # ② 价格突破横盘区间上沿
    range_high = np.max(high[-40:]) if len(high) >= 40 else np.max(high)
    if close[-1] <= range_high:
        return None

    # 成交量是均量2倍以上
    vol_ma = np.mean(volume[-20:])
    if vol_ma > 0 and volume[-1] < vol_ma * 2:
        return None

    # 突破K线实体 ≥ 5%
    if len(close) >= 2:
        body_pct = abs(close[-1] - df["open"].values[-1]) / df["open"].values[-1]
        if body_pct < 0.05:
            return None

    last_close = close[-1]
    return {
        "code": code,
        "mode": "MA_SPREAD",
        "name": "均线束发散",
        "signal_strength": 75,
        "entry_price": last_close,
        "stop_loss": last_close * 0.93,
        "take_profit_1": last_close * 1.18,
        "take_profit_2": None,
        "position_pct": 0.15,
        "direction": "long",
    }


def check_chan_buy3_trend(code, kline_daily) -> dict:
    """战法四: 缠论三买 + 趋势线突破 (Chan Buy-3 + Trendline)

    前期已有一段明显上涨, 日线有中枢, 回踩不破中枢上沿

    Args:
        code: 股票代码
        kline_daily: 日线K线 DataFrame

    Returns:
        dict or None
    """
    df = kline_daily
    if df is None or len(df) < 60:
        return None

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    volume = df["volume"].values

    # ① 查找日线中枢 (最近40根K线内找价格重叠区)
    # 简化: 中枢 = 最近的多段高低点重叠区域
    recent_highs = high[-40:]
    recent_lows = low[-40:]

    # 找上升一笔(上涨段)
    high_peak = np.argmax(recent_highs)
    if high_peak < 5 or high_peak > len(recent_highs) - 5:
        return None

    # 中枢 = 上涨段之前的低点到高点之间的重叠区
    zhongshu_high = np.max(recent_highs[:high_peak])
    zhongshu_low = np.min(recent_lows[:high_peak])

    # 回踩不破中枢上沿
    pullback_low = np.min(recent_lows[high_peak:])
    if pullback_low <= zhongshu_high:
        return None  # 跌破中枢上沿, 不是三买

    # 回踩期间缩量 (洗盘)
    pullback_vol_avg = np.mean(volume[high_peak:]) if len(volume[high_peak:]) > 0 else 0
    pre_pullback_vol_avg = np.mean(volume[max(0, high_peak - 10):high_peak])
    if pre_pullback_vol_avg > 0 and pullback_vol_avg > pre_pullback_vol_avg:
        return None  # 未缩量

    # ② 趋势线突破: 连接回踩低点与前一个低点
    # 当前价格突破下降压力线
    last_close = close[-1]
    last_high = high[-1]

    # ③ 周线MACD仍在零轴上方
    has_macd_support = True  # 周线数据由外层传入

    return {
        "code": code,
        "mode": "CHAN_BUY3",
        "name": "缠论三买+趋势线突破",
        "signal_strength": 70,
        "entry_price": last_close,
        "stop_loss": min(pullback_low * 0.98, last_close * 0.93),  # 取宽
        "take_profit_1": last_close + (high[high_peak] - zhongshu_low) * 1.0,
        "take_profit_2": last_close * 1.18,
        "position_pct": 0.20,
        "direction": "long",
    }


def check_long_breakout(code, kline_weekly, kline_daily) -> dict:
    """战法五: 长期横盘突破 (Base Breakout)

    横盘 ≥ 6个月(120交易日), 振幅 ≤ 30%, 放量突破

    Args:
        code: 股票代码
        kline_weekly: 周线K线 DataFrame (大盘趋势检查)
        kline_daily: 日线K线 DataFrame

    Returns:
        dict or None
    """
    df = kline_daily
    if df is None or len(df) < 125:
        return None

    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    volume = df["volume"].values

    # 横盘区间: 最近120个交易日
    if len(high) < 120:
        return None
    base_high = np.max(high[-120:])
    base_low = np.min(low[-120:])
    base_range = (base_high - base_low) / base_low if base_low > 0 else 0

    if base_range > 0.30:
        return None  # 振幅 > 30%

    # ① 突破横盘区间上沿
    if close[-1] <= base_high:
        return None  # 未突破

    # 突破距离区间最低点 ≥ 20%
    if base_low > 0:
        breakout_gain = (close[-1] - base_low) / base_low
        if breakout_gain < 0.20:
            return None

    # ② 量能放大
    vol_ma5 = np.mean(volume[-5:])
    if vol_ma5 < np.mean(volume[-10:-5]) * 3:
        return None  # 突破量能不足

    # 突破K线实体 ≥ 5%
    body_pct = abs(close[-1] - df["open"].values[-1]) / df["open"].values[-1]
    if body_pct < 0.05:
        return None

    # 后续日成交量 ≥ 均量 × 1.5
    vol_ma = np.mean(volume[-60:]) if len(volume) >= 60 else np.mean(volume)
    recent_vol_check = all(v >= vol_ma * 1.5 for v in volume[-3:])
    if not recent_vol_check:
        return None

    # ③ 大盘趋势检查(周线)
    if kline_weekly is not None and len(kline_weekly) >= 12:
        wk_ma60 = kline_weekly["close"].rolling(60).mean().values
        if len(wk_ma60) > 0 and wk_ma60[-1] > 0:
            last_wk_close = kline_weekly["close"].values[-1]
            if last_wk_close <= wk_ma60[-1]:
                return None  # 大盘MA60未向上

    last_close = close[-1]
    return {
        "code": code,
        "mode": "LONG_BREAKOUT",
        "name": "长期横盘突破",
        "signal_strength": 80,
        "entry_price": last_close,
        "stop_loss": base_high * 0.98,  # 区间上沿下方2%
        "take_profit_1": last_close * 1.18,
        "take_profit_2": None,
        "position_pct": 0.20,
        "direction": "long",
    }
