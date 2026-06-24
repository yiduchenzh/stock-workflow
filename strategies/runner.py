"""策略执行器 — 5战法 + 波浪 + 123/2B · 斯波朗迪 (R21: 回测驱动修复)"""
import logging, numpy as np
import pandas as pd
logger = logging.getLogger("aurora.strategies")

def analyze_all(candidates: list, kline_override: dict = None) -> list:
    from data.sources import get_kline
    results = []
    for c in candidates[:15]:
        code = c.get("code", "")
        kline = kline_override.get(code) if kline_override else None
        if kline is None:
            kline = get_kline(code, 120)
        if kline.empty or len(kline) < 30:
            results.append({"code": code, "name": c.get("name",""), "signal": False, "score": 0, "price": c.get("price",0)})
            continue
        price = float(kline["close"].iloc[-1])
        signals = []
        # 五大战法
        fb = _check_first_board(kline)
        if fb > 0: signals.append(("first_board", fb, price))
        pb = _check_pullback(kline)
        if pb > 0: signals.append(("pullback", pb, price))
        wp = _check_wave_point(kline)
        if wp > 0: signals.append(("wave_point", wp, price))
        from strategies.naked_k import detect_pin_bar
        pb = detect_pin_bar(kline)
        tl = pb.get("score", 0) if pb else 0
        if tl > 0: signals.append(("test_line", tl, price))
        from strategies.naked_k import naked_k_score
        nk = naked_k_score(kline)
        if nk >= 50: signals.append(("naked_k", int(nk), price))  # R20 fix: threshold 40→60
        # 123法则 (斯波朗迪·真实实现)
        s123 = _check_123_rule(kline)
        if s123 > 0: signals.append(("123_rule", s123, price))
        # MA突破
        ma = _check_ma_breakout(kline)
        if ma > 0: signals.append(("ma_breakout", ma, price))
        # 多战法投票: >=2个战法看好→确认
        if len(signals) >= 2:
            weighted_score = sum(s[1] for s in signals) / len(signals) + 10
            best_strat = max(signals, key=lambda x: x[1])[0]
        elif signals:
            best_strat = signals[0][0]
            weighted_score = signals[0][1]
        else:
            best_strat = None; weighted_score = 0
        results.append({
            "code": code, "name": c.get("name",""),
            "signal": bool(signals),
            "best_strategy": best_strat, "best_score": weighted_score,
            "entry_price": price, "price": price,
            "stop_loss": price * 0.95, "take_profit": price * 1.10,
            "can_slim": c.get("can_slim", 50),
            "kline_df": kline,
            "signal_count": len(signals),
            "all_signals": [s[0] for s in signals],
        })
    return results

def _check_first_board(df, lookback=60, cons_days=5):
    if len(df) < lookback: return 0
    close = df["close"].values; vol = df["volume"].values
    chg = np.diff(close) / close[:-1] * 100
    lu_idx = np.where(chg[-lookback:] >= 9.5)[0]
    if len(lu_idx) == 0: return 0
    idx = lu_idx[0] + len(chg) - lookback
    if len(close) - idx - 1 < cons_days: return 0
    cons_zone = close[idx+1:]
    cons_range = (max(cons_zone) - min(cons_zone)) / close[idx] * 100
    if cons_range > 5: return 0
    vol_ratio = vol[-1] / np.mean(vol[-20:]) if np.mean(vol[-20:]) > 0 else 1
    if vol_ratio < 1.5: return 0
    score = 50 + min(cons_days * 2, 20) + (10 if cons_range < 3 else 0) + (8 if vol_ratio >= 2.5 else 0)
    return min(score, 100)

def _check_pullback(df):
    if len(df) < 30: return 0
    close = df["close"].values; vol = df["volume"].values
    chg = np.diff(close) / close[:-1] * 100
    lu = np.where(chg >= 9.5)[0]
    if len(lu) == 0: return 0
    last_lu = lu[-1]
    r_high = max(close[:last_lu+1]); r_low = min(close[:last_lu+1])
    if (r_high - r_low) / r_low < 0.10: return 0
    fib = r_high - (r_high - r_low) * 0.382
    dev = abs(close[-1] - fib) / fib
    if dev > 0.03: return 0
    return 50 + (20 if dev < 0.01 else 10)

def _check_wave_point(df, atr_period=14):
    """R20 fix: 趋势过滤 — 只在上升趋势中买低点"""
    if len(df) < atr_period + 30: return 0
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    # 趋势过滤: MA20 > MA50 且 close > MA20 (不在下跌趋势中接飞刀)
    ma20 = np.mean(c[-20:])
    ma50 = np.mean(c[-50:])
    if not (ma20 > ma50 and c[-1] > ma20):
        return 0
    tr = [max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])) for i in range(1, len(h))]
    atr = np.mean(tr[-atr_period:])
    wave = (max(h[-10:]) - min(l[-10:])) / c[-1]
    if wave < 0.015: return 0
    pos = (c[-1] - min(l[-10:])) / (max(h[-10:]) - min(l[-10:]))
    if pos > 0.55: return 0
    score = 50 + (10 if wave > 0.05 else 5) + (10 if pos < 0.15 else 0)
    # ATR/c > 1.5% 加分
    if atr / c[-1] > 0.015:
        score += 8
    return min(score, 100)

