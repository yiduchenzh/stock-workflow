"""多周期盘中分析 — 日线定方向 + 30分定趋势 + 5分定买卖点
缠论+裸K+123法则在3个时间框架综合研判"""
import logging, urllib.request, json, numpy as np
import pandas as pd
logger = logging.getLogger("aurora.mtf_intraday")

def get_mtf_kline(code: str) -> dict:
    """获取3个时间框架的K线数据"""
    pfx = f"sz{code}" if code and code.startswith(("0","3")) else f"sh{code}"
    result = {"daily": None, "m30": None, "m5": None}
    urls = {
        "daily": f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={pfx},day,,,120,qfq",
        "m5": f"http://ifzq.gtimg.cn/appstock/app/kline/mkline?param={pfx},m5,,,100",
        "m30": f"http://ifzq.gtimg.cn/appstock/app/kline/mkline?param={pfx},m30,,,100",
    }
    for tf, url in urls.items():
        try:
            d = json.loads(urllib.request.urlopen(url, timeout=10).read().decode("gbk", "replace"))
            if tf == "daily":
                raw = d.get("data", {}).get(pfx, {}).get("qfqday", [])
            else:
                raw = d.get("data", {}).get(pfx, {}).get(tf, [])
            if raw:
                rows = []
                for bar in raw:
                    rows.append({
                        "date": str(bar[0]),
                        "open": float(bar[1]),
                        "close": float(bar[2]),
                        "high": float(bar[3]),
                        "low": float(bar[4]),
                        "volume": float(bar[5]) if len(bar) > 5 else 0,
                    })
                df = pd.DataFrame(rows)
                df["date"] = pd.to_datetime(df["date"])
                result[tf] = df
        except Exception as e:
            logger.warning(f"[MTF] {tf} data fail: {e}")
    return result

def analyze_daily_trend(daily_df) -> dict:
    """日线趋势: MACD方向 + MA排列 + 缠论分型"""
    if daily_df is None or len(daily_df) < 30:
        return {"direction": "unknown", "score": 50, "desc": "数据不足"}
    c = daily_df["close"].values
    ema12 = _ema(c, 12); ema26 = _ema(c, 26)
    dif = ema12 - ema26; dea = _ema(dif, 9)
    macd_bull = dif[-1] > dea[-1] and dif[-1] > 0
    ma5 = np.mean(c[-5:]); ma10 = np.mean(c[-10:]); ma20 = np.mean(c[-20:])
    ma_bull = c[-1] > ma5 > ma10 > ma20
    score = (50 if macd_bull else 20) + (30 if ma_bull else 10)
    direction = "bull" if score >= 60 else ("bear" if score <= 30 else "range")
    return {"direction": direction, "score": score, "macd_bull": macd_bull, "ma_bull": ma_bull,
            "desc": f"MACD={'↑' if macd_bull else '↓'} MA={'↑' if ma_bull else '↓'} score={score}"}

def analyze_m30_trend(m30_df) -> dict:
    """30分钟趋势: MACD + 均线排列 + 波段高低点"""
    if m30_df is None or len(m30_df) < 30:
        return {"direction": "unknown", "score": 50, "desc": "数据不足"}
    c = m30_df["close"].values
    ema12 = _ema(c, 12); ema26 = _ema(c, 26)
    dif = ema12 - ema26; dea = _ema(dif, 10)
    macd_bull = dif[-1] > dea[-1]
    macd_rising = dif[-1] > dif[-3]  # MACD柱在升高
    ma5 = np.mean(c[-5:]); ma10 = np.mean(c[-10:]); ma20 = np.mean(c[-20:])
    ma_bull = c[-1] > ma5 > ma10
    # 最近高低点
    high_5 = np.max(c[-20:]); low_5 = np.min(c[-20:])
    near_high = c[-1] >= high_5 * 0.97
    near_low = c[-1] <= low_5 * 1.03
    score = (30 if macd_bull else 10) + (20 if macd_rising else 5) + (25 if ma_bull else 5) + (15 if near_high else -10 if near_low else 0)
    direction = "bull" if score >= 60 else ("bear" if score <= 35 else "range")
    return {"direction": direction, "score": score, "macd_bull": macd_bull, "ma_bull": ma_bull,
            "desc": f"MACD={'↑' if macd_bull else '↓'} MA={'↑' if ma_bull else '↓'} score={score}"}

