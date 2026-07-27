"""
[Soul] 事件驱动信号 — 涨停强度/回购信号/低估信号/业绩窗口
- check_limit_up_strength(code, quote): 封单比+涨停强度
- check_buyback_opportunity(code): 回购信号(用PE+PB代理)
- check_undervaluation(code): 破净/低估值信号
- check_earnings_momentum(code, score): 业绩预告窗口效应
- enrich_candidates(candidates, quotes): 为候选股批量注入事件信号
- 所有数据从腾讯API实时获取,无外部依赖
"""
import logging, urllib.request
from datetime import datetime

logger = logging.getLogger("aurora.soul.event_signals")

UA = "Mozilla/5.0"

# ─── 腾讯API辅助 ───

def _get_tencent_quote(code: str) -> dict:
    """获取单只股票腾讯实时行情
    
    返回: {code, name, price, change_pct, pe, pb, mcap, turnover, vol_ratio}
    """
    try:
        pfx = f"sh{code}" if code.startswith(("6", "9")) else f"sz{code}"
        url = f"https://qt.gtimg.cn/q={pfx}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        resp = urllib.request.urlopen(req, timeout=8)
        raw = resp.read().decode("gbk", errors="replace")
        if "~" not in raw:
            return {}
        parts = raw.split("~")
        if len(parts) < 53:
            return {}
        return {
            "code": code,
            "name": parts[1],
            "price": float(parts[3]) if parts[3] else 0,
            "change_pct": float(parts[32]) if parts[32] else 0,
            "pe": float(parts[39]) if parts[39] else 0,
            "pb": float(parts[46]) if parts[46] else 0,
            "mcap": float(parts[44]) if parts[44] else 0,
            "turnover": float(parts[38]) if parts[38] else 0,
            "vol_ratio": float(parts[49]) if parts[49] else 0,
            "high": float(parts[33]) if parts[33] else 0,
            "low": float(parts[34]) if parts[34] else 0,
            "open": float(parts[5]) if parts[5] else 0,
            "pre_close": float(parts[4]) if parts[4] else 0,
        }
    except Exception as e:
        logger.debug(f"[Soul] 腾讯行情获取失败 {code}: {e}")
        return {}


def _get_tencent_kline(code: str, days: int = 30) -> list:
    """获取腾讯日K线数据(最近days天)
    
    返回: [{date, open, close, high, low, volume}, ...]
    """
    try:
        pfx = f"sh{code}" if code.startswith(("6", "9")) else f"sz{code}"
        url = f"https://ifzq.gtimg.cn/appstock/app/fqkline/get?param={pfx},day,,,{days},qfq"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        resp = urllib.request.urlopen(req, timeout=8)
        data = resp.read().decode("utf-8", errors="replace")
        import json as _json
        parsed = _json.loads(data)
        raw_bars = parsed.get("data", {}).get(pfx, {}).get("qfqday", [])
        if not raw_bars:
            raw_bars = parsed.get("data", {}).get(pfx, {}).get("day", [])
        result = []
        for d in raw_bars:
            if len(d) >= 6:
                result.append({
                    "date": str(d[0]),
                    "open": float(d[1]),
                    "close": float(d[2]),
                    "high": float(d[3]),
                    "low": float(d[4]),
                    "volume": float(d[5]),
                })
        return result
    except Exception as e:
        logger.debug(f"[Soul] K线获取失败 {code}: {e}")
        return []


# ─── 事件信号函数 ───

def check_limit_up_strength(code: str, quote: dict = None) -> dict:
    """检测涨停封板强度
    
    基于腾讯实时行情判断:
      - 当前涨幅>=9.5%视为涨停
      - 使用量比(vol_ratio)近似封板强度:
        - 缩量涨停(vol_ratio<0.7): 强封板+40
        - 温和涨停(0.7-1.0): 较强+30
        - 微放量(1.0-1.5): 一般+20
        - 放量涨停(>=1.5): 存疑+10
    
    返回: {
        "is_limit_up": bool,
        "strength": "strong"/"normal"/"weak",
        "score": 0-40,
        "details": {}
    }
    """
    result = {"is_limit_up": False, "strength": "normal", "score": 0, "details": {}}
    try:
        if quote is None:
            quote = _get_tencent_quote(code)
        if not quote:
            return result

        change_pct = quote.get("change_pct", 0)
        result["details"]["change_pct"] = change_pct

        if change_pct < 9.5:
            return result

        result["is_limit_up"] = True
        vol_ratio = quote.get("vol_ratio", 0)
        result["details"]["vol_ratio"] = vol_ratio

        if vol_ratio < 0.7:
            result["strength"] = "strong"
            result["score"] = 40
            result["details"]["reason"] = "缩量涨停,封板强"
        elif vol_ratio < 1.0:
            result["strength"] = "strong"
            result["score"] = 30
            result["details"]["reason"] = "温和涨停,封板较强"
        elif vol_ratio < 1.5:
            result["strength"] = "normal"
            result["score"] = 20
            result["details"]["reason"] = "微放量涨停,封板一般"
        else:
            result["strength"] = "weak"
            result["score"] = 10
            result["details"]["reason"] = "放量涨停,封板存疑"

        logger.info(f"[Soul] check_limit_up_strength({code}): score={result['score']} "
                     f"strength={result['strength']} reason={result['details'].get('reason','')}")
        return result

    except Exception as e:
        logger.warning(f"[Soul] check_limit_up_strength({code}) 异常: {e}")
        return result


