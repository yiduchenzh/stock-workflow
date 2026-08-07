"""策略执行器 — 5战法+动量突破+板块轮动+波浪+123/2B · 斯波朗迪"""
import logging, numpy as np
logger = logging.getLogger("aurora.strategies")
_SECTOR_CACHE = {"data": None, "time": 0}

def analyze_all(candidates: list, kline_override: dict = None, market_regime: str = None) -> list:
    from data.sources import get_kline
    results = []

    # 板块轮动检测(全市场一次, 不在个股循环内)
    sector_best_code = None
    sector_score = 0
    sector_name = ""
    try:
        from strategies.sector_rotation import check_sector_rotation
        # 收集所有候选股的K线
        all_klines = {}
        for c in candidates[:15]:
            code = c.get("code", "")
            kline = kline_override.get(code) if kline_override else None
            if kline is None:
                kline = get_kline(code, 60)
            if kline is not None and not kline.empty:
                all_klines[code] = kline
        global _SECTOR_CACHE
        import time as _t
        if _SECTOR_CACHE["data"] is None or _t.time() - _SECTOR_CACHE["time"] > 300:
            try:
                from data.sources import get_sector_ranking
                _SECTOR_CACHE["data"] = get_sector_ranking(10)
                _SECTOR_CACHE["time"] = _t.time()
            except Exception:
                pass
        sr = check_sector_rotation(all_klines, _SECTOR_CACHE["data"])
        if sr["signal"]:
            sector_best_code = sr.get("code")
            sector_score = sr["score"]
            sector_name = sr.get("sector", "")
            logger.info(f"[Sector] {sector_name} leader={sector_best_code} score={sector_score}")
    except Exception as e:
        logger.debug(f"[Sector] rotation check fail: {e}")

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
        # pb = _check_pullback(kline)
        # if pb > 0: signals.append(("pullback", pb, price))  # 注释: 与mean_reversion重叠
        wp = _check_wave_point(kline)
        if wp > 0: signals.append(("wave_point", wp, price))

        # 均值回归 v1.0
        from strategies.mean_reversion import check_mean_reversion
        mr = check_mean_reversion(kline)
        if mr["signal"]: signals.append(("mean_reversion", mr["score"], price))

        # 动量突破 v1.0 (R24新增 — 与wave_point低相关)
        from strategies.momentum_breakout import check_momentum_breakout
        mo = check_momentum_breakout(kline, market_regime)
        if mo["signal"]: signals.append(("momentum_breakout", mo["score"], price))

        # 裸K四大形态信号 v2.0 (完整形态库)
        from strategies.naked_k import (
            detect_pin_bar, detect_inside_bar, detect_engulfing,
            detect_fakey, detect_supply_demand_zones, naked_k_score
        )
        pb = detect_pin_bar(kline)
        if pb and pb.get("score", 0) > 0:
            signals.append(("naked_pinbar", pb["score"], price))
        ib = detect_inside_bar(kline)
        if ib and ib.get("score", 0) > 0:
            signals.append(("naked_insidebar", ib["score"], price))
        eg = detect_engulfing(kline)
        if eg and eg.get("score", 0) > 0:
            signals.append(("naked_engulf", eg["score"], price))
        # fy = detect_fakey(kline)
        # if fy and fy.get("score", 0) > 0:
        #     signals.append(("naked_fakey", fy["score"], price))  # 注释: <2%触发率, 低效
        sd = detect_supply_demand_zones(kline)
        sd_score = max((z.get("score", 0) for z in sd), default=0) if sd else 0
        if sd_score > 0:
            signals.append(("naked_supply_demand", sd_score, price))
        # # 裸K综合评分兜底(无具体形态时) — 注释: 低效(<1%触发)
        # nk = naked_k_score(kline)
        # if nk >= 50 and not any(s[0].startswith("naked_") for s in signals):
        #     signals.append(("naked_k", int(nk), price))

        # 缠论三类买卖点信号 v3.0
        from strategies.chan_theory import detect_fractals
        chan = detect_fractals(kline)
        if chan.get("signal"):
            bs = chan.get("last_bs", {})
            if bs:
                bs_type = bs.get("type", "")
                bs_score = bs.get("score", 70)
                signals.append(("chan_" + bs_type, bs_score, price))
            # else:  # 注释: 泛化chan_theory信号<1%触发
            #     signals.append(("chan_theory", 65, price))
        # # 缠论区间套精确度补充 — 注释: <1%触发
        # from strategies.chan_theory import interval_nesting
        # try:
        #     nesting = interval_nesting(kline)
        #     if nesting.get("precision") == "high" and not any(s[0].startswith("chan_") for s in signals):
        #         signals.append(("chan_theory", 70, price))
        # except Exception:
        #     pass

        # # 123法则 — 注释: <3%触发率, 低效
        # s123 = _check_123_rule(kline)
        # if s123 > 0: signals.append(("123_rule", s123, price))

        # MA突破
        ma = _check_ma_breakout(kline)
        if ma > 0: signals.append(("ma_breakout", ma, price))

        # 板块轮动加成: 如果是板块推荐股, 加信号分
        if code == sector_best_code and sector_best_code is not None:
            bonus = int(sector_score * 0.5)  # 板块轮动50%加成
            if not signals:
                signals.append(("sector_rotation", max(30, bonus), price))
            else:
                # 给已有信号加分
                signals = [(s[0], min(100, s[1] + int(bonus * 0.3)), s[2]) for s in signals]
                signals.append(("sector_rotation", min(100, bonus), price))

        # 拉里·威廉姆斯短线信号
        try:
            from strategies.larry_williams import williams_composite_score
            wm = williams_composite_score(kline, code)
            for ws in wm.get("signals", []):
                if ws[0] not in [s[0] for s in signals]:
                    signals.append(ws)
        except Exception:
            pass

        # 昨收价极简战法信号 (v14.45: 短线专属 — 买点A挖坑转强/买点B强势延续)
        try:
            from strategies.prev_close_play import check_prev_close
            pc_sig = check_prev_close(kline)
            if pc_sig["signal"]:
                signals.append(("prev_close_" + pc_sig["type"], pc_sig["score"], price))
        except Exception as e:
            logger.debug(f"[PrevClose] {code}: {e}")

        # 多战法投票 (双重确认: 需要≥2个信号)
        if len(signals) >= 2:
            weighted_score = sum(s[1] for s in signals) / len(signals) + 10
            best_strat = max(signals, key=lambda x: x[1])[0]
        else:
            # 单信号或0信号 → 不确认
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
def _check_first_board(df, lookback: int = 60, cons_days: int = 5) -> int:
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