def analyze_m5_entry(m5_df) -> dict:
    """5分钟买卖点: 缠论分型+裸K+123法则"""
    if m5_df is None or len(m5_df) < 30:
        return {"signal": "none", "score": 0, "desc": "数据不足"}
    c = m5_df["close"].values; h = m5_df["high"].values; l = m5_df["low"].values
    
    # 缠论分型检测 (顶分型/底分型)
    tops = []; bottoms = []
    for i in range(2, len(c) - 2):
        if h[i] > h[i-1] and h[i] > h[i+1]: tops.append((i, h[i]))
        if l[i] < l[i-1] and l[i] < l[i+1]: bottoms.append((i, l[i]))
    
    # 裸K形态检测
    signals = []
    last5 = m5_df.tail(5)
    body = abs(c[-1] - last5["open"].iloc[-1])
    upper_wick = h[-1] - max(c[-1], last5["open"].iloc[-1])
    lower_wick = min(c[-1], last5["open"].iloc[-1]) - l[-1]
    
    # Pin Bar: 长影线
    if upper_wick > body * 2 and lower_wick < body * 0.3:
        signals.append({"type": "shooting_star", "dir": "sell", "score": 70})
    elif lower_wick > body * 2 and upper_wick < body * 0.3:
        signals.append({"type": "hammer", "dir": "buy", "score": 70})
    
    # Inside Bar
    if len(last5) >= 2:
        prev = last5.iloc[-2]; cur = last5.iloc[-1]
        if cur["high"] <= prev["high"] and cur["low"] >= prev["low"]:
            compression = 1 - (cur["high"] - cur["low"]) / max(prev["high"] - prev["low"], 0.01)
            if compression > 0.5:
                signals.append({"type": "inside_bar", "dir": "breakout_pending", "score": 60})
    
    # 123法则 (趋势线突破)
    if len(c) >= 20:
        recent_high = max(c[-20:]); recent_low = min(c[-20:])
        retrace = (c[-1] - recent_low) / max(recent_high - recent_low, 0.01) * 100
        if retrace > 50 and c[-1] > c[-2] and len(tops) > 0:
            signals.append({"type": "123_rule_buy", "dir": "buy", "score": 65})
        elif retrace < 50 and c[-1] < c[-2] and len(bottoms) > 0:
            signals.append({"type": "123_rule_sell", "dir": "sell", "score": 65})
    
    # 缠论顶底分型确认
    if tops and c[-1] >= tops[-1][1] * 0.98:
        signals.append({"type": "top_fractal", "dir": "sell", "score": 55})
    if bottoms and c[-1] <= bottoms[-1][1] * 1.02:
        signals.append({"type": "bottom_fractal", "dir": "buy", "score": 55})
    
    if not signals:
        return {"signal": "none", "score": 0, "desc": "无信号", "tops": len(tops), "bottoms": len(bottoms)}
    
    best = max(signals, key=lambda s: s["score"])
    return {"signal": best["dir"], "score": best["score"],
            "desc": f"{best['type']} score={best['score']}",
            "signals": signals, "tops": len(tops), "bottoms": len(bottoms)}

