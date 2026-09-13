"""
上班族中短线专属战法 — 4种入场策略代码化
基于 data/strategy_office.md 第6章 代码化条件速查表

每个函数按战法规定的IF条件逐条检查, 返回结构统一:
    {"signal": bool, "score": int, "reason": str}
"""
import logging
logger = logging.getLogger("aurora.office_battle")


def check_mgp(stock: dict, daily: dict, morning_data: dict) -> dict:
    """
    战法1: 早盘跳空突破 (Morning Gapper)
    适用: 09:30-10:00, 蓝筹跳空高开+均线多头+量比放大
    信号权重: momentum_breakout(2.0), chan_buy3(0.5)
    """
    # ── 时间窗口检查 ──
    t = morning_data.get("time", "")
    time_ok = "09:30" <= t <= "10:00" if t else False
    if not time_ok:
        return {"signal": False, "score": 0, "reason": "非早盘窗口(09:30-10:00)"}

    # ── 跳空幅度 ──
    gap = morning_data.get("gap_pct", 0)
    if gap <= 1.5:
        return {"signal": False, "score": 0, "reason": f"跳空不足1.5% (实际{gap:.2f}%)"}

    # ── 均线多头排列 ──
    ma5 = daily.get("ma5", 0)
    ma10 = daily.get("ma10", 0)
    ma20 = daily.get("ma20", 0)
    ma60 = daily.get("ma60", 0)
    if not (ma5 > ma10 > ma20):
        return {"signal": False, "score": 0,
                "reason": f"均线非多头排列: ma5={ma5:.2f} ma10={ma10:.2f} ma20={ma20:.2f}"}
    # ma20 > ma60 或走平上翘
    if not (ma20 > ma60 or abs(ma20 - ma60) < 0.02 * ma60):
        return {"signal": False, "score": 0, "reason": "ma20未站在ma60之上或附近"}

    # ── 量比 ──
    vol_ratio = morning_data.get("vol_ratio", 0)
    if vol_ratio <= 1.5:
        return {"signal": False, "score": 0, "reason": f"量比不足1.5 (实际{vol_ratio:.2f})"}

    # ── 昨日收盘在ma5之上 ──
    close = daily.get("close", 0)
    if close < ma5:
        return {"signal": False, "score": 0, "reason": "昨日收盘未站上ma5"}

    # ── 市值范围 ──
    mcap = stock.get("mcap_yi", stock.get("mcap", 0))  # 亿
    if not (50 <= mcap <= 20000):
        return {"signal": False, "score": 0, "reason": f"市值不在50亿-2万亿区间 ({mcap:.0f}亿)"}

    # ── 计分: 条件越多越强 ──
    score = 65
    if gap > 2.5:
        score += 10
    if vol_ratio > 2.5:
        score += 10
    if ma5 > ma10 > ma20 > ma60:
        score += 10
    score = min(score, 100)

    return {"signal": True, "score": score,
            "reason": f"MGP触发: 跳空{gap:.1f}% 量比{vol_ratio:.1f} 均线多头排列"}


