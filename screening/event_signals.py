"""
事件驱动信号评分模块 — 涨停封板/破净分红/回购超跌/龙虎榜

用于 step_cascade 阶段为候选股增加 event_score 字段(0-100)
"""
import numpy as np
import logging

logger = logging.getLogger("aurora.event")


def _limit_up_signal(kline_df) -> float:
    """涨停封板比评分 0-40

    如果最近K线涨停(涨幅>=9.5%):
      用成交量变化近似封板强度:
        - 缩量(vol_ratio<0.7): +40(封板强)
        - 温和(0.7<=vol_ratio<1.0): +30
        - 微放(1.0<=vol_ratio<1.5): +20
        - 放量(>=1.5): +10(封板存疑)
      无vol字段: +20(基础)
    否则返回0
    """
    if kline_df is None:
        return 0.0
    try:
        close_vals = kline_df["close"].values
        if len(close_vals) < 2:
            return 0.0
        latest = close_vals[-1]
        prev = close_vals[-2]
        change_pct = (latest - prev) / prev * 100
        if change_pct < 9.5:
            return 0.0

        has_vol = "vol" in kline_df.columns
        if not has_vol:
            return 20.0

        vol_vals = kline_df["vol"].values
        if len(vol_vals) < 2:
            return 20.0

        recent_vol = vol_vals[-1]
        # 用前一段平均量 (至少1根, 最多取前5根)
        n_prev = min(len(vol_vals) - 1, 5)
        mean_vol = np.mean(vol_vals[-1 - n_prev:-1]) if n_prev >= 1 else vol_vals[0]
        if mean_vol <= 0:
            return 20.0

        vol_ratio = recent_vol / mean_vol
        if vol_ratio < 0.7:
            return 40.0
        elif vol_ratio < 1.0:
            return 30.0
        elif vol_ratio < 1.5:
            return 20.0
        else:
            return 10.0
    except Exception as e:
        logger.debug(f"_limit_up_signal error: {e}")
        return 0.0


def _break_book_signal(pb: float, dividend_yield: float) -> float:
    """破净+高分红评分 0-100

    - PB<1: +30基础分
    - PB<0.8: +20额外
    - PB<0.6: +20额外
    - 股息率>3%: +15
    - 股息率>5%: +10额外(叠加)
    """
    score = 0.0
    if pb < 1.0:
        score += 30
        if pb < 0.8:
            score += 20
        if pb < 0.6:
            score += 20
    if dividend_yield > 5.0:
        score += 25
    elif dividend_yield > 3.0:
        score += 15
    return float(min(score, 100))


def _buyback_signal(kline_df, pb: float) -> float:
    """回购潜力评分 0-100

    - 近20日跌幅>15%: +20分
    - PB<1.5: +15分
    - 近20日跌幅>10%+PB<1: +20分(双重信号)
    """
    if kline_df is None:
        return 0.0
    score = 0.0
    try:
        close_vals = kline_df["close"].values
        n_bars = len(close_vals)
        if n_bars < 2:
            return 0.0

        # 取近20日(或全部)计算区间涨跌幅
        lookback = min(n_bars - 1, 20)
        start_val = close_vals[-1 - lookback]
        end_val = close_vals[-1]
        recent_return = (end_val - start_val) / start_val * 100

        if recent_return < -15:
            score += 20
        if pb < 1.5:
            score += 15
        if recent_return < -10 and pb < 1.0:
            score += 20
        return float(min(score, 100))
    except Exception as e:
        logger.debug(f"_buyback_signal error: {e}")
        return 0.0


def _longhubang_signal(code: str, kline_df) -> float:
    """龙虎榜信号(简化版) 0-100

    - 最近涨停(>=9.5%): +30
      - 涨停+放量(vol_ratio>1.5): +20额外
    - 近3日涨幅>15%: +20
      - +放量(vol_3d/vol_prev>1.3): +30额外
    """
    if kline_df is None:
        return 0.0
    score = 0.0
    try:
        close_vals = kline_df["close"].values
        if len(close_vals) < 4:
            return 0.0

        has_vol = "vol" in kline_df.columns

        # 最近涨停
        latest_chg = (close_vals[-1] - close_vals[-2]) / close_vals[-2] * 100
        if latest_chg >= 9.5:
            score += 30
            if has_vol:
                vol_vals = kline_df["vol"].values
                if len(vol_vals) >= 3:
                    recent_vol = vol_vals[-1]
                    n_prev = min(len(vol_vals) - 1, 5)
                    mean_vol = np.mean(vol_vals[-1 - n_prev:-1]) if n_prev >= 1 else vol_vals[0]
                    if mean_vol > 0 and recent_vol / mean_vol > 1.5:
                        score += 20

        # 近3日涨幅>15%+放量
        chg_3d = (close_vals[-1] - close_vals[-4]) / close_vals[-4] * 100
        if chg_3d > 15:
            score += 20
            if has_vol:
                vol_vals = kline_df["vol"].values
                if len(vol_vals) >= 4:
                    vol_3d = np.sum(vol_vals[-4:])
                    vol_prev = np.sum(vol_vals[-8:-4]) if len(vol_vals) >= 8 else np.mean(vol_vals[:4]) * 4
                    if vol_prev > 0 and vol_3d / vol_prev > 1.3:
                        score += 30

        return float(min(score, 100))
    except Exception as e:
        logger.debug(f"_longhubang_signal error: {e}")
        return 0.0


def scan_event_signals(candidates: list, kline_cache: dict = None) -> list:
    """
    为候选股扫描事件驱动信号

    信号来源及权重:
      1. 涨停封板比信号(权重0.3): 从kline检测涨停和封板强度
      2. 破净+高分红信号(权重0.3): 从candidate的pb/dividend字段
      3. 回购超跌信号(权重0.2): 超跌+低PB
      4. 龙虎榜信号(权重0.2): 涨停放量+主力活跃

    Parameters
    ----------
    candidates : list[dict]
        候选股列表, 每个dict需包含 code, pb 等字段
    kline_cache : dict or None
        code -> DataFrame (需包含 "close" 列, 可选 "vol" 列)

    Returns
    -------
    list[dict]
        每个候选股增加 event_score 字段(0-100)
    """
    if not candidates:
        return []

    for c in candidates:
        code = c.get("code", "")
        pb = float(c.get("pb", 2.0))
        div = float(c.get("dividend_yield", c.get("div_yield", 0)))
        kline = None
        if kline_cache and code in kline_cache:
            kline = kline_cache[code]

        signals = []
        weights = []

        # 1. 涨停封板 (权重0.3)
        lu = _limit_up_signal(kline)
        if lu > 0:
            signals.append(lu)
            weights.append(0.3)

        # 2. 破净高分红 (权重0.3)
        bb = _break_book_signal(pb, div)
        if bb > 0:
            signals.append(bb)
            weights.append(0.3)

        # 3. 回购超跌 (权重0.2)
        bs = _buyback_signal(kline, pb)
        if bs > 0:
            signals.append(bs)
            weights.append(0.2)

        # 4. 龙虎榜 (权重0.2)
        lh = _longhubang_signal(code, kline)
        if lh > 0:
            signals.append(lh)
            weights.append(0.2)

        if signals:
            total_weight = sum(weights)
            if total_weight > 0:
                c["event_score"] = round(sum(s * w for s, w in zip(signals, weights)), 1)
            else:
                c["event_score"] = 0.0
        else:
            c["event_score"] = 0.0

    return candidates