def synthesize(daily: dict, m30: dict, m5: dict) -> dict:
    """三周期综合研判"""
    # 日线方向 = 主方向
    main_dir = daily.get("direction", "unknown")
    m30_dir = m30.get("direction", "unknown")
    m5_signal = m5.get("signal", "none")
    
    # 三级共振
    if main_dir == "bull" and m30_dir == "bull" and "buy" in m5_signal:
        return {"action": "open_buy", "confidence": "high",
                "desc": f"三级共振买入 | 日{m5_dir_to_chr(main_dir)} 30分{m5_dir_to_chr(m30_dir)} 5分{m5_signal}"}
    if main_dir == "bear" and m30_dir == "bear" and "sell" in m5_signal:
        action = "close_long" if "sell" in m5_signal else "none"
        return {"action": action, "confidence": "high",
                "desc": f"三级共振卖出 | 日{m5_dir_to_chr(main_dir)} 30分{m5_dir_to_chr(m30_dir)} 5分{m5_signal}"}
    
    # 二级共振 (日线+30分一致)
    if main_dir == m30_dir:
        if main_dir == "bull" and "buy" in m5_signal:
            return {"action": "open_buy", "confidence": "medium",
                    "desc": f"二级共振买入 | 日{m5_dir_to_chr(main_dir)} 30分{m5_dir_to_chr(m30_dir)} 5分{m5_signal}"}
        if main_dir == "bear" and "sell" in m5_signal:
            return {"action": "close_long", "confidence": "medium",
                    "desc": f"二级共振卖出 | 日{m5_dir_to_chr(main_dir)} 30分{m5_dir_to_chr(m30_dir)} 5分{m5_signal}"}
    
    # 仅日线方向 (v14.44: 收紧阈值 — 单日线触发须score≤20极空+30分不偏多, 防正常波动误减仓)
    if main_dir == "bull" and daily.get("score", 0) >= 70:
        return {"action": "hold", "confidence": "low",
                "desc": f"日线偏多,持有观察 | 5分{m5_signal}"}
    if main_dir == "bear" and daily.get("score", 0) <= 20 and m30_dir != "bull":
        return {"action": "reduce", "confidence": "low",
                "desc": f"日线极空,减仓避险 | 30分{m5_dir_to_chr(m30_dir)} 5分{m5_signal}"}
    
    return {"action": "wait", "confidence": "low",
            "desc": f"观望 | 日{m5_dir_to_chr(main_dir)} 30分{m5_dir_to_chr(m30_dir)} 5分{m5_signal}"}

def m5_dir_to_chr(d):
    return {"bull": "↑", "bear": "↓", "range": "→", "unknown": "?"}.get(d, "?")

def _ema(data, period):
    alpha = 2 / (period + 1)
    result = [data[0]]
    for i in range(1, len(data)):
        result.append(alpha * data[i] + (1 - alpha) * result[-1])
    return np.array(result)

def analyze_stock(code: str, has_position: bool = False) -> dict:
    """一站式多周期分析 + 缠论区间套精确定位"""
    kl = get_mtf_kline(code)
    daily_r = analyze_daily_trend(kl["daily"])
    m30_r = analyze_m30_trend(kl["m30"])
    m5_r = analyze_m5_entry(kl["m5"])
    decision = synthesize(daily_r, m30_r, m5_r)

    # 缠论区间套: 在日线K线数据上做三级递归
    chan_nesting = {"precision": "none", "score": 0, "detail": "未触发"}
    if kl["daily"] is not None and len(kl["daily"]) >= 90:
        try:
            from strategies.chan_theory import interval_nesting
            chan_nesting = interval_nesting(kl["daily"])
        except Exception as e:
            logger.warning(f"[ChanNest] {code}: {e}")

    # 区间套修正: 如果区间套高精度(precise)且5分信号方向一致, 提升置信度
    if chan_nesting.get("precise") and decision["confidence"] != "high":
        # 三级区间套共振, 提升决策等级
        nest_dir = chan_nesting.get("direction", "")
        if ("bullish" in nest_dir and "buy" in decision.get("action", "")) or            ("bearish" in nest_dir and "sell" in decision.get("action", "")):
            decision["confidence"] = "high"
            decision["desc"] += " [缠论区间套确认]"
        elif "bullish" in nest_dir:
            # 区间套看多但MTF未买入: 提示但不强制
            decision["chan_note"] = "缠论区间套看多, 等待5分买点"
        elif "bearish" in nest_dir:
            decision["chan_note"] = "缠论区间套看空, 注意风险"

    return {
        "code": code, "decision": decision,
        "daily": daily_r, "m30": m30_r, "m5": m5_r,
        "chan_nesting": chan_nesting,
        "has_position": has_position,
    }