def check_lcp(stock: dict, daily: dict, h60_last_4: list) -> dict:
    """
    战法2: 午间回调确认 (Lunch Confirmation)
    适用: 11:30-12:30, 60分钟回调缩量不破昨日低点
    信号权重: wave_point(1.5), momentum_breakout(1.0)
    """
    if not h60_last_4 or len(h60_last_4) < 4:
        return {"signal": False, "score": 0, "reason": "60分钟K线数据不足4根"}

    # ── 日线在ma20之上 ──
    close_d = daily.get("close", 0)
    ma20_d = daily.get("ma20", 0)
    if close_d <= ma20_d:
        return {"signal": False, "score": 0,
                "reason": f"日线收盘{close_d:.2f}未站上ma20({ma20_d:.2f})"}

    # ── 趋势健康 ──
    adx = daily.get("adx", 0)
    macd = daily.get("macd", 0)
    if not (adx > 25 or macd > 0):
        return {"signal": False, "score": 0,
                "reason": f"趋势不健康: adx={adx:.1f} macd={macd:.2f}"}

    # ── 60分钟均线多头 ──
    last_bar = h60_last_4[-1]
    if last_bar.get("ma5_60", 0) <= last_bar.get("ma20_60", 0):
        return {"signal": False, "score": 0, "reason": "60分钟均线非多头"}

    # ── 回调缩量 ──
    avg_vol = sum(k.get("vol", 0) for k in h60_last_4[:-1]) / max(len(h60_last_4[:-1]), 1)
    if avg_vol <= 0:
        return {"signal": False, "score": 0, "reason": "无法计算60分钟均量"}
    if last_bar.get("vol", 0) >= avg_vol:
        return {"signal": False, "score": 0, "reason": "回调未缩量"}

    # ── 未破昨日低点 ──
    prev_low = daily.get("prev_low", 0)
    if last_bar.get("low", 0) < prev_low:
        return {"signal": False, "score": 0,
                "reason": f"已跌破昨日低点({prev_low:.2f})"}

    # ── 日量达标 ──
    vol_d = daily.get("vol", 0)
    ma5_vol = daily.get("ma5_vol", 0)
    if ma5_vol > 0 and vol_d < 0.8 * ma5_vol:
        return {"signal": False, "score": 0,
                "reason": f"今日量{vol_d:.0f}不足ma5均量的80%({ma5_vol*0.8:.0f})"}

    score = 60
    if adx > 30:
        score += 10
    if last_bar.get("candle_type") in ("doji", "hammer"):
        score += 10
    if vol_d > ma5_vol:
        score += 10
    score = min(score, 100)

    return {"signal": True, "score": score,
            "reason": f"LCP触发: 60分回调缩量+日线趋势健康 adx={adx:.1f}"}


def check_eodm(stock: dict, daily: dict, today_bar: dict, sector: dict) -> dict:
    """
    战法3: 收盘趋势确认 (EOD Momentum)
    适用: 15:00复盘, 次日早盘执行。放量突破未涨停的优质标的
    信号权重: momentum_breakout(2.0), sector_rotation(0.5), chan_buy3(0.5)
    """
    if not today_bar:
        return {"signal": False, "score": 0, "reason": "缺少今日K线数据"}

    # ── 收盘在最高3%以内(非冲高回落) ──
    high = today_bar.get("high", 0)
    close = today_bar.get("close", 0)
    if high > 0 and (high - close) / high > 0.03:
        return {"signal": False, "score": 0, "reason": "冲高回落,收盘不在最高3%内"}

    # ── 实体>1.5% ──
    range_pct = today_bar.get("range_pct", 0)
    if range_pct <= 1.5:
        return {"signal": False, "score": 0, "reason": f"实体涨幅不足1.5% ({range_pct:.2f}%)"}

    # ── 收盘突破ma5 ──
    ma5 = daily.get("ma5", 0)
    if close <= ma5:
        return {"signal": False, "score": 0, "reason": "收盘未突破ma5"}

    # ── 放量但非极端 ──
    vol = today_bar.get("vol", 0)
    ma5_vol = daily.get("ma5_vol", 0)
    if ma5_vol > 0:
        vol_ratio = vol / ma5_vol
        if vol_ratio <= 1.8:
            return {"signal": False, "score": 0, "reason": f"放量不足1.8倍 (实际{vol_ratio:.1f}x)"}
        if vol_ratio >= 3.0:
            return {"signal": False, "score": 0, "reason": f"放量过度≥3.0倍 ({vol_ratio:.1f}x)"}
    else:
        return {"signal": False, "score": 0, "reason": "无法计算均量"}

    # ── 板块检查 ──
    if sector:
        sec_rank = sector.get("rank", 99)
        if sec_rank > 5:
            return {"signal": False, "score": 0, "reason": f"板块排名{sec_rank},不在前5"}
        if sector.get("net_flow", 0) <= 0:
            return {"signal": False, "score": 0, "reason": "板块资金净流入为负"}
    else:
        logger.debug("[EODM] 无板块数据,跳过板块检查")

    # ── 中期趋势 ──
    ma10 = daily.get("ma10", 0)
    ma20 = daily.get("ma20", 0)
    ma60 = daily.get("ma60", 0)

    # 均线向上
    ma5_slope = daily.get("ma5_slope", 0)
    if ma5_slope > 0 and not (ma5 > ma10):
        return {"signal": False, "score": 0, "reason": "ma5斜率向上但ma5<ma10"}
    if close <= ma20:
        return {"signal": False, "score": 0, "reason": "收盘未站上ma20"}

    # 大趋势: 收盘>ma60 或 距离<5%
    if ma60 > 0:
        dist_to_ma60 = (ma60 - close) / ma60 * 100
        if not (close > ma60 or 0 < dist_to_ma60 < 5):
            return {"signal": False, "score": 0,
                    "reason": f"距ma60({ma60:.2f})过远({dist_to_ma60:.1f}%)"}

    score = 65
    if range_pct > 3:
        score += 10
    if vol_ratio > 2.5:
        score += 5
    if sector and sector.get("rank", 99) <= 3:
        score += 10
    score = min(score, 100)

    return {"signal": True, "score": score,
            "reason": f"EODM触发: 涨幅{range_pct:.1f}% 量比{vol_ratio:.1f}x 板块#{sec_rank if sector else 'N/A'}"}


