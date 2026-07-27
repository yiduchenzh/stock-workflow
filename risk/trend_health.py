"""
趋势健康度评分模块 — P0升级
============================
作用: 对每个持仓进行逐级健康评分，实现持仓动态管理。
代替"要么持有要么止损"的二值判断，改为渐进式分级响应。

使用方式:
    from risk.trend_health import calc_trend_health
    health = calc_trend_health(code, kline_df, regime)
    # health: 0-100, 越低越危险

分级响应:
    ≥80  持有, 正常监控
    60-79 预警: 收紧止损至ATR×1.5
    40-59 减仓1/3, 收紧止损
    20-39 减半仓
    <20   清仓
"""
import logging
import numpy as np

logger = logging.getLogger("aurora.trend_health")


def calc_trend_health(code: str, kline_df, regime: str = "range") -> int:
    """
    计算持仓趋势健康度 (0-100)
    
    Params:
        code: 股票代码
        kline_df: 日K线DataFrame (至少20行), 需含 close/open/high/low/volume
        regime: 当前市场状态 (影响评分权重)
    
    Returns:
        score: 0-100 健康度评分
        details: dict 各维度得分
    """
    if kline_df is None or (hasattr(kline_df, 'empty') and kline_df.empty):
        return 50, {"error": "no_data", "score": 50}
    
    try:
        closes = kline_df["close"].values
        highs = kline_df["high"].values
        lows = kline_df["low"].values
        opens = kline_df["open"].values
        volumes = kline_df["volume"].values
    except (KeyError, AttributeError, IndexError):
        return 50, {"error": "columns", "score": 50}
    
    n = len(closes)
    if n < 5:
        return 50, {"error": "too_short", "score": 50}
    
    score = 100
    dims = {}
    
    # ─── 维度1: 均线形态 (权重30%) ───
    dim1 = _calc_ma_score(closes, n)
    dims["ma"] = dim1
    
    # ─── 维度2: MACD状态 (权重25%) ───
    dim2 = _calc_macd_score(closes, n)
    dims["macd"] = dim2
    
    # ─── 维度3: 量价关系 (权重20%) ───
    dim3 = _calc_volume_score(closes, volumes, n)
    dims["volume"] = dim3
    
    # ─── 维度4: K线形态 (权重15%) ───
    dim4 = _calc_kline_score(opens, closes, highs, lows, n)
    dims["kline"] = dim4
    
    # ─── 维度5: 波动与趋势强度 (权重10%) ───
    dim5 = _calc_trend_strength(closes, highs, lows, n)
    dims["trend_strength"] = dim5
    
    # ─── 综合评分 ───
    weights = {"ma": 30, "macd": 25, "volume": 20, "kline": 15, "trend_strength": 10}
    
    # regime调整权重: bear_weak下MACD权重增加(更敏感), trend_strength减少
    if regime and "bear" in regime:
        weights = {"ma": 25, "macd": 30, "volume": 20, "kline": 15, "trend_strength": 10}
    elif regime and "bull" in regime:
        weights = {"ma": 35, "macd": 20, "volume": 15, "kline": 15, "trend_strength": 15}
    
    composite = sum(dims[k] * weights[k] for k in dims) / sum(weights.values())
    score = max(0, min(100, int(composite)))
    
    return score, dims


def _calc_ma_score(closes, n) -> int:
    """均线形态评分 (0-100)"""
    s = 100
    ma5 = np.mean(closes[-5:]) if n >= 5 else closes[-1]
    ma10 = np.mean(closes[-10:]) if n >= 10 else closes[-1]
    ma20 = np.mean(closes[-20:]) if n >= 20 else closes[-1]
    cur = closes[-1]
    
    # 价格与均线关系
    if cur < ma20: s -= 25  # 跌破MA20
    elif cur < ma10: s -= 15  # 跌破MA10
    
    # 均线排列
    if ma5 < ma10: s -= 20   # 短线转弱
    if ma10 < ma20: s -= 20  # 中线转弱
    if ma5 < ma20: s -= 15   # 短中皆弱
    
    # 均线方向 (用斜率判断)
    if n >= 5:
        ma5_slope = (ma5 - np.mean(closes[-10:-5])) / (np.mean(closes[-10:-5]) + 1e-8)
        if ma5_slope < -0.01: s -= 10  # MA5快速下行
    if n >= 10:
        ma10_slope = (ma10 - np.mean(closes[-20:-10])) / (np.mean(closes[-20:-10]) + 1e-8)
        if ma10_slope < -0.005: s -= 10  # MA10缓慢下行
    
    return max(0, s)


