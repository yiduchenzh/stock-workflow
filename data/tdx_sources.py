"""
TDX Data Source Adapter — wraps TDXDataFetcher (tdxapi) to match sources.py interface.
纯TCP直连通达信行情服务器，不依赖通达信客户端，不依赖腾讯HTTP API。
"""

import sys, os, time, logging
from pathlib import Path

# 确保项目根和 tdxapi 在路径中
_PROJ = Path(__file__).resolve().parent.parent
if str(_PROJ) not in sys.path:
    sys.path.insert(0, str(_PROJ))

import pandas as pd

logger = logging.getLogger(__name__)

# === 全局客户端(懒加载) ===
_tdx_client = None
_tdx_available = True  # 设为False当TDX服务器不可达时降级

def _get_client():
    """懒加载TDX客户端，单例复用"""
    global _tdx_client, _tdx_available
    if not _tdx_available:
        return None
    if _tdx_client is not None:
        return _tdx_client

    try:
        from data.tdxapi import TdxClient
        _tdx_client = TdxClient()
        _tdx_client.connect()
        logger.info("[TDX] Client connected to TDX server")
        return _tdx_client
    except Exception as e:
        logger.warning(f"[TDX] Connection failed: {e}, falling back to Tencent HTTP")
        _tdx_available = False
        return None


def _code_to_market(code: str) -> tuple:
    """Convert stock code to (market_int, market_str, raw_code)"""
    code = str(code).zfill(6)
    if code.startswith(("6", "9")):
        return (1, "SH", code)  # 上海
    elif code.startswith(("0", "3", "2")):
        return (0, "SZ", code)  # 深圳
    elif code.startswith(("8", "4")):
        return (2, "BJ", code)  # 北京
    return (1, "SH", code)

def _code_to_market_tuple(code: str) -> tuple:
    """get_quotes用: (market_int, raw_code) 2元组"""
    mk, _, raw = _code_to_market(code)
    return (mk, raw)


# === 行情接口 (对应 get_tencent_quotes) ===

def get_tdx_quotes(codes: list) -> dict:
    """批量获取实时行情 — TDX TCP直连，返回格式兼容 sources.py"""
    client = _get_client()
    if not client:
        return {}

    result = {}
    stocks = [_code_to_market_tuple(c) for c in codes]

    try:
        quotes = client.get_quotes(stocks)
        for q in quotes:
            if q is None:
                continue
            code = q.code if hasattr(q, "code") else ""
            if not code:
                continue
            # 去掉市场前缀 (SH/SZ)
            raw_code = code.replace("SH", "").replace("SZ", "").replace("BJ", "")
            # TDX协议提供基础价格量数据，PE/市值等丰富字段需WZ/Tencent补充
            price = float(getattr(q, "price", 0) or 0)
            last_close = float(getattr(q, "last_close", 0) or 0)
            result[raw_code] = {
                "code": raw_code,
                "name": getattr(q, "name", ""),
                "price": price,
                "open": float(getattr(q, "open", 0) or 0),
                "high": float(getattr(q, "high", 0) or 0),
                "low": float(getattr(q, "low", 0) or 0),
                "volume": int(getattr(q, "volume", 0) or 0),
                "amount": float(getattr(q, "amount", 0) or 0),
                "change_pct": round((price - last_close) / last_close * 100, 2) if last_close > 0 else 0,
                "pe": 0, "mcap": 0, "turnover": 0, "vol_ratio": 0, "pb": 0,
                "_source": "tdx",
            }
        logger.info(f"[TDX] {len(result)}/{len(codes)} quotes")
    except Exception as e:
        logger.warning(f"[TDX] get_quotes failed: {e}")

    return result


# === K线接口 (对应 get_kline) ===

_TDX_PERIOD_MAP = {
    "1min": "1min", "5min": "5min", "15min": "15min", "30min": "30min",
    "60min": "60min", "day": "1d", "week": "1w", "month": "1m", "year": "1y",
}


