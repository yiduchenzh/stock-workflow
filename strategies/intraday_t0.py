"""日内T+0引擎 — 5策略并行·VWAP回归·A股T+1兼容"""
import numpy as np
import logging
logger = logging.getLogger("aurora.t0")

def run_t0_analysis(positions: dict, kline_cache: dict, cfg: dict) -> list:
    import logging; logging.getLogger(__name__).warning("[NotYetConnected] run_t0_analysis called but not wired to pipeline")
    """对所有持仓运行T+0分析, 返回可执行计划"""
    if not positions: return []
    t0_cfg = cfg.get("intraday_t0", {})
    if not t0_cfg.get("enabled", True): return []
    
    plans = []
    for code, pos in positions.items():
        if pos.get("shares", 0) < 200: continue  # 至少2手底仓
        kline = kline_cache.get(code)
        if kline is None or len(kline) < 10: continue
        
        price = float(kline["close"].values[-1])
        cost = pos.get("avg_cost", price)
        shares = pos.get("shares", 0)
        t0_shares = min(int(shares * 0.30 / 100) * 100, shares // 2)  # 最多用30%底仓做T
        if t0_shares < 100: continue
        
        # 运行5个策略
        signals = []
        s1 = _t0_vwap_reversion(kline, price)
        if s1: signals.append(s1)
        s2 = _t0_grid(kline, price, cost)
        if s2: signals.append(s2)
        s3 = _t0_momentum(kline, price)
        if s3: signals.append(s3)
        s4 = _t0_mean_reversion(kline, price, cost)
        if s4: signals.append(s4)
        s5 = _t0_volume_breakout(kline, price)
        if s5: signals.append(s5)
        
        if not signals: continue
        
        # 取最强信号
        best = max(signals, key=lambda x: x["score"])
        if best["score"] < 60: continue
        
        plans.append({
            "code": code, "strategy": "t0", "t0_type": best["type"],
            "direction": best["direction"],
            "entry_price": round(best.get("entry", price), 2),
            "exit_price": round(best.get("target", price), 2),
            "shares": t0_shares,
            "score": best["score"],
            "risk": round(abs(best.get("entry", price) - price) / price * 100, 2),
        })
    
    plans.sort(key=lambda x: x["score"], reverse=True)
    return plans[:cfg.get("risk", {}).get("max_positions", 3)]

# ═══ 策略1: VWAP回归 (A股最有效) ═══
def _t0_vwap_reversion(kline, price):
    """价格偏离VWAP超2σ→回归, 胜率~65%"""
    if kline is None or len(kline) < 5: return None
    high, low, close, vol = kline["high"].values, kline["low"].values, kline["close"].values, kline["volume"].values
    typical = (high[-20:] + low[-20:] + close[-20:]) / 3
    vwap = np.sum(typical * vol[-20:]) / np.sum(vol[-20:]) if np.sum(vol[-20:]) > 0 else price
    dev = (price - vwap) / vwap * 100
    # 偏离VWAP下方→买入做多方向T
    if dev < -2.0:
        return {"type": "vwap_long", "direction": "buy_first", "entry": price,
                "target": round(vwap, 2), "score": 75, "desc": f"VWAP下方{abs(dev):.1f}%→回归"}
    # 偏离VWAP上方→卖出做空方向T
    if dev > 2.5:
        return {"type": "vwap_short", "direction": "sell_first", "entry": price,
                "target": round(vwap, 2), "score": 70, "desc": f"VWAP上方{dev:.1f}%→回归"}
    return None

# ═══ 策略2: 网格做T ═══
def _t0_grid(_kline, price, cost):
    """围绕成本价的网格: 低于成本→买入, 高于成本+2%→卖出"""
    profit_pct = (price - cost) / cost * 100 if cost > 0 else 0
    # 低于成本→先买后卖
    if profit_pct < -2.0:
        return {"type": "grid_buy", "direction": "buy_first",
                "entry": price, "target": round(cost, 2),
                "score": 65, "desc": f"低于成本{abs(profit_pct):.1f}%→网格买入"}
    # 高于成本+3%→先卖后买
    if profit_pct > 3.0:
        return {"type": "grid_sell", "direction": "sell_first",
                "entry": price, "target": round(cost * 1.01, 2),
                "score": 65, "desc": f"高于成本{profit_pct:.1f}%→网格卖出"}
    return None

# ═══ 策略3: 动量T+0 (顺日内趋势) ═══
def _t0_momentum(kline, price):
    """连续3根阳线+放量→追涨做多"""
    if len(kline) < 4: return None
    close = kline["close"].values; vol = kline["volume"].values
    # 连续3阳
    if close[-1] > close[-2] > close[-3] > close[-4]:
        vol_ratio = vol[-1] / np.mean(vol[-10:]) if np.mean(vol[-10:]) > 0 else 1
        if vol_ratio > 1.5:
            return {"type": "momentum_long", "direction": "buy_first",
                    "entry": price, "target": round(price * 1.015, 2),
                    "score": 60, "desc": "3连阳放量→追涨"}
    # 连续3阴
    if close[-1] < close[-2] < close[-3] < close[-4]:
        vol_ratio = vol[-1] / np.mean(vol[-10:]) if np.mean(vol[-10:]) > 0 else 1
        if vol_ratio > 1.5:
            return {"type": "momentum_short", "direction": "sell_first",
                    "entry": price, "target": round(price * 0.985, 2),
                    "score": 55, "desc": "3连阴放量→杀跌"}
    return None

# ═══ 策略4: 均值回归 ═══
def _t0_mean_reversion(kline, price, _cost):
    """RSI超卖→反弹回归均值"""
    if len(kline) < 14: return None
    close = kline["close"].values
    deltas = np.diff(close[-14:])
    gains = np.where(deltas > 0, deltas, 0); losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains); avg_loss = np.mean(losses)
    rsi = 100 - 100 / (1 + avg_gain / avg_loss) if avg_loss > 0 else 100
    if rsi < 25:
        return {"type": "rsi_oversold", "direction": "buy_first",
                "entry": price, "target": round(price * 1.01, 2),
                "score": 70, "desc": f"RSI超卖({rsi:.0f})→反弹"}
    if rsi > 78:
        return {"type": "rsi_overbought", "direction": "sell_first",
                "entry": price, "target": round(price * 0.99, 2),
                "score": 65, "desc": f"RSI超买({rsi:.0f})→回调"}
    return None

# ═══ 策略5: 量价突破 ═══
def _t0_volume_breakout(kline, price):
    """巨量+突破前高→日内趋势启动"""
    if len(kline) < 10: return None
    high, vol = kline["high"].values, kline["volume"].values
    prev_high = max(high[-10:-1])
    vol_ratio = vol[-1] / np.mean(vol[-10:]) if np.mean(vol[-10:]) > 0 else 1
    if price > prev_high and vol_ratio > 2.5:
        return {"type": "breakout", "direction": "buy_first",
                "entry": price, "target": round(price * 1.02, 2),
                "score": 80, "desc": "巨量突破前高→强势"}
    return None