def _calc_adx(high, low, close, period=14):
    """ADX趋势强度 (0-100). ADX>=10=有趋势, 123法则可用"""
    if len(close) < period * 2 + 5:
        return 0
    n = len(close)
    pdm = [0.0]*n; mdm = [0.0]*n; tr = [0.0]*n
    for i in range(1, n):
        up = high[i] - high[i-1]
        dn = low[i-1] - low[i]
        pdm[i] = up if (up > dn and up > 0) else 0
        mdm[i] = dn if (dn > up and dn > 0) else 0
        tr[i] = max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1]))
    alpha = 2.0/(period+1)
    ps = [0.0]*n; ms = [0.0]*n; ts = [0.0]*n
    ps[period] = sum(pdm[1:period+1])/period
    ms[period] = sum(mdm[1:period+1])/period
    ts[period] = sum(tr[1:period+1])/period
    for i in range(period+1, n):
        ps[i] = ps[i-1] + alpha*(pdm[i]-ps[i-1])
        ms[i] = ms[i-1] + alpha*(mdm[i]-ms[i-1])
        ts[i] = ts[i-1] + alpha*(tr[i]-ts[i-1])
    dx = [0.0]*n
    for i in range(period, n):
        if ts[i] > 0:
            pd_ = 100*ps[i]/ts[i]; md_ = 100*ms[i]/ts[i]; s = pd_+md_
            if s > 0: dx[i] = 100*abs(pd_-md_)/s
    adx = [0.0]*n
    if n > period*2:
        adx[period*2] = sum(dx[period+1:period*2+1])/period
    for i in range(period*2+1, n):
        adx[i] = adx[i-1] + alpha*(dx[i]-adx[i-1])
    return max(0, min(100, adx[-1]))


def _check_test_line(df, wick_ratio=0.60):
    if len(df) < 5: return 0
    o, h, l, c = df["open"].values[-1], df["high"].values[-1], df["low"].values[-1], df["close"].values[-1]
    body_h = max(o, c); body_l = min(o, c)
    upper_wick = h - body_h; lower_wick = body_l - l
    total = h - l
    if total <= 0: return 0
    if lower_wick / total >= wick_ratio:
        return 55 + int(min(lower_wick/total - wick_ratio, 0.3) * 50)
    if upper_wick / total >= wick_ratio:
        return 40
    return 0

def _check_123_rule(df):
    """123法则+ADX: ①ADX趋势过滤 ②趋势线突破 ③回踩确认 ④放量验证"""
    if len(df) < 40: return 0
    close = df["close"].values; high = df["high"].values
    low = df["low"].values; vol = df["volume"].values
    # ADX趋势过滤: <15时无趋势, 123法则不可靠
    adx = _calc_adx(high, low, close)
    if adx < 10:
        return 0
    # 趋势线突破
    lookback = 20
    trendline_top = max(high[-lookback:])
    if close[-1] <= trendline_top * 0.98:
        return 0
    # 回踩确认+再次突破: 价格短暂回调后再次上涨突破前高
    recent_high_5 = max(high[-5:])
    ref_high = max(high[-10:-5]) if len(close) >= 10 else max(high[:-5])
    # 条件A: 当前价格突破最近5日高点 (再次突破)
    breakout = close[-1] > recent_high_5 * 0.99
    # 条件B: 回调不破前低 (回踩确认)
    ref_low = min(low[-10:-5]) if len(close) >= 10 else min(low[:-5])
    retrace_ok = min(low[-5:]) > ref_low * 0.95
    if not (breakout and retrace_ok):
        return 0
    # 放量验证
    vol_ratio = vol[-1] / np.mean(vol[-20:]) if np.mean(vol[-20:]) > 0 else 1
    if vol_ratio < 1.0:
        return 0
    ma20 = np.mean(close[-20:])
    ma50 = np.mean(close[-50:]) if len(close) >= 50 else ma20 * 0.99
    trend_score = 15 if ma20 > ma50 else 5
    adx_bonus = 10 if adx >= 40 else (5 if adx >= 25 else 0)
    score = 50 + trend_score + min(int((vol_ratio - 1.2) * 15), 15) + adx_bonus
    return min(score, 95)


def _check_ma_breakout(df):
    close = df["close"].values; vol = df["volume"].values
    if len(close) < 20: return 0
    ma5 = np.mean(close[-5:]); ma10 = np.mean(close[-10:]); ma20 = np.mean(close[-20:])
    if not (close[-1] > ma5 > ma10 > ma20): return 0
    vol_ratio = vol[-1] / np.mean(vol[-20:])
    if vol_ratio < 1.0: return 0
    return 60 + min(int((vol_ratio - 1.2) * 20), 20)
