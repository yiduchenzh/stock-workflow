"""移动止盈 v2.0 — ATR增强版 + 固定阶梯
+5%保本 +10%锁利 +20%奔跑 · 斯波朗迪 + ATR自适应"""
import logging
logger = logging.getLogger("aurora.trailing")

def calc_trailing_stop(entry_price: float, current_price: float, current_stop: float,
                       klines=None, market_regime="range", highest_price: float = None,
                       profile_name: str = None) -> float:
    """计算移动止盈位 — 支持ATR增强

    v14.46: 新增 highest_price 参数 — ATR回撤必须用入场以来最高价(不是当前价)。
    原实现 `highest = max(current_price, ...)` 导致ATR从当前价回撤, 浮盈后止损位
    计算错误(回撤基准随价格跳动)。调用方(watch_positions)跟踪 _trailing_highs 传入。

    v14.47: 新增 profile_name 参数 — 止盈阈值按画像 holding_period 差异化
    (2026-08-14 账户画像审计 P1b): 固定阶梯 5/10/20% 对短线合理, 但价值投资者
    (30天+)/趋势跟踪者(10-30天) 1天就跑 — 长持仓画像用更高触发阈值让利润奔跑。

    Returns: 新止损价
    """
    profit_pct = (current_price - entry_price) / entry_price * 100

    # v14.47: 长持仓画像阈值上调 (价值/趋势 = 1.5x, 上班族 = 1.2x, 短线/新手 = 1.0x)
    _mult = 1.0
    if profile_name == "价值投资者":
        _mult = 1.5
    elif profile_name == "趋势跟踪者":
        _mult = 1.5
    elif profile_name == "上班族中短线":
        _mult = 1.2

    # ATR增强（如果有K线数据）
    if klines is not None:
        try:
            from risk.atr_stop import calc_atr, atr_trailing_stop
            atr = calc_atr(klines)
            if atr and atr > 0:
                highest = highest_price or max(current_price, entry_price * (1 + profit_pct / 100))
                trail = atr_trailing_stop(entry_price, highest, current_price, atr)
                if trail:
                    return max(current_stop, trail)
        except:
            pass

    # 固定阶梯（兜底）— 按画像倍率上调触发阈值
    new_stop = current_stop
    if profit_pct >= 20 * _mult:
        new_stop = entry_price * 1.10  # 锁定+10%
    elif profit_pct >= 10 * _mult:
        new_stop = entry_price * 1.05  # 锁定+5%
    elif profit_pct >= 5 * _mult:
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
