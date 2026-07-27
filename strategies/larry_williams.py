"""
拉里·威廉姆斯《短线交易秘诀》策略模块
====================================
核心思想: 短线交易不是预测趋势, 而是捕捉价格的"爆发点"

关键技术:
1. Williams %R - 超买超卖反转信号
2. Setup/Signal/Action - 三级确认框架
3. 开盘区间突破 (ORB) - 日内最强策略
4. 时间周期规律 - 首尾30分钟最佳交易时段
"""
import numpy as np
import logging
logger = logging.getLogger("aurora.williams")

# ═══════════════════════════════════════════
# 1. Williams %R 指标
# ═══════════════════════════════════════════
def williams_r(high, low, close, period=14):
    """Williams %R = (最高价 - 收盘价) / (最高价 - 最低价) × (-100)
    
    返回值: -100 ~ 0
    <-80: 超卖(买入信号)  >-20: 超买(卖出信号)
    """
    if len(close) < period + 1:
        return np.full(len(close), -50)
    
    result = np.zeros(len(close))
    for i in range(period, len(close)):
        hh = np.max(high[i-period:i+1])
        ll = np.min(low[i-period:i+1])
        if hh - ll > 0:
            result[i] = (hh - close[i]) / (hh - ll) * -100
        else:
            result[i] = result[i-1] if i > 0 else -50
    return result

def williams_r_signal(kline_df):
    """Williams %R 信号检测
    
    买入: %R < -80 且 上升(从极低回升)
    卖出: %R > -20 且 下降(从极高回落)
    """
    if kline_df is None or len(kline_df) < 20:
        return {"signal": False, "score": 0}
    
    high = kline_df["high"].values.astype(float)
    low = kline_df["low"].values.astype(float)
    close = kline_df["close"].values.astype(float)
    
    wr = williams_r(high, low, close, 14)
    
    if len(wr) < 3:
        return {"signal": False, "score": 0}
    
    w1, w2, w3 = wr[-3], wr[-2], wr[-1]
    
    # MA20趋势过滤: 买入信号需价格在MA20上方
    close_vals = kline_df["close"].values.astype(float) if "close" in kline_df.columns else None
    ma20 = float(np.mean(close_vals[-20:])) if close_vals is not None and len(close_vals) >= 20 else 0
    above_ma20 = close_vals[-1] > ma20 if close_vals is not None and ma20 > 0 else True
    
    # 超卖区反转买入: %R < -80 且连续上升
    if w3 < -80 and w3 > w2 > w1 and above_ma20:
        score = min(85, int(abs(w3) * 0.8 + 20))
        return {
            "signal": True, "type": "wr_oversold_buy",
            "direction": "bullish", "score": score,
            "wr": round(w3, 1),
            "detail": f"Williams%R超卖买入({w3:.0f}<-80回升)"
        }
    # 超买区反转卖出: %R > -20 且连续下降
    if w3 > -20 and w3 < w2 < w1:
        score = min(80, int((100 - abs(w3)) * 0.7 + 20))
        return {
            "signal": True, "type": "wr_overbought_sell",
            "direction": "bearish", "score": score,
            "wr": round(w3, 1),
            "detail": f"Williams%R超买卖出({w3:.0f}>-20回落)"
        }
    # %R从极低价区(-90以下)回升的强势买入
    if min(wr[-10:]) < -90 and w3 > -70 and above_ma20:
        return {
            "signal": True, "type": "wr_extreme_buy",
            "direction": "bullish", "score": 75,
            "wr": round(w3, 1),
            "detail": f"Williams%R极端超卖反弹({w3:.0f}从-90以下回升)"
        }
    
    return {"signal": False, "score": 0, "wr": round(wr[-1], 1)}


# ═══════════════════════════════════════════
# 2. 开盘区间突破 (Opening Range Breakout)
# ═══════════════════════════════════════════
def opening_range_breakout(kline_df, code=None):
    """开盘区间突破策略 (拉里·威廉姆斯核心日内策略)
    
    原理: 开盘前30分钟形成"开盘区间", 突破该区间=当日方向
    买入: 价格突破开盘区间上轨 + 成交量确认
    卖出: 价格跌破开盘区间下轨 + 成交量确认
    """
    # 需要5分钟K线数据
    if code is None:
        return {"signal": False, "score": 0, "detail": "需要个股代码获取分钟K线"}
    
    try:
        from data.sources import get_kline_period
        m5_k = get_kline_period(code, "5min", 48)
        if m5_k is None or m5_k.empty or len(m5_k) < 12:
            # 降级到日K线
            return _daily_breakout(kline_df)
        
        close = m5_k["close"].values.astype(float)
        high = m5_k["high"].values.astype(float)
        low = m5_k["low"].values.astype(float)
        vol = m5_k["volume"].values.astype(float)
        
        # 开盘前6根K线(30分钟) = 开盘区间
        or_high = np.max(high[:6])
        or_low = np.min(low[:6])
        or_range = or_high - or_low
        
        if or_range < 0.01:
            return {"signal": False, "score": 0, "detail": "开盘区间过窄"}
        
        current = close[-1]
        # 当前成交量相对前6根均值
        vol_ratio = np.mean(vol[-3:]) / (np.mean(vol[:6]) or 1)
        
        # 突破上轨买入
        if current > or_high * 1.001 and vol_ratio > 1.2:
            score = min(85, int(vol_ratio * 30 + 40))
            return {
                "signal": True, "type": "orb_breakout_up",
                "direction": "bullish", "score": score,
                "or_high": round(or_high, 2), "or_low": round(or_low, 2),
                "detail": f"开盘区间上轨突破({current:.2f}>{or_high:.2f})"
            }
        # 跌破下轨卖出
        if current < or_low * 0.999 and vol_ratio > 1.2:
            return {
                "signal": True, "type": "orb_breakout_down",
                "direction": "bearish", "score": 75,
                "or_high": round(or_high, 2), "or_low": round(or_low, 2),
                "detail": f"开盘区间下轨跌破({current:.2f}<{or_low:.2f})"
            }
        
        # 价格在区间内, 计算位置百分比
        pos_pct = (current - or_low) / or_range * 100 if or_range > 0 else 50
        return {
            "signal": False, "score": 0,
            "pos_pct": round(pos_pct, 1),
            "detail": f"开盘区间内({pos_pct:.0f}%位置)"
        }
    except Exception as e:
        logger.debug(f"[ORB] {code}: {e}")
        return _daily_breakout(kline_df)