def check_buyback_opportunity(code: str) -> dict:
    """检测回购/超跌机会
    
    使用腾讯实时PE+PB+近期跌幅判断:
      - 近20日跌幅>15% => 超跌信号+20
      - PB<1.5 => 低估值+15
      - 近20日跌幅>10% 且 PB<1 => 双重信号+20
      - PE<15且PE>0 => 低PE+10
    
    返回: {
        "score": 0-65,
        "signals": [str],
        "details": {}
    }
    """
    result = {"score": 0, "signals": [], "details": {}}
    try:
        quote = _get_tencent_quote(code)
        if not quote:
            return result

        pe = quote.get("pe", 0)
        pb = quote.get("pb", 0)
        result["details"]["pe"] = pe
        result["details"]["pb"] = pb

        # 获取K线计算跌幅
        kline = _get_tencent_kline(code, 30)
        if len(kline) >= 20:
            c20 = kline[-20]["close"] if len(kline) >= 20 else kline[0]["close"]
            c1 = kline[-1]["close"]
            recent_return = (c1 - c20) / c20 * 100 if c20 > 0 else 0
            result["details"]["recent_20d_return"] = round(recent_return, 2)

            if recent_return < -15:
                result["score"] += 20
                result["signals"].append(f"超跌{recent_return:.1f}%")

            if pb > 0 and pb < 1.5:
                result["score"] += 15
                result["signals"].append(f"低PB({pb:.2f})")

            if recent_return < -10 and 0 < pb < 1.0:
                result["score"] += 20
                result["signals"].append("超跌+破净双重信号")
        else:
            # 只有行情数据,用PB近似
            if pb > 0 and pb < 1.5:
                result["score"] += 15
                result["signals"].append(f"低PB({pb:.2f})")

        # PE评分
        if 0 < pe < 15:
            result["score"] += 10
            result["signals"].append(f"低PE({pe:.1f})")

        result["score"] = min(result["score"], 65)

        if result["signals"]:
            logger.info(f"[Soul] check_buyback_opportunity({code}): score={result['score']} "
                         f"signals={'; '.join(result['signals'])}")
        return result

    except Exception as e:
        logger.warning(f"[Soul] check_buyback_opportunity({code}) 异常: {e}")
        return result


def check_undervaluation(code: str) -> dict:
    """检测低估/破净信号
    
    基于腾讯实时PB:
      - PB<1: 破净+30
      - PB<0.8: 深度破净+20(叠加)
      - PB<0.6: 极度破净+20(叠加)
      - PE>0且PE<10: 极低PE+15
      - PE>0且PE<15: 低PE+10
      - 高股息率(用PB<1且PE<12近似): +10
    
    返回: {
        "score": 0-100,
        "signals": [str],
        "is_undervalued": bool,
        "details": {}
    }
    """
    result = {"score": 0, "signals": [], "is_undervalued": False, "details": {}}
    try:
        quote = _get_tencent_quote(code)
        if not quote:
            return result

        pb = quote.get("pb", 0)
        pe = quote.get("pe", 0)
        result["details"]["pb"] = pb
        result["details"]["pe"] = pe

        # 破净信号
        if pb > 0 and pb < 1.0:
            result["score"] += 30
            result["signals"].append(f"破净(PB={pb:.2f})")
            if pb < 0.8:
                result["score"] += 20
                result["signals"].append(f"深度破净(PB={pb:.2f})")
            if pb < 0.6:
                result["score"] += 20
                result["signals"].append(f"极度破净(PB={pb:.2f})")

        # 低PE信号
        if pe > 0 and pe < 10:
            result["score"] += 15
            result["signals"].append(f"极低PE({pe:.1f})")
        elif pe > 0 and pe < 15:
            result["score"] += 10
            result["signals"].append(f"低PE({pe:.1f})")

        # 高股息近似(破净+低PE)
        if 0 < pb < 1 and 0 < pe < 12:
            result["score"] += 10
            result["signals"].append("高股息潜力")

        result["score"] = min(result["score"], 100)
        result["is_undervalued"] = result["score"] >= 40

        if result["signals"]:
            logger.info(f"[Soul] check_undervaluation({code}): score={result['score']} "
                         f"undervalued={result['is_undervalued']}")
        return result

    except Exception as e:
        logger.warning(f"[Soul] check_undervaluation({code}) 异常: {e}")
        return result