def check_sqb(stock: dict, daily: dict, today_bar: dict) -> dict:
    """
    战法4: 均线粘合突破 (Squeeze Breakout)
    适用: 多周期均线粘合后放量突破上沿, 上班族最易捕捉的中线起涨点
    信号权重: momentum_breakout(2.0)
    """
    if not today_bar:
        return {"signal": False, "score": 0, "reason": "缺少今日K线数据"}

    ma5 = daily.get("ma5", 0)
    ma10 = daily.get("ma10", 0)
    ma20 = daily.get("ma20", 0)

    if not (ma5 > 0 and ma10 > 0 and ma20 > 0):
        return {"signal": False, "score": 0, "reason": "均线数据不完整"}

    # ── 均线间距 < 3% ──
    max_ma = max(ma5, ma10, ma20)
    min_ma = min(ma5, ma10, ma20)
    ma_gap = (max_ma - min_ma) / min_ma * 100
    if ma_gap >= 3.0:
        return {"signal": False, "score": 0,
                "reason": f"均线间距{ma_gap:.2f}% ≥3%,未粘合"}

    # ── 粘合持续天数 ──
    squeeze_days = daily.get("squeeze_days", 0)
    if squeeze_days < 5:
        return {"signal": False, "score": 0,
                "reason": f"粘合仅{squeeze_days}天,不足5天"}

    # ── 布林带宽压缩 ──
    bw_pct = daily.get("bollinger_width_pct", 100)
    bw_min = daily.get("bollinger_20day_min", 0)
    if bw_min > 0 and bw_pct > bw_min * 1.3:
        return {"signal": False, "score": 0, "reason": "布林带未充分压缩"}

    # ── 突破上沿+0.5% ──
    close = today_bar.get("close", 0)
    if close <= max_ma * 1.005:
        return {"signal": False, "score": 0,
                "reason": f"收盘{close:.2f}未突破均线上沿{max_ma*1.005:.2f}"}

    # ── 放量 ──
    vol = today_bar.get("vol", 0)
    ma5_vol = daily.get("ma5_vol", 0)
    if ma5_vol > 0:
        vol_ratio = vol / ma5_vol
        if vol_ratio <= 1.5:
            return {"signal": False, "score": 0,
                    "reason": f"量比{vol_ratio:.1f} ≤1.5,放量不足"}
    else:
        return {"signal": False, "score": 0, "reason": "无法计算均量"}

    # ── 涨幅>2% ──
    range_pct = today_bar.get("range_pct", 0)
    if range_pct <= 2.0:
        return {"signal": False, "score": 0, "reason": f"当日涨幅{range_pct:.1f}% ≤2%"}

    # ── ADX确认 ──
    adx = daily.get("adx", 0)
    di_plus = daily.get("di_plus", 0)
    di_minus = daily.get("di_minus", 0)
    if not (adx > 20 and di_plus > di_minus):
        return {"signal": False, "score": 0,
                "reason": f"ADX={adx:.1f} +DI={di_plus:.1f} -DI={di_minus:.1f} 趋势未确认"}

    score = 70
    if ma_gap < 1.5:
        score += 10
    if squeeze_days >= 10:
        score += 10
    if range_pct > 3.5:
        score += 5
    score = min(score, 100)

    return {"signal": True, "score": score,
            "reason": f"SQB触发: 间距{ma_gap:.2f}% 粘合{squeeze_days}天 涨幅{range_pct:.1f}% 量比{vol_ratio:.1f}x"}