def _check_pullback(df) -> int:
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

def _check_wave_point(df, atr_period: int = 14) -> int:
    if len(df) < atr_period + 30: return 0
    h, l, c = df["high"].values, df["low"].values, df["close"].values
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
    if atr / c[-1] > 0.015:
        score += 8
    return min(score, 100)

def _calc_adx(high, low, close, period: int = 14) -> float:
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

def _check_test_line(df, wick_ratio: float = 0.60) -> int:
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

def _check_123_rule(df) -> int:
    if len(df) < 40: return 0
    close = df["close"].values; high = df["high"].values
    low = df["low"].values; vol = df["volume"].values
    adx = _calc_adx(high, low, close)
    if adx < 10:
        return 0
    lookback = 20
    trendline_top = max(high[-lookback:])
    if close[-1] <= trendline_top * 0.98:
        return 0
    recent_high_5 = max(high[-5:])
    ref_high = max(high[-10:-5]) if len(close) >= 10 else max(high[:-5])
    breakout = close[-1] > recent_high_5 * 0.99
    ref_low = min(low[-10:-5]) if len(close) >= 10 else min(low[:-5])
    retrace_ok = min(low[-5:]) > ref_low * 0.95
    if not (breakout and retrace_ok):
        return 0
    vol_ratio = vol[-1] / np.mean(vol[-20:]) if np.mean(vol[-20:]) > 0 else 1
    if vol_ratio < 1.0:
        return 0
    ma20 = np.mean(close[-20:])
    ma50 = np.mean(close[-50:]) if len(close) >= 50 else ma20 * 0.99
    trend_score = 15 if ma20 > ma50 else 5
    adx_bonus = 10 if adx >= 40 else (5 if adx >= 25 else 0)
    score = 50 + trend_score + min(int((vol_ratio - 1.2) * 15), 15) + adx_bonus
    return min(score, 95)

def _check_ma_breakout(df) -> int:
    close = df["close"].values; vol = df["volume"].values
    if len(close) < 20: return 0
    ma5 = np.mean(close[-5:]); ma10 = np.mean(close[-10:]); ma20 = np.mean(close[-20:])
    if not (close[-1] > ma5 > ma10 > ma20): return 0
    vol_ratio = vol[-1] / np.mean(vol[-20:])
    if vol_ratio < 1.0: return 0
    return 60 + min(int((vol_ratio - 1.2) * 20), 20)
