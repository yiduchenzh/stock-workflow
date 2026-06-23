
"""移动止盈阶梯 — +5%保本 +10%锁利 +20%奔跑 · 斯波朗迪"""
import logging
logger = logging.getLogger("aurora.trailing")

def calc_trailing_stop(entry_price: float, current_price: float, current_stop: float) -> float:
    import logging; logging.getLogger(__name__).warning("[NotYetConnected] calc_trailing_stop called but not wired to pipeline")
    """计算移动止盈位"""
    profit_pct = (current_price - entry_price) / entry_price * 100
    new_stop = current_stop
    if profit_pct >= 20:
        new_stop = entry_price * 1.10  # 锁定+10%
    elif profit_pct >= 10:
        new_stop = entry_price * 1.05  # 锁定+5%
    elif profit_pct >= 5:
        new_stop = entry_price * 1.00  # 保本
    return max(current_stop, new_stop)

def should_scale_out(entry_price: float, current_price: float, shares: int) -> tuple:
    import logging; logging.getLogger(__name__).warning("[NotYetConnected] should_scale_out called but not wired to pipeline")
    """分批止盈: +20%减1/3, +30%再减1/3"""
    profit_pct = (current_price - entry_price) / entry_price * 100
    if profit_pct >= 30:
        return (True, int(shares * 0.5))  # 减半仓
    elif profit_pct >= 20:
        return (True, int(shares * 0.33))  # 减1/3
    return (False, 0)
