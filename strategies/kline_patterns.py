
"""K线组合形态 — 股市操练大全八大反转组合+涨停板分析"""
import numpy as np
import logging
logger = logging.getLogger("aurora.patterns")

def detect_eight_patterns(kline_df):
    """八大反转K线组合"""
    if kline_df is None or len(kline_df) < 4: return []
    o, c, h, l = kline_df["open"].values, kline_df["close"].values, kline_df["high"].values, kline_df["low"].values
    vol = kline_df["volume"].values if "volume" in kline_df.columns else np.ones(len(o))
    patterns = []
    idx = -1
    
    # 早晨之星: 大阴+小K线+大阳, 第三根深入第一根1/2
    if len(o) >= 3:
        bar1_body = abs(c[-3] - o[-3]); bar3_body = abs(c[-1] - o[-1])
        bar2_body = abs(c[-2] - o[-2])
        if c[-3] < o[-3] and c[-1] > o[-1] and bar1_body > 0 and bar3_body > 0:
            if bar2_body < bar1_body * 0.3 and c[-1] > o[-3]:
                patterns.append({"type": "morning_star", "dir": "bullish", "score": 80,
                                "detail": "早晨之星(底部反转)"})
    
    # 曙光初现: 大阴+低开大阳(收>前阴1/2)
    if c[-2] < o[-2] and o[-1] < c[-2] and c[-1] > (o[-2] + c[-2]) / 2 and c[-1] > o[-1]:
        patterns.append({"type": "dawn_break", "dir": "bullish", "score": 70,
                        "detail": "曙光初现(底部反转)"})
    
    # 旭日东升: 大阴+高开大阳(收>前阴开盘)
    if c[-2] < o[-2] and o[-1] > o[-2] and c[-1] > o[-1] and c[-1] > o[-2]:
        patterns.append({"type": "rising_sun", "dir": "bullish", "score": 85,
                        "detail": "旭日东升(强底部反转)"})
    
    # 底部穿头破脚: 阴线+更大阳线完全包容
    if c[-2] < o[-2] and c[-1] > o[-1] and l[-1] < l[-2] and h[-1] > h[-2]:
        vol_ratio = vol[-1] / np.mean(vol[-10:]) if np.mean(vol[-10:]) > 0 else 1
        if vol_ratio > 1.2:
            patterns.append({"type": "bullish_engulf", "dir": "bullish", "score": 75,
                           "detail": "底部穿头破脚(放量确认)"})
    
    # 黄昏之星: 大阳+小K线+大阴, 第三根深入第一根1/2
    if len(o) >= 3 and c[-3] > o[-3] and c[-1] < o[-1]:
        if abs(c[-2] - o[-2]) < abs(c[-3] - o[-3]) * 0.3 and c[-1] < o[-3]:
            patterns.append({"type": "evening_star", "dir": "bearish", "score": 80,
                           "detail": "黄昏之星(顶部反转)"})
    
    # 乌云盖顶: 大阳+高开大阴(收<前阳1/2)
    if c[-2] > o[-2] and o[-1] > c[-2] and c[-1] < (o[-2] + c[-2]) / 2 and c[-1] < o[-1]:
        patterns.append({"type": "dark_cloud", "dir": "bearish", "score": 70,
                        "detail": "乌云盖顶(顶部反转)"})
    
    # 顶部穿头破脚
    if c[-2] > o[-2] and c[-1] < o[-1] and h[-1] > h[-2] and l[-1] < l[-2]:
        vol_ratio = vol[-1] / np.mean(vol[-10:]) if np.mean(vol[-10:]) > 0 else 1
        if vol_ratio > 1.2:
            patterns.append({"type": "bearish_engulf", "dir": "bearish", "score": 75,
                           "detail": "顶部穿头破脚(放量确认)"})
    return patterns

def analyze_limit_up(kline_df):
    """涨停板强弱分析: 缩量封板/放量封板/巨量烂板"""
    if kline_df is None or len(kline_df) < 3: return None
    close, vol = kline_df["close"].values, kline_df["volume"].values
    chg = (close[-1] - close[-2]) / close[-2] * 100
    if chg < 9.5: return None  # 非涨停
    vol_ratio = vol[-1] / np.mean(vol[-10:-1]) if len(vol) > 10 and np.mean(vol[-10:-1]) > 0 else 1
    high_low_range = (kline_df["high"].values[-1] - kline_df["low"].values[-1]) / close[-1] * 100
    
    if vol_ratio < 0.5 and high_low_range < 1:
        return {"type": "limit_up_tight", "quality": "A", "score": 90,
                "detail": "缩量一字封板(最强)", "next_day": "大概率继续涨停"}
    elif vol_ratio < 1.0:
        return {"type": "limit_up_good", "quality": "B", "score": 75,
                "detail": "缩量封板", "next_day": "次日大概率高开"}
    elif vol_ratio < 2.0:
        return {"type": "limit_up_normal", "quality": "C", "score": 60,
                "detail": "放量封板", "next_day": "次日看开盘高开可持低开减仓"}
    else:
        return {"type": "limit_up_weak", "quality": "D", "score": 30,
                "detail": "巨量烂板(弱)", "next_day": "次日大概率低开,建议离场"}
