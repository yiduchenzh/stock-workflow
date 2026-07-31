"""ATR自适应止损 v1.0 — 基于波动率的动态止损"""
import logging
from datetime import datetime

logger = logging.getLogger("aurora.atr")

# ATR参数
ATR_PERIOD = 14
MULTIPLIER_MAP = {
    "bull_strong": 3.0, "bull_weak": 2.5,
    "range": 2.0,
    "bear_weak": 1.8, "bear_strong": 1.5,
}
TRAIL_MULTIPLIER = 2.5  # 移动止盈ATR倍数

def calc_atr(klines, period=ATR_PERIOD):
    """计算ATR(平均真实波幅) — 从K线数据"""
    if klines is None:
        return None
    
    # 兼容DataFrame和list-of-dicts两种格式
    is_df = hasattr(klines, 'columns') or hasattr(klines, 'iterrows')
    
    klen = len(klines)
    if klen < period + 1:
        return None
    
    def _get_val(kline, key, df_key=None):
        if is_df:
            try:
                if hasattr(kline, 'iloc'):
                    return float(kline[key])
                return float(kline[key])
            except (KeyError, TypeError, ValueError, IndexError):
                try:
                    # Try as dict
                    return float(kline.get(key, 0))
                except:
                    return 0.0
        else:
            return kline.get(key, 0)
    
    tr_values = []
    for i in range(len(klines) - 1, len(klines) - period - 2, -1):
        if i < 0 or i >= len(klines):
            continue
        curr = klines.iloc[i] if is_df else klines[i]
        if i == 0:
            tr = _get_val(curr, "high", "high") - _get_val(curr, "low", "low")
        else:
            prev = klines.iloc[i - 1] if is_df else klines[i - 1]
            hl = _get_val(curr, "high", "high") - _get_val(curr, "low", "low")
            hc = abs(_get_val(curr, "high", "high") - _get_val(prev, "close", "close"))
            lc = abs(_get_val(curr, "low", "low") - _get_val(prev, "close", "close"))
            tr = max(hl, hc, lc)
        if tr > 0:
            tr_values.append(tr)
    
    if len(tr_values) < period:
        return None
    
    # EMA of TR
    alpha = 2.0 / (period + 1)
    atr = sum(tr_values[:period]) / period
    for v in tr_values[period:]:
        atr = alpha * v + (1 - alpha) * atr
    return round(atr, 2)


def atr_stop_loss(entry_price, current_price, atr_value, market_regime="range"):
    """ATR自适应止损价 — 比固定%止损更精准
    
    Args:
        entry_price: 入场价
        current_price: 当前价(用于判断浮盈/亏)
        atr_value: ATR值
        market_regime: 市场状态
    Returns:
        float: 建议止损价
    """
    if not atr_value or atr_value <= 0:
        return None
    
    multiplier = MULTIPLIER_MAP.get(market_regime, 2.0)
    # 浮盈时放宽止损, 浮亏时收紧
    pnl_pct = (current_price - entry_price) / entry_price * 100
    if pnl_pct > 5:
        multiplier *= 1.2  # 多头让利润奔跑
    elif pnl_pct < -3:
        multiplier *= 0.8  # 亏损收紧
    
    stop_distance = atr_value * multiplier
    stop_price = round(entry_price - stop_distance, 2)
    return max(stop_price, entry_price * 0.75)  # 硬上限25%


def atr_trailing_stop(entry_price, highest_price, current_price, atr_value):
    """ATR移动止盈 — 从最高点回撤ATR*倍数出场
    
    Args:
        entry_price: 入场价
        highest_price: 入场以来最高价
        current_price: 当前价
        atr_value: ATR值
    Returns:
        float: 建议止盈价, 或None
    """
    if not atr_value or atr_value <= 0:
        return None
    
    profit_pct = (highest_price - entry_price) / entry_price * 100
    
    # 盈利<5%: 保本止损
    if profit_pct < 5:
        return round(entry_price * 0.995, 2)
    
    # 盈利5-15%: 从最高点回撤2倍ATR出场
    if profit_pct < 15:
        trail_stop = highest_price - atr_value * TRAIL_MULTIPLIER
        return round(max(trail_stop, entry_price * 1.0), 2)
    
    # 盈利15-30%: 从最高点回撤3倍ATR
    if profit_pct < 30:
        trail_stop = highest_price - atr_value * 3.0
        return round(max(trail_stop, entry_price * 1.05), 2)
    
    # 盈利>30%: 锁定15%
    return round(max(highest_price - atr_value * 3.5, entry_price * 1.15), 2)


def atr_take_profit(entry_price, current_price, atr_value, market_regime="range"):
    """ATR自适应止盈目标价
    
    Args:
        entry_price: 入场价
        current_price: 当前价
        atr_value: ATR值
        market_regime: 市场状态
    Returns:
        dict: {tp1, tp2, tp3} 三级止盈目标
    """
    if not atr_value or atr_value <= 0:
        return None
    
    regime_mult = {
        "bull_strong": 1.0, "bull_weak": 0.85,
        "range": 0.7, "bear_weak": 0.55, "bear_strong": 0.4,
    }.get(market_regime, 0.7)
    
    # 三级止盈: 保守/中等/激进
    tp1 = round(entry_price + atr_value * 2 * regime_mult, 2)
    tp2 = round(entry_price + atr_value * 3.5 * regime_mult, 2)
    tp3 = round(entry_price + atr_value * 5 * regime_mult, 2)
    
    return {"tp1": tp1, "tp2": tp2, "tp3": tp3}


def get_risk_adjusted_stop(entry_price, current_price, klines, market_regime, current_stop=None):
    """一站式获取调整后的止损价
    
    整合ATR止损 + 固定%止损(兜底)，取较严者
    """
    atr = calc_atr(klines)
    atr_stop = atr_stop_loss(entry_price, current_price, atr, market_regime) if atr else None
    
    # 固定%止损(兜底) — 2026-07-31优化: 8%→5%收紧, 单笔亏损控制在可接受范围
    pct_map = {"bull_strong":0.05,"bull_weak":0.045,"range":0.04,"bear_weak":0.035,"bear_strong":0.03}
    pct = pct_map.get(market_regime, 0.04)
    fixed_stop = round(entry_price * (1 - pct), 2)
    
    # 取较严者
    if atr_stop:
        new_stop = max(atr_stop, fixed_stop)  # 取较高的(较紧)
    else:
        new_stop = fixed_stop
    
    # 已有止损基础上只上移(不降低)
    if current_stop:
        new_stop = max(new_stop, current_stop)
    
    return round(new_stop, 2)


def check_moving_tp(entry_price, highest_price, current_price, klines):
    """检查是否触发移动止盈
    
    Returns:
        str: None/"partial"/"full"
    """
    atr = calc_atr(klines)
    if not atr:
        return None
    
    trail = atr_trailing_stop(entry_price, highest_price, current_price, atr)
    if not trail:
        return None
    
    profit_pct = (highest_price - entry_price) / entry_price * 100
    
    if current_price <= trail:
        if profit_pct >= 20:
            return "partial"  # 减一半
        return "full"  # 全出
    
    return None
