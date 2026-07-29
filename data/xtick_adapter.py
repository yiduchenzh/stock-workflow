"""
[Soul] XTick Level2 数据适配器 — 预留接口
- 当前返回模拟数据; 接入 XTick 后自动切换
- API 参考: http://api.xtick.top
"""
import logging
import time
import random
from datetime import datetime

logger = logging.getLogger("aurora.soul.xtick_adapter")

# 当此标志为 True 时, 使用真实 XTick 源
_USE_REAL_XTICK = False


def _try_real_xtick():
    """尝试导入真实 XTick 源并检查 token"""
    global _USE_REAL_XTICK
    if _USE_REAL_XTICK:
        return True
    try:
        from data.xtick_sources import TOKEN as _xtick_token
        if _xtick_token:
            _USE_REAL_XTICK = True
            logger.info("[Soul] XTick adapter: 使用真实XTick数据源")
            return True
    except Exception:
        pass
    return False


def _mock_tick(code: str) -> dict:
    """生成模拟 tick 数据"""
    now = datetime.now()
    base_price = 10.0 + hash(code) % 200
    return {
        "code": code,
        "time": now.strftime("%H:%M:%S"),
        "price": round(base_price + random.uniform(-0.5, 0.5), 2),
        "volume": random.randint(100, 10000),
        "amount": round(random.uniform(10000, 500000), 2),
        "direction": random.choice(["buy", "sell", "neutral"]),
        "source": "mock",
    }


def _mock_order_book(code: str) -> dict:
    """生成模拟五档盘口"""
    base_price = 10.0 + hash(code) % 200
    bids, asks = [], []
    for i in range(5):
        bp = round(base_price - (i + 1) * 0.01, 2)
        ap = round(base_price + (i + 1) * 0.01, 2)
        bids.append({"price": bp, "volume": random.randint(1000, 50000)})
        asks.append({"price": ap, "volume": random.randint(1000, 50000)})
    return {
        "code": code,
        "time": datetime.now().strftime("%H:%M:%S"),
        "bids": bids,
        "asks": asks,
        "last_price": base_price,
        "bid_ask_spread": round(0.02, 2),
        "source": "mock",
    }


def _mock_transactions(code: str, count: int = 10) -> list:
    """生成模拟逐笔成交"""
    base_price = 10.0 + hash(code) % 200
    txns = []
    t = time.time()
    for i in range(count):
        direction = random.choice(["buy", "sell"])
        price = round(base_price + random.uniform(-0.3, 0.3), 2)
        vol = random.randint(100, 5000)
        txns.append({
            "code": code,
            "time": datetime.fromtimestamp(t - i * random.uniform(0.5, 3.0)).strftime("%H:%M:%S.%f")[:12],
            "price": price,
            "volume": vol,
            "amount": round(price * vol, 2),
            "direction": direction,
            "source": "mock",
        })
    return txns


def get_tick(code: str) -> dict:
    """
    获取最新 Tick 数据
    Args:
        code: 股票代码, 如 "000001"
    Returns:
        dict: {code, time, price, volume, amount, direction, source}
    """
    try:
        if _try_real_xtick():
            from data.xtick_sources import get_realtime_quotes
            quotes = get_realtime_quotes([code])
            if quotes and code in quotes:
                return {**quotes[code], "source": "xtick"}
        return _mock_tick(code)
    except Exception as e:
        logger.warning(f"[Soul] get_tick({code}) 异常: {e}")
        return _mock_tick(code)


def get_order_book(code: str) -> dict:
    """
    获取五档买卖盘口
    Args:
        code: 股票代码, 如 "000001"
    Returns:
        dict: {code, time, bids:[{price,volume}], asks:[{price,volume}],
               last_price, bid_ask_spread, source}
    """
    try:
        if _try_real_xtick():
            from data.xtick_sources import get_level2
            level2 = get_level2(code)
            if level2 and isinstance(level2, dict) and "bids" in level2:
                return {**level2, "source": "xtick"}
        return _mock_order_book(code)
    except Exception as e:
        logger.warning(f"[Soul] get_order_book({code}) 异常: {e}")
        return _mock_order_book(code)


def get_minute_kline(code: str, period: str = "1m") -> list:
    """
    获取分钟K线
    Args:
        code: 股票代码
        period: 周期, 1m/5m/15m/30m/60m
    Returns:
        list: [{time, open, high, low, close, volume, amount}, ...]
    """
    try:
        if _try_real_xtick():
            from data.xtick_sources import get_klines
            df = get_klines(code, days=5, period=period)
            if not df.empty:
                return df.to_dict("records")
        # fallback 模拟
        now = datetime.now()
        klines = []
        base_price = 10.0 + hash(code) % 200
        for i in range(30):
            o = round(base_price + random.uniform(-0.5, 0.5), 2)
            h = round(o + random.uniform(0, 0.3), 2)
            l_ = round(o - random.uniform(0, 0.3), 2)
            c = round(random.uniform(l_, h), 2)
            klines.append({
                "code": code,
                "time": datetime(now.year, now.month, now.day, 9, 30 + i, 0).strftime("%H:%M"),
                "open": o, "high": h, "low": l_, "close": c,
                "volume": random.randint(10000, 500000),
                "amount": round(random.uniform(50000, 5000000), 2),
                "source": "mock",
            })
        return klines
    except Exception as e:
        logger.warning(f"[Soul] get_minute_kline({code}) 异常: {e}")
        return []


def get_transactions(code: str, count: int = 20) -> list:
    """
    获取逐笔成交数据
    Args:
        code: 股票代码
        count: 返回条数
    Returns:
        list: [{code, time, price, volume, amount, direction}, ...]
    """
    try:
        if _try_real_xtick():
            # XTick 暂未提供逐笔成交API, 使用模拟
            pass
        return _mock_transactions(code, count)
    except Exception as e:
        logger.warning(f"[Soul] get_transactions({code}) 异常: {e}")
        return _mock_transactions(code, count)


def set_real_mode(enabled: bool = True):
    """手动切换为真实XTick模式"""
    global _USE_REAL_XTICK
    _USE_REAL_XTICK = enabled
    logger.info(f"[Soul] XTick adapter: real_mode={'ON' if enabled else 'OFF'}")