def _calc_macd_score(closes, n) -> int:
    """MACD状态评分 (0-100)"""
    if n < 26:
        return 50
    
    s = 100
    close_arr = closes
    
    # 计算MACD
    ema12 = _ema(close_arr, 12)
    ema26 = _ema(close_arr, 26)
    dif = ema12 - ema26
    dea = _ema(dif, 9)
    macd_hist = 2 * (dif - dea)
    
    cur_hist = macd_hist[-1]
    prev_hist = macd_hist[-2] if len(macd_hist) >= 2 else 0
    
    # MACD柱方向
    if cur_hist < 0 and cur_hist < prev_hist:
        s -= 25  # 绿柱放大 — 恶化
    elif cur_hist < 0 and cur_hist > prev_hist:
        s -= 15  # 绿柱缩小 — 可能见底
    elif cur_hist > 0 and cur_hist < prev_hist:
        s -= 10  # 红柱缩小 — 动能减弱
    # 红柱放大不扣分
    
    # DIF与DEA关系
    if dif[-1] < dea[-1]: s -= 15  # 死叉
    if dif[-1] < 0: s -= 10  # DIF在零轴下
    
    # 背离检测 (最近5根)
    if len(close_arr) >= 10 and len(macd_hist) >= 10:
        recent_close_high = max(close_arr[-5:])
        recent_macd_high = max(macd_hist[-5:])
        prev_close_high = max(close_arr[-10:-5])
        prev_macd_high = max(macd_hist[-10:-5])
        if recent_close_high > prev_close_high and recent_macd_high < prev_macd_high:
            s -= 20  # 顶背离
    
    return max(0, s)


def _calc_volume_score(closes, volumes, n) -> int:
    """量价关系评分 (0-100)"""
    if n < 5:
        return 50
    
    s = 100
    cur_price = closes[-1]
    prev_price = closes[-2] if n >= 2 else cur_price
    cur_vol = volumes[-1]
    avg_vol_20 = np.mean(volumes[-20:]) if n >= 20 else np.mean(volumes)
    avg_vol_5 = np.mean(volumes[-5:]) if n >= 5 else avg_vol_20
    
    if avg_vol_20 <= 0:
        return 50
    
    vol_ratio = cur_vol / avg_vol_20
    
    # 放量下跌 = 最差
    if cur_price < prev_price and vol_ratio > 1.5:
        s -= 25
    # 放量滞涨
    elif abs(cur_price - prev_price) / prev_price < 0.005 and vol_ratio > 1.5:
        s -= 15
    # 缩量上涨(高位) = 动能不足
    elif cur_price > prev_price and vol_ratio < 0.6 and avg_vol_20 > 1000:
        s -= 10
    # 缩量下跌(低位) = 抛压衰竭，不扣分
    
    # 成交量趋势 (连续缩量)
    if n >= 5:
        vol_trend = np.mean(volumes[-5:]) / (np.mean(volumes[-10:-5]) + 1e-8)
        if cur_price < prev_price and vol_trend < 0.7:
            s += 5  # 缩量下跌是好事（抛压衰竭）
        elif cur_price > prev_price and vol_trend < 0.6:
            s -= 10  # 缩量上涨需警惕
    
    return max(0, min(100, s))