def get_tdx_kline(code: str, days: int = 500, period: str = "day") -> pd.DataFrame:
    """获取历史K线 — TDX TCP直连，返回DataFrame格式兼容 sources.py"""
    client = _get_client()
    if not client:
        return pd.DataFrame()

    _, market_str, raw_code = _code_to_market(code)
    tdx_period = _TDX_PERIOD_MAP.get(period, "1d")

    try:
        bars = client.get_bars(raw_code, market_str, tdx_period, count=days)
        if not bars:
            logger.debug(f"[TDX] No bars for {code}")
            return pd.DataFrame()

        rows = []
        for b in bars:
            rows.append({
                "date": str(getattr(b, "date", "")),
                "open": float(getattr(b, "open", 0) or 0),
                "close": float(getattr(b, "close", 0) or 0),
                "high": float(getattr(b, "high", 0) or 0),
                "low": float(getattr(b, "low", 0) or 0),
                "volume": float(getattr(b, "volume", 0) or 0),
            })
        df = pd.DataFrame(rows)
        if not df.empty:
            df["date"] = df["date"].astype(str)
        logger.debug(f"[TDX] K-line {code} {period}: {len(df)} bars")
        return df
    except Exception as e:
        logger.warning(f"[TDX] get_bars failed for {code}: {e}")
        return pd.DataFrame()


def get_tdx_kline_period(code: str, period: str = "day", days: int = 250) -> pd.DataFrame:
    """获取分钟/日K线 — 对应 get_kline_period()"""
    return get_tdx_kline(code, days=days, period=period)


# === 股票列表 (对应 get_real_stock_list) ===

def get_tdx_stock_list() -> list:
    """获取沪深全市场股票列表"""
    client = _get_client()
    if not client:
        return _fallback_stock_list()

    codes = []
    try:
        # 上海
        try:
            sh_list = client.get_security_list("SH")
            for s in sh_list:
                c = getattr(s, "code", "") or ""
                c = c.replace("SH", "").replace("SZ", "")
                if c and len(c) == 6 and c[0] in "69":
                    codes.append(c)
        except Exception:
            pass

        # 深圳
        try:
            sz_list = client.get_security_list("SZ")
            for s in sz_list:
                c = getattr(s, "code", "") or ""
                c = c.replace("SH", "").replace("SZ", "")
                if c and len(c) == 6 and c[0] in "023":
                    codes.append(c)
        except Exception:
            pass

        logger.info(f"[TDX] Stock list: {len(codes)} stocks")
    except Exception as e:
        logger.warning(f"[TDX] Stock list failed: {e}")

    return codes if codes else _fallback_stock_list()


def _fallback_stock_list() -> list:
    """备用股票列表—从东方财富获取"""
    try:
        from data.sources import _sina_stock_list
        return _sina_stock_list()
    except Exception:
        return []


# === 指数行情 ===

def get_tdx_index_snapshot(codes: list) -> dict:
    """获取指数快照"""
    client = _get_client()
    if not client:
        return {}

    result = {}
    try:
        for code in codes:
            try:
                q = client.get_index_quote(code)
                if q:
                    result[code] = {
                        "code": code,
                        "name": getattr(q, "name", ""),
                        "price": float(getattr(q, "price", 0) or 0),
                        "change_pct": float(getattr(q, "change_pct", 0) or 0),
                    }
            except Exception:
                continue
        logger.debug(f"[TDX] Index snapshot: {len(result)} indices")
    except Exception as e:
        logger.warning(f"[TDX] Index snapshot failed: {e}")

    return result


# === 状态检查 ===

def is_tdx_available() -> bool:
    """检查TDX是否可用"""
    return _tdx_available and _get_client() is not None


def close_tdx():
    """关闭TDX连接"""
    global _tdx_client
    if _tdx_client:
        try:
            _tdx_client.close()
        except Exception:
            pass
        _tdx_client = None


# === quick test ===
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing TDX sources...")
    quotes = get_tdx_quotes(["600519", "000001"])
    print(f"Quotes: {len(quotes)} stocks")
    for k, v in list(quotes.items())[:2]:
        print(f"  {k} {v.get('name')}: {v.get('price')}")

    kline = get_tdx_kline("600519", days=10)
    print(f"K-line: {len(kline)} bars")
    if not kline.empty:
        print(kline.tail(3))

    close_tdx()