def _daily_breakout(kline_df):
    """降级: 日K线的价格突破 (当分钟K线不可用时)"""
    if kline_df is None or len(kline_df) < 20:
        return {"signal": False, "score": 0}
    
    close = kline_df["close"].values.astype(float)
    high = kline_df["high"].values.astype(float)
    low = kline_df["low"].values.astype(float)
    
    # 近10日最高最低 = 近似"开盘区间"
    recent_high = np.max(high[-10:])
    recent_low = np.min(low[-10:])
    current = close[-1]
    
    if current > recent_high and close[-1] > np.mean(close[-5:-1]):
        return {
            "signal": True, "type": "daily_breakout_up",
            "direction": "bullish", "score": 70,
            "detail": f"日线突破近10日高点({current:.2f}>{recent_high:.2f})"
        }
    if current < recent_low and close[-1] < np.mean(close[-5:-1]):
        return {
            "signal": True, "type": "daily_breakout_down",
            "direction": "bearish", "score": 65,
            "detail": f"日线跌破近10日低点({current:.2f}<{recent_low:.2f})"
        }
    return {"signal": False, "score": 0}


# ═══════════════════════════════════════════
# 3. 拉里·威廉姆斯综合评分
# ═══════════════════════════════════════════
def williams_composite_score(kline_df, code=None):
    """拉里·威廉姆斯综合策略评分
    
    融合: Williams%R + 开盘区间突破 + 时间周期
    返回: 0-100 综合评分, 以及具体信号
    """
    if kline_df is None or len(kline_df) < 20:
        return {"score": 0, "signals": []}
    
    signals = []
    
    # 1. Williams %R 信号
    wr = williams_r_signal(kline_df)
    if wr.get("signal"):
        signals.append(("williams_r", wr["score"], wr.get("detail", "")))
    
    # 2. 开盘区间突破
    orb = opening_range_breakout(kline_df, code)
    if orb.get("signal"):
        signals.append(("orb", orb["score"], orb.get("detail", "")))
    
    # 3. 价格位置分析 (威廉姆斯: 寻找紧凑整理后的爆发)
    close = kline_df["close"].values.astype(float)
    high = kline_df["high"].values.astype(float)
    low = kline_df["low"].values.astype(float)
    vol = kline_df["volume"].values.astype(float) if "volume" in kline_df.columns else np.ones(len(close))
    
    # 计算近期波动收缩
    if len(close) >= 10:
        recent_range = (np.max(high[-5:]) - np.min(low[-5:])) / np.mean(close[-5:]) * 100
        prev_range = (np.max(high[-10:-5]) - np.min(low[-10:-5])) / np.mean(close[-10:-5]) * 100
        if recent_range < prev_range * 0.7 and recent_range < 5:
            # 波动收缩=突破前兆
            vol_increase = vol[-1] / (np.mean(vol[-5:]) or 1)
            if vol_increase > 1.3:
                signals.append(("williams_compression", 75, f"波动收缩+放量({recent_range:.1f}%<{prev_range:.1f}%)"))
            else:
                signals.append(("williams_compression", 55, f"波动收缩待放量({recent_range:.1f}%)"))
    
    # 综合评分: 取最高信号
    if signals:
        max_signal = max(signals, key=lambda x: x[1])
        return {
            "score": max_signal[1],
            "best_strategy": max_signal[0],
            "signals": signals,
            "detail": " | ".join([f"{s[0]}({s[1]})" for s in signals[:3]]),
        }
    
    return {"score": 0, "signals": []}


# ═══════════════════════════════════════════
# 4. 交易日时段分析
# ═══════════════════════════════════════════
def get_trading_session():
    """返回当前交易时段 (拉里·威廉姆斯时间规律)
    
    威廉姆斯发现: 开盘30分钟和收盘30分钟是最大波动时段
    """
    from datetime import datetime
    now = datetime.now()
    t = now.hour * 60 + now.minute
    
    if t < 570: return "pre_open", 0   # 盘前
    if t < 600: return "open_surge", 1.5  # 开盘冲击(9:30-10:00)
    if t < 660: return "morning", 1.0    # 早盘(10:00-11:00)
    if t < 690: return "pre_noon", 0.8   # 午前(11:00-11:30)
    if t < 780: return "lunch", 0.3      # 午休(11:30-13:00)
    if t < 840: return "afternoon", 1.0  # 下午(13:00-14:00)
    if t < 870: return "power_hour", 1.3 # 动力小时(14:00-14:30)
    if t < 900: return "close_surge", 1.5# 收盘冲击(14:30-15:00)
    return "closed", 0