def check_earnings_momentum(code: str, score: float = None) -> dict:
    """检测业绩预告窗口效应
    
    基于近期涨跌幅和估值判断业绩动量:
      - 近10日涨幅>10% => 可能有利好预期+20
      - 近10日涨幅>5% => 温和走强+10
      - PE>0且PE<20 => 估值合理有空间+10
      - 近10日量比>1.5 => 资金关注+10
      - 如果score参数传入,结合综合评分加权
    
    返回: {
        "score": 0-50,
        "window_active": bool,
        "signals": [str],
        "details": {}
    }
    """
    result = {"score": 0, "window_active": False, "signals": [], "details": {}}
    try:
        quote = _get_tencent_quote(code)
        if not quote:
            return result

        kline = _get_tencent_kline(code, 15)
        pe = quote.get("pe", 0)
        vol_ratio = quote.get("vol_ratio", 0)
        change_pct = quote.get("change_pct", 0)

        result["details"]["pe"] = pe
        result["details"]["vol_ratio"] = vol_ratio

        # 近期涨幅
        if len(kline) >= 10:
            c10 = kline[-10]["close"]
            c1 = kline[-1]["close"]
            ret_10d = (c1 - c10) / c10 * 100 if c10 > 0 else 0
            result["details"]["recent_10d_return"] = round(ret_10d, 2)

            if ret_10d > 10:
                result["score"] += 20
                result["signals"].append(f"近10日涨{ret_10d:.1f}%")
            elif ret_10d > 5:
                result["score"] += 10
                result["signals"].append(f"近10日涨{ret_10d:.1f}%")

        # 估值合理
        if 0 < pe < 20:
            result["score"] += 10
            result["signals"].append(f"PE合理({pe:.1f})")

        # 放量关注
        if vol_ratio > 1.5:
            result["score"] += 10
            result["signals"].append(f"放量(量比{vol_ratio:.2f})")

        # 当日强势
        if change_pct > 3:
            result["score"] += 10
            result["signals"].append(f"当日强势({change_pct:+.2f}%)")

        result["score"] = min(result["score"], 50)

        # 如果传入了外部评分,融合
        if score is not None:
            combined = result["score"] * 0.4 + score * 0.6
            result["combined_score"] = round(combined, 1)
            result["window_active"] = combined >= 40
        else:
            result["window_active"] = result["score"] >= 25

        if result["signals"]:
            logger.info(f"[Soul] check_earnings_momentum({code}): score={result['score']} "
                         f"active={result['window_active']}")
        return result

    except Exception as e:
        logger.warning(f"[Soul] check_earnings_momentum({code}) 异常: {e}")
        return result


# ─── 批量处理 ───

def enrich_candidates(candidates: list, quotes: dict = None) -> list:
    """为候选股批量注入事件信号
    
    每个候选股增加字段:
      - event_limit_up: 涨停强度结果dict
      - event_buyback: 回购信号结果dict
      - event_undervaluation: 低估信号结果dict
      - event_earnings: 业绩窗口结果dict
      - event_total_score: 综合事件评分(0-100)
    
    Args:
        candidates: 候选股列表,每个包含code字段
        quotes: 预获取的行情dict, code→quote, None则自动获取
    
    Returns:
        增强后的候选股列表
    """
    if not candidates:
        return []

    for c in candidates:
        code = c.get("code", "")
        if not code:
            continue

        base_score = c.get("best_score", c.get("score", 50))
        quote = quotes.get(code) if quotes else None

        try:
            lu = check_limit_up_strength(code, quote)
            c["event_limit_up"] = lu
        except Exception as e:
            logger.debug(f"[Soul] enrich limit_up {code}: {e}")
            c["event_limit_up"] = {"score": 0}

        try:
            bo = check_buyback_opportunity(code)
            c["event_buyback"] = bo
        except Exception as e:
            logger.debug(f"[Soul] enrich buyback {code}: {e}")
            c["event_buyback"] = {"score": 0}

        try:
            uv = check_undervaluation(code)
            c["event_undervaluation"] = uv
        except Exception as e:
            logger.debug(f"[Soul] enrich undervaluation {code}: {e}")
            c["event_undervaluation"] = {"score": 0}

        try:
            em = check_earnings_momentum(code, base_score)
            c["event_earnings"] = em
        except Exception as e:
            logger.debug(f"[Soul] enrich earnings {code}: {e}")
            c["event_earnings"] = {"score": 0}

        # 综合事件评分: 涨停强度(0.3)+回购(0.2)+低估(0.3)+业绩(0.2)
        total = (
            c["event_limit_up"].get("score", 0) * 0.3
            + c["event_buyback"].get("score", 0) * 0.2
            + c["event_undervaluation"].get("score", 0) * 0.3
            + c["event_earnings"].get("score", 0) * 0.2
        )
        c["event_total_score"] = round(total, 1)

        if total > 20:
            logger.info(f"[Soul] event_score({code}): {total:.1f} "
                         f"(lu={c['event_limit_up'].get('score',0)} "
                         f"bo={c['event_buyback'].get('score',0)} "
                         f"uv={c['event_undervaluation'].get('score',0)} "
                         f"em={c['event_earnings'].get('score',0)})")

    return candidates