def _calc_kline_score(opens, closes, highs, lows, n) -> int:
    """K线形态评分 (0-100)"""
    if n < 3:
        return 50
    
    s = 100
    
    # 最近一根K线
    last = {"o": opens[-1], "c": closes[-1], "h": highs[-1], "l": lows[-1]}
    prev = {"o": opens[-2], "c": closes[-2], "h": highs[-2], "l": lows[-2]}
    
    body = abs(last["c"] - last["o"])
    upper = last["h"] - max(last["c"], last["o"])
    lower = min(last["c"], last["o"]) - last["l"]
    total_range = last["h"] - last["l"]
    
    if total_range <= 0:
        return s
    
    # 长上影 (抛压)
    if upper / total_range > 0.6 and body > 0:
        s -= 20
        if last["c"] < last["o"]:  # 阴线 + 长上影 = 更差
            s -= 10
    
    # 长下影 (支撑)
    if lower / total_range > 0.6 and body > 0:
        if last["c"] > last["o"]:  # 阳线 + 长下影 = 探底回升
            s += 5
        # 阴线长下影 = 空方仍占优，不扣分
    
    # 阴包阳 (看跌吞没)
    if n >= 2:
        prev_body = abs(prev["c"] - prev["o"])
        if prev["c"] > prev["o"] and last["c"] < last["o"]:  # 前阳后阴
            if last["c"] < prev["o"] and last["o"] > prev["c"]:  # 阴线实体包住前阳线
                s -= 15
    
    # 十字星 (变盘信号，高位差低位好)
    if body / total_range < 0.1 and total_range > 0:
        # 在趋势高位出现十字星 = 风险
        if n >= 5:
            recent_trend = (closes[-1] - closes[-5]) / closes[-5]
            if recent_trend > 0.05:  # 近期上涨后
                s -= 10
    
    return max(0, min(100, s))


def _calc_trend_strength(closes, highs, lows, n) -> int:
    """趋势强度评分 (0-100)"""
    if n < 10:
        return 50
    
    s = 100
    
    # 线性回归斜率 (最近20根)
    n_slope = min(20, n)
    x = np.arange(n_slope)
    y = closes[-n_slope:]
    if np.std(x) > 0 and np.std(y) > 0:
        slope, _ = np.polyfit(x, y, 1)
        # 归一化斜率
        norm_slope = slope / (np.mean(y) + 1e-8)
        
        if norm_slope > 0.005:
            s += 10  # 上升趋势加分
        elif norm_slope < -0.005:
            s -= 25  # 下降趋势大扣分
        elif norm_slope < -0.002:
            s -= 10
    
    # 波动率检查 (过高的波动 = 不稳定)
    if n >= 10:
        returns = np.diff(closes[-10:]) / closes[-10:-1]
        vol = np.std(returns)
        if vol > 0.03:  # 日波动>3%
            s -= 10
    
    # 新高新低
    if n >= 20:
        cur = closes[-1]
        period_high = np.max(highs[-20:])
        period_low = np.min(lows[-20:])
        if cur >= period_high * 0.98:
            s += 5  # 接近新高
        elif cur <= period_low * 1.02:
            s -= 10  # 接近新低
    
    return max(0, min(100, s))


def _ema(data, period):
    """指数移动平均"""
    if len(data) < period:
        return np.full_like(data, data[-1])
    result = np.full_like(data, np.nan)
    multiplier = 2 / (period + 1)
    result[period - 1] = np.mean(data[:period])
    for i in range(period, len(data)):
        result[i] = (data[i] - result[i-1]) * multiplier + result[i-1]
    return result


def get_health_action(health: int, regime: str = "range") -> dict:
    """
    根据健康度获取建议操作
    
    Returns:
        dict with keys: action, shares_pct, reason, stop_adjust
    """
    if health >= 80:
        return {"action": "hold", "shares_pct": 1.0, 
                "reason": "趋势健康", "stop_adjust": 1.0}
    elif health >= 60:
        return {"action": "warn", "shares_pct": 1.0,
                "reason": "趋势预警: 收紧止损", "stop_adjust": 0.6}
    elif health >= 40:
        return {"action": "reduce_third", "shares_pct": 0.67,
                "reason": "趋势转弱: 减仓1/3", "stop_adjust": 0.5}
    elif health >= 20:
        return {"action": "reduce_half", "shares_pct": 0.5,
                "reason": "趋势恶化: 减半仓", "stop_adjust": 0.4}
    else:
        return {"action": "close", "shares_pct": 0.0,
                "reason": "趋势破坏: 清仓", "stop_adjust": 0.0}
