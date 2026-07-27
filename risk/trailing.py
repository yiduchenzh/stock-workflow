"""移动止盈 v2.0 — ATR增强版 + 固定阶梯
+5%保本 +10%锁利 +20%奔跑 · 斯波朗迪 + ATR自适应"""
import logging
logger = logging.getLogger("aurora.trailing")

def calc_trailing_stop(entry_price: float, current_price: float, current_stop: float,
                       klines=None, market_regime="range") -> float:
    """计算移动止盈位 — 支持ATR增强
    
    Returns: 新止损价
    """
    profit_pct = (current_price - entry_price) / entry_price * 100
    
    # ATR增强（如果有K线数据）
    if klines is not None:
        try:
            from risk.atr_stop import calc_atr, atr_trailing_stop
            atr = calc_atr(klines)
            if atr and atr > 0:
                highest = max(current_price, entry_price * (1 + profit_pct / 100))
                trail = atr_trailing_stop(entry_price, highest, current_price, atr)
                if trail:
                    return max(current_stop, trail)
        except:
            pass
    
    # 固定阶梯（兜底）
    new_stop = current_stop
    if profit_pct >= 20:
        new_stop = entry_price * 1.10  # 锁定+10%
    elif profit_pct >= 10:
        new_stop = entry_price * 1.05  # 锁定+5%
    elif profit_pct >= 5:
        new_stop = entry_price * 1.00  # 保本
    return max(current_stop, new_stop)

def should_scale_out(entry_price: float, current_price: float, shares: int, 
                     klines=None, market_regime="range") -> tuple:
    """分批止盈: ATR优先级 > 固定%"""
    profit_pct = (current_price - entry_price) / entry_price * 100
    
    # ATR减仓
    if klines is not None:
        try:
            from risk.atr_stop import calc_atr
            atr = calc_atr(klines)
            if atr and atr > 0:
                tp_mult = {"bull_strong":1.0,"bull_weak":0.85,"range":0.7,"bear_weak":0.55,"bear_strong":0.4}
                m = tp_mult.get(market_regime, 0.7)
                tp2 = entry_price + atr * 3.5 * m
                tp3 = entry_price + atr * 5 * m
                if current_price >= tp3:
                    return (True, int(shares * 0.5))  # 达三级目标减半
                if current_price >= tp2:
                    return (True, int(shares * 0.33))  # 达二级目标减1/3
        except:
            pass
    
    # 固定阶梯（兜底）
    if profit_pct >= 30:
        return (True, int(shares * 0.5))
    elif profit_pct >= 20:
        return (True, int(shares * 0.33))
    return (False, 0)
