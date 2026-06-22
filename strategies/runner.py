
"""策略执行器 — 5战法并行"""
import logging, numpy as np
import pandas as pd
logger = logging.getLogger("aurora.strategies")

def analyze_all(candidates: list) -> list:
    """对所有候选执行5战法分析"""
    from data.sources import get_kline
    results = []
    for c in candidates[:10]:
        code = c.get("code", "")
        kline = get_kline(code, 120)
        if kline.empty or len(kline) < 30:
            results.append({"code": code, "name": c.get("name",""), "signal": False, "score": 0})
            continue
        signals = []
        # 1. 首板起爆
        fb = _check_first_board(kline)
        if fb: signals.append(("first_board", fb))
        # 2. 涨停回踩
        pb = _check_pullback(kline)
        if pb: signals.append(("pullback", pb))
        # 3. 波动点
        wp = _check_wave_point(kline)
        if wp: signals.append(("wave_point", wp))
        # 4. 均线突破(简化)
        ma = _check_ma_breakout(kline)
        if ma: signals.append(("ma_breakout", ma))
        best = max(signals, key=lambda x: x[1]) if signals else (None, 0)
        results.append({
            "code": code, "name": c.get("name",""), "signal": bool(signals),
            "best_strategy": best[0], "best_score": best[1] if best[1] else 0,
            "entry_price": float(kline["close"].iloc[-1]),
            "price": c.get("price", float(kline["close"].iloc[-1])),
        })
    return results

def _check_first_board(df, lookback=60, cons_days=5):
    if len(df) < lookback: return 0
    close = df["close"].values; vol = df["volume"].values
    chg = np.diff(close) / close[:-1] * 100
    lu_mask = np.where(chg[-lookback:] >= 9.5)[0]
    if len(lu_mask) == 0: return 0
    lu_idx = lu_mask[0]
    if len(close) - lu_idx - 1 < cons_days: return 0
    cons_zone = close[lu_idx+1:]
    cons_range = (max(cons_zone) - min(cons_zone)) / close[lu_idx] * 100
    if cons_range > 5: return 0
    vol_ratio = vol[-1] / np.mean(vol[-20:]) if np.mean(vol[-20:]) > 0 else 1
    if vol_ratio < 1.5: return 0
    score = 50 + min(cons_days * 2, 20) + (10 if cons_range < 3 else 0) + (8 if vol_ratio >= 2.5 else 0)
    return min(score, 100)

def _check_pullback(df):
    if len(df) < 30: return 0
    close = df["close"].values; vol = df["volume"].values
    chg = np.diff(close) / close[:-1] * 100
    lu_idx = np.where(chg >= 9.5)[0]
    if len(lu_idx) == 0: return 0
    last_lu = lu_idx[-1]
    rally_high = max(close[:last_lu+1]); rally_low = min(close[:last_lu+1])
    if (rally_high - rally_low) / rally_low < 0.10: return 0
    fib_382 = rally_high - (rally_high - rally_low) * 0.382
    dev = abs(close[-1] - fib_382) / fib_382
    if dev > 0.03: return 0
    return 50 + (20 if dev < 0.01 else 10)

def _check_wave_point(df, atr_period=14):
    if len(df) < atr_period + 10: return 0
    high = df["high"].values; low = df["low"].values; close = df["close"].values
    tr = [max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1])) for i in range(1, len(high))]
    atr = np.mean(tr[-atr_period:])
    wave = (max(high[-10:]) - min(low[-10:])) / close[-1]
    if wave < 0.03: return 0
    pos = (close[-1] - min(low[-10:])) / (max(high[-10:]) - min(low[-10:]))
    if pos > 0.3: return 0
    return 50 + (10 if wave > 0.05 else 5) + (10 if pos < 0.15 else 0)

def _check_ma_breakout(df):
    close = df["close"].values; vol = df["volume"].values
    if len(close) < 20: return 0
    ma5 = np.mean(close[-5:]); ma10 = np.mean(close[-10:]); ma20 = np.mean(close[-20:])
    if not (close[-1] > ma5 > ma10 > ma20): return 0
    vol_ratio = vol[-1] / np.mean(vol[-20:])
    if vol_ratio < 1.2: return 0
    return 60 + min(int((vol_ratio - 1.2) * 20), 20)
