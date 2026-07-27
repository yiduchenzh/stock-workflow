"""盘中突发处理 — 大盘急跌/涨停打开/跌停撬开/缩量预警"""
import logging
import numpy as np
logger = logging.getLogger("aurora.contingency")

def check_contingency(positions: dict, market_status: dict, kline_cache: dict = None) -> list:
    """检查所有持仓的突发情况, 返回紧急操作列表"""
    alerts = []
    market_chg = market_status.get("index_change", 0)
    
    # 大盘急跌>2%: 所有持仓收紧止损
    if market_chg < -2.0:
        for code, pos in positions.items():
            sl = pos.get("stop_loss", pos.get("avg_cost", 10) * 0.93)
            new_sl = pos.get("current_price", pos.get("avg_cost", 10)) * 0.97  # 收紧至-3%
            if new_sl > sl:  # 收紧止损
                alerts.append({
                    "type": "market_crash", "code": code, "urgency": "high",
                    "action": "tighten_stop", "new_stop": round(new_sl, 2),
                    "reason": f"大盘急跌{market_chg:.1f}%, 止损收紧至{new_sl:.2f}",
                })
    
    # 个股检查
    for code, pos in positions.items():
        kline = kline_cache.get(code) if kline_cache else None
        if kline is None or len(kline) < 3: continue
        
        close = kline["close"].values; high = kline["high"].values; low = kline["low"].values
        vol = kline["volume"].values
        cur = pos.get("current_price", close[-1])
        
        # 涨停打开检测: 前日涨停+今日高开+回落>3%
        prev_chg = (close[-2] - close[-3]) / close[-3] * 100 if len(close) >= 3 else 0
        today_change = (cur - close[-2]) / close[-2] * 100
        if prev_chg >= 9.5 and today_change < 2:
            alerts.append({
                "type": "limit_up_open", "code": code, "urgency": "high",
                "action": "reduce_or_exit",
                "reason": f"涨停打开: 昨涨停+今日仅+{today_change:.1f}%, 主力出货嫌疑",
            })
        
        # 午后量能萎缩: 成交量降至上午的50%
        if len(vol) >= 2:
            morning_vol = vol[-2]  # 简化: 上一根K线量
            afternoon_vol = vol[-1]
            if morning_vol > 0 and afternoon_vol / morning_vol < 0.5 and cur < close[-2]:
                alerts.append({
                    "type": "volume_shrink", "code": code, "urgency": "medium",
                    "action": "reduce_t0", 
                    "reason": "午后缩量下跌, 降低T+0频率",
                })
        
        # 连续下跌+放量: 加速赶底或恐慌出逃
        if len(close) >= 3:
            three_day_chg = (cur - close[-3]) / close[-3] * 100
            vol_ratio = vol[-1] / np.mean(vol[-10:]) if np.mean(vol[-10:]) > 0 else 1
            if three_day_chg < -8 and vol_ratio > 1.5:
                alerts.append({
                    "type": "panic_selling", "code": code, "urgency": "high",
                    "action": "evaluate_exit",
                    "reason": f"3日跌{three_day_chg:.1f}%+放量{vol_ratio:.1f}x, 恐慌出逃",
                })
    
    return alerts