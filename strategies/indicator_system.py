
"""股市操练大全指标系统 — MACD背离+KDJ超买超卖+BOLL收口开口"""
import numpy as np
import logging
logger = logging.getLogger("aurora.indicators")

# ═══ MACD 背离检测 (股市操练大全: 最核心用法) ═══
def detect_macd_divergence(kline_df):
    """顶背离: 股价新高+MACD DIF不创新高 → 强卖出
       底背离: 股价新低+MACD DIF不创新低 → 强买入"""
    if kline_df is None or len(kline_df) < 60: return {"type": "none", "signal": False, "score": 0}
    close = kline_df["close"].values
    # 计算MACD
    ema12 = _ema(close, 12); ema26 = _ema(close, 26)
    dif = np.array([ema12[i] - ema26[i] for i in range(len(ema12))])
    
    # 找最近两个极值点 (60日内)
    lookback = min(60, len(close))
    # 股价高点
    p1_high = max(close[-lookback:-lookback//2]); p2_high = max(close[-lookback//2:])
    dif1 = dif[-lookback:-lookback//2][np.argmax(close[-lookback:-lookback//2])]
    dif2 = dif[-lookback//2:][np.argmax(close[-lookback//2:])]
    # 股价低点
    p1_low = min(close[-lookback:-lookback//2]); p2_low = min(close[-lookback//2:])
    dif1_low = dif[-lookback:-lookback//2][np.argmin(close[-lookback:-lookback//2])]
    dif2_low = dif[-lookback//2:][np.argmin(close[-lookback//2:])]
    
    # 顶背离: 价创新高但DIF不创新高
    if p2_high > p1_high and dif2 < dif1:
        return {"type": "top_divergence", "signal": True, "direction": "bearish",
                "score": 80, "detail": f"顶背离(价{p2_high:.1f}>{p1_high:.1f}, DIF{dif2:.2f}<{dif1:.2f})"}
    # 底背离: 价创新低但DIF不创新低
    if p2_low < p1_low and dif2_low > dif1_low:
        return {"type": "bottom_divergence", "signal": True, "direction": "bullish",
                "score": 85, "detail": f"底背离(价{p2_low:.1f}<{p1_low:.1f}, DIF{dif2_low:.2f}>{dif1_low:.2f})"}
    return {"type": "none", "signal": False, "score": 0}

# ═══ KDJ 超买超卖系统 ═══
def detect_kdj_signal(kline_df):
    """KDJ: K<20金叉=买入, K>80死叉=卖出"""
    if kline_df is None or len(kline_df) < 20: return {"signal": False, "score": 0}
    high, low, close = kline_df["high"].values, kline_df["low"].values, kline_df["close"].values
    k, d, j = _calc_kdj(high, low, close)
    # 超卖区金叉: K在20附近上穿D
    if k[-2] <= 20 and d[-2] <= 25 and k[-1] > d[-1]:
        return {"signal": True, "type": "oversold_golden_cross", "direction": "bullish",
                "score": 70, "K": round(k[-1], 1), "D": round(d[-1], 1),
                "detail": f"KDJ超卖金叉(K={k[-1]:.1f},D={d[-1]:.1f})"}
    # 超买区死叉: K在80附近下穿D
    if k[-2] >= 75 and d[-2] >= 75 and k[-1] < d[-1]:
        return {"signal": True, "type": "overbought_death_cross", "direction": "bearish",
                "score": 65, "K": round(k[-1], 1), "D": round(d[-1], 1),
                "detail": f"KDJ超买死叉(K={k[-1]:.1f},D={d[-1]:.1f})"}
    # 低位钝化后的金叉更强
    j_low_streak = sum(1 for x in j[-10:] if x < 20)
    if j_low_streak >= 3 and k[-1] > d[-1]:
        return {"signal": True, "type": "bottom_divergence_golden", "direction": "bullish",
                "score": 80, "detail": f"KDJ低位钝化后金叉(连续{j_low_streak}天J<20)"}
    return {"signal": False, "score": 0}

def _calc_kdj(high, low, close, n=9):
    k, d, j = [50], [50], [50]
    for i in range(n-1, len(close)):
        hh = max(high[i-n+1:i+1]); ll = min(low[i-n+1:i+1])
        rsv = (close[i] - ll) / (hh - ll) * 100 if hh > ll else 50
        k.append(2/3 * k[-1] + 1/3 * rsv)
        d.append(2/3 * d[-1] + 1/3 * k[-1])
        j.append(3 * k[-1] - 2 * d[-1])
    return np.array(k), np.array(d), np.array(j)

# ═══ BOLL 布林带 ═══
def detect_boll_signal(kline_df):
    """BOLL: 收口=变盘, 开口=趋势启动, 突破上轨+开口=加速涨"""
    if kline_df is None or len(kline_df) < 25: return {"signal": False, "score": 0}
    close = kline_df["close"].values
    ma20 = np.mean(close[-20:])
    std20 = np.std(close[-20:], ddof=1)
    upper = ma20 + 2 * std20; lower = ma20 - 2 * std20
    # 前20日带宽
    prev_ma20 = np.mean(close[-40:-20])
    prev_std20 = np.std(close[-40:-20], ddof=1)
    prev_width = 4 * prev_std20 / prev_ma20 * 100 if prev_ma20 > 0 else 0
    cur_width = 4 * std20 / ma20 * 100 if ma20 > 0 else 0
    
    # 开口放大
    if cur_width > prev_width * 1.3 and close[-1] > upper:
        return {"signal": True, "type": "boll_breakout_up", "direction": "bullish",
                "score": 70, "detail": f"BOLL开口突破上轨(宽{cur_width:.1f}%)"}
    # 收口变盘
    if cur_width < prev_width * 0.7:
        direction = "bullish" if close[-1] > ma20 else "bearish"
        return {"signal": True, "type": "boll_squeeze", "direction": direction,
                "score": 55, "detail": f"BOLL收口(宽{cur_width:.1f}%→变盘)"}
    # 价格在中轨之上
    if close[-1] > ma20:
        return {"signal": False, "score": 30, "detail": "中轨上方"}
    return {"signal": False, "score": 0}

def _ema(data, period):
    alpha = 2 / (period + 1)
    result = [data[0]]
    for i in range(1, len(data)):
        result.append(alpha * data[i] + (1 - alpha) * result[-1])
    return np.array(result)

def indicator_composite_score(kline_df):
    """综合指标评分: MACD背离+KDJ+BOLL"""
    if kline_df is None: return 50
    macd = detect_macd_divergence(kline_df)
    kdj = detect_kdj_signal(kline_df)
    boll = detect_boll_signal(kline_df)
    score = 50
    if macd["signal"]:
        score += 20 if macd["direction"] == "bullish" else -15
    if kdj["signal"]:
        score += 12 if kdj["direction"] == "bullish" else -10
    if boll["signal"]:
        score += 8 if boll["direction"] == "bullish" else -5
    return min(max(score, 0), 100)
