"""T+0 日内做T模块 — 底仓做T+0策略 (先买后卖/先卖后买)"""
import logging, numpy as np
from datetime import datetime
from data.sources import get_kline_period, get_tencent_quotes

logger = logging.getLogger("aurora.t0")

def calc_intraday_volatility(code: str) -> dict:
    """计算日内波动率，判断是否有做T空间"""
    try:
        # 5分钟K线判断日内波动
        df = get_kline_period(code, "5min", 48)  # 近2天5分钟线
        if df is None or len(df) < 12:
            return {"tradable": False, "reason": "数据不足"}
        highs = df["high"].values[-12:]
        lows = df["low"].values[-12:]
        closes = df["close"].values
        # 日内振幅
        day_high = max(highs[-6:])  # 今天最高
        day_low = min(lows[-6:])    # 今天最低
        amplitude = (day_high - day_low) / day_low * 100
        # 当前价格位置(从低点反弹%)
        current = closes[-1]
        rally_from_low = (current - day_low) / (day_high - day_low) * 100 if day_high > day_low else 50
        return {
            "tradable": amplitude >= 2.5,  # 振幅>2.5%才有做T空间
            "amplitude": round(amplitude, 2),
            "day_high": day_high,
            "day_low": day_low,
            "position_pct": round(rally_from_low, 0),  # 0=在最低, 100=在最高
            "reason": f"振幅{amplitude:.1f}%" if amplitude >= 2.5 else f"振幅{amplitude:.1f}%<2.5%,不合适",
        }
    except Exception as e:
        return {"tradable": False, "reason": f"分析失败: {e}"}

def detect_t0_signal(code: str, quote: dict, position: dict) -> dict:
    """检测T+0信号: 正T(先买后卖) 或 反T(先卖后买)"""
    result = {"signal": None, "action": None, "reason": "", "confidence": 0}
    cost = position.get("avg_cost", 0)
    shares = position.get("shares", 0)
    price = quote.get("price", 0)
    
    if cost <= 0 or shares <= 0 or price <= 0:
        return result
    
    profit_pct = (price - cost) / cost * 100
    
    # 获取日内波动数据
    vol_data = calc_intraday_volatility(code)
    if not vol_data.get("tradable"):
        return result
    
    amp = vol_data.get("amplitude", 0)
    pos_pct = vol_data.get("position_pct", 50)
    
    # ── 反T(先卖后买): 急涨到高位时卖出底仓,回落买回 ──
    # 条件: 价格在高位(>70%) + 盈利>1% + 振幅够大
    if pos_pct >= 75 and profit_pct > 1.0 and amp >= 2.5:
        # 卖出比例: 根据位置决定
        if pos_pct >= 90:
            ratio = 0.5  # 接近最高,出半仓
        else:
            ratio = 0.33  # 偏高位置,出1/3
        
        t_shares = max(100, int(shares * ratio / 100) * 100)
        result.update({
            "signal": "reverse_t", "action": "sell",
            "reason": f"反T卖出:价格在{pos_pct:.0f}%高位+盈利{profit_pct:.1f}%+振幅{amp:.1f}%",
            "shares": t_shares, "ratio": ratio, "confidence": min(80, 50 + pos_pct - 70),
        })
        return result
    
    # ── 正T(先买后卖): 急跌到低位时买入,反弹卖出底仓 ──
    # 条件: 价格在低位(<25%) + (盈利>0 或 亏损<5%) + 振幅够大
    if pos_pct <= 30 and profit_pct > -5.0 and amp >= 2.5:
        t_shares = max(100, int(shares * 0.2 / 100) * 100)  # 买底仓20%
        result.update({
            "signal": "forward_t", "action": "buy",
            "reason": f"正T买入:价格在{pos_pct:.0f}%低位+盈利{profit_pct:.1f}%+振幅{amp:.1f}%",
            "shares": t_shares, "ratio": 0.2, "confidence": min(75, 50 + (30 - pos_pct)),
        })
        return result
    
    return result

def execute_t0(account, code: str, signal: dict) -> dict:
    """执行T+0交易"""
    if not signal or not signal.get("signal"):
        return {"success": False}
    
    action = signal["action"]
    shares = signal["shares"]
    
    # 实时价格
    quotes = get_tencent_quotes([code])
    q = quotes.get(code, {})
    price = q.get("price", 0)
    if price <= 0:
        return {"success": False, "error": "无法获取实时价格"}
    
    if action == "sell":
        # 反T: 卖出底仓
        result = account.sell(code, price, shares, f"t0_reverse_{signal['reason'][:20]}")
        logger.info(f"[T+0] 反T卖出 {code} {shares}股 @{price:.2f}")
        return result
    elif action == "buy":
        # 正T: 买入浮动仓
        result = account.buy(code, price, shares, f"t0_forward_{signal['reason'][:20]}")
        logger.info(f"[T+0] 正T买入 {code} {shares}股 @{price:.2f}")
        return result
    
    return {"success": False, "error": f"未知操作:{action}"}
