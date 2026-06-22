"""仓位缩放 — 金字塔加仓+分批止盈+动态仓位管理"""
import logging
logger = logging.getLogger("aurora.scaling")

def check_add_position(pos: dict, current_price: float, kline_df=None, cfg: dict = None) -> dict:
    """金字塔加仓条件检查 (欧奈尔+股市操练大全)
    
    条件:
    1. 盈利≥2% (加仓不摊平亏损 — 斯波朗迪鳄鱼原则)
    2. 放量 (当日量>5日均量1.2倍)
    3. 价格在MA10之上 (趋势未破)
    4. 金字塔: 加仓量 < 底仓量 (递减)
    """
    if not pos: return {"should_add": False, "reason": "无持仓"}
    
    cost = pos.get("avg_cost", current_price)
    shares = pos.get("shares", 0)
    profit_pct = (current_price - cost) / cost * 100 if cost > 0 else 0
    
    # 铁律: 亏损不摊平
    if profit_pct < 2.0:
        return {"should_add": False, "reason": f"盈利不足({profit_pct:.1f}%<2%),不摊平"}
    
    # 量能检查
    if kline_df is not None and len(kline_df) >= 5:
        vol = kline_df["volume"].values
        vol_ratio = vol[-1] / np.mean(vol[-5:]) if np.mean(vol[-5:]) > 0 else 1
        if vol_ratio < 1.2:
            return {"should_add": False, "reason": f"量能不足(量比{vol_ratio:.1f}<1.2)"}
    
    # MA10支撑
    if kline_df is not None and len(kline_df) >= 10:
        ma10 = np.mean(kline_df["close"].values[-10:])
        if current_price < ma10:
            return {"should_add": False, "reason": f"跌破MA10({ma10:.2f})"}
    
    # 金字塔加仓: 每次加仓量为底仓的50%→30%→20%
    import numpy as np
    add_count = pos.get("add_count", 0)
    pyramid_ratios = [0.5, 0.3, 0.2]
    ratio = pyramid_ratios[min(add_count, len(pyramid_ratios)-1)]
    add_shares = max(100, int(shares * ratio / 100) * 100)
    
    return {
        "should_add": True, "shares": add_shares, "ratio": ratio,
        "price": current_price, "profit_pct": round(profit_pct, 1),
        "reason": f"金字塔第{add_count+1}次加仓(盈利{profit_pct:.1f}%)"
    }

def check_scale_out(pos: dict, current_price: float) -> dict:
    """分批止盈检查 (斯波朗迪+欧奈尔)
    
    分批计划:
    +10% → 减1/3 (锁定部分利润)
    +20% → 再减1/3 (让剩余奔跑)
    +30% → 减到底仓 (清仓)
    """
    cost = pos.get("avg_cost", current_price)
    profit_pct = (current_price - cost) / cost * 100 if cost > 0 else 0
    shares = pos.get("shares", 0)
    scaled = pos.get("scaled_out", 0)
    
    # +30%: 清仓
    if profit_pct >= 30 and scaled < 3:
        return {"should_scale": True, "ratio": 1.0, "shares": shares,
                "reason": f"+30%清仓(盈利{profit_pct:.1f}%)"}
    # +20%: 减1/3
    if profit_pct >= 20 and scaled < 2:
        sell_shares = max(100, int(shares * 0.33 / 100) * 100)
        return {"should_scale": True, "ratio": 0.33, "shares": sell_shares,
                "reason": f"+20%减1/3(盈利{profit_pct:.1f}%)"}
    # +10%: 减1/3
    if profit_pct >= 10 and scaled < 1:
        sell_shares = max(100, int(shares * 0.33 / 100) * 100)
        return {"should_scale": True, "ratio": 0.33, "shares": sell_shares,
                "reason": f"+10%减1/3(盈利{profit_pct:.1f}%)"}
    
    return {"should_scale": False, "reason": f"盈利{profit_pct:.1f}%,未触发止盈"}

def calc_dynamic_position(capital: float, score: float, confidence: float, 
                          market_regime: str, garch_adj: float = 1.0) -> float:
    """动态仓位计算: 综合评分+置信度+市场状态+GARCH
    
    返回: 仓位比例 (0.01~0.25)
    """
    base = 0.05  # 基础仓位5%
    
    # 评分加成
    if score >= 80: base += 0.10
    elif score >= 65: base += 0.05
    elif score >= 50: base += 0.02
    
    # 置信度加成
    base *= (0.5 + confidence * 0.5)
    
    # 市场状态调整
    regime_mult = {"bull_strong": 1.2, "bull_weak": 1.0, "range": 0.7,
                   "bear_weak": 0.3, "bear_strong": 0.1}
    base *= regime_mult.get(market_regime, 0.5)
    
    # GARCH波动率调整
    base *= garch_adj
    
    return max(0.01, min(base, 0.25))