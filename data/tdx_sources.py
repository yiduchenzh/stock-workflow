"""
TDX 数据源 — mootdx TCP直连 (2026-07-28 替换自定义tdxapi)
══════════════════════════════════════════════════════════
使用 mootdx v0.11.7 替代自研 tdxapi，连接提速 10 倍。

数据源优先级:
  TDX TCP (mootdx, 不封IP) → 腾讯 HTTP (不封IP)

接口兼容 sources.get_kline / get_tencent_quotes 格式.
"""
import logging, time
from pathlib import Path

logger = logging.getLogger("aurora.tdx")

# ── 全局客户端(单例, 懒加载) ──
_CLIENT = None
_CLIENT_TS = 0
_CLIENT_TTL = 300  # 5分钟重连
# v14.43: P1-3 WalkForward并行寻优 — mootdx TCP连接非线程安全, 全局锁串行化
import threading as _threading
_TDX_LOCK = _threading.RLock()


def _get_client():
    """懒加载mootdx客户端，单例复用"""
    global _CLIENT, _CLIENT_TS
    now = time.time()
    if _CLIENT is not None and now - _CLIENT_TS < _CLIENT_TTL:
        return _CLIENT
    try:
        from mootdx.quotes import Quotes
        _CLIENT = Quotes.factory(market='std')
        _CLIENT_TS = now
        logger.info(f"[TDX] mootdx connected ({_CLIENT_TS:.0f})")
        return _CLIENT
    except Exception as e:
        logger.warning(f"[TDX] mootdx连接失败: {e}")
        _CLIENT = None
        return None


# ── K线数据 ──

# 常见指数代码(走index_bars接口)
_INDEX_CODES = {"000001", "000300", "000905", "000852", "399001", "399006",
                "399300", "399005", "399905", "899050"}


def _normalize_tdx_df(df: "pd.DataFrame") -> "pd.DataFrame":
    """标准化mootdx返回的DataFrame:
    1. 去重列(0.11.7返回重复的volume列)
    2. 合成标准date列(优先datetime, 其次year/month/day)
    3. 统一列名 {date, open, close, high, low, volume, amount}
    """
    import pandas as pd

    # 1. 去重列 — 保留第一个
    df = df.loc[:, ~df.columns.duplicated()]

    # 2. 合成date列
    if "date" in df.columns:
        # 防御: 乱码日期(如 "1133-78-45 15:00")直接丢弃该行
        date_raw = df["date"].astype(str)
        mask = date_raw.str.match(r"^\d{4}-\d{2}-\d{2}")
        df = df[mask]
        if df.empty:
            return pd.DataFrame()
        df["date"] = date_raw[mask].str[:10]
    elif "datetime" in df.columns:
        dt_raw = df["datetime"].astype(str)
        mask = dt_raw.str.match(r"^\d{4}-\d{2}-\d{2}")
        df = df[mask]
        if df.empty:
            return pd.DataFrame()
        df["date"] = dt_raw[mask].str[:10]
        df = df.drop(columns=["datetime"])  # 防止rename产生重复date列
    elif {"year", "month", "day"}.issubset(df.columns):
        df["date"] = (df["year"].astype(str) + "-" +
                      df["month"].astype(str).str.zfill(2) + "-" +
                      df["day"].astype(str).str.zfill(2))

    if "date" not in df.columns:
        return pd.DataFrame()

    # 3. 统一列名
    rename_map = {"vol": "volume", "datetime": "date"}
    df = df.rename(columns=rename_map)
    # 删除中间列(year/month/day/hour/minute/up_count/down_count)
    drop_cols = [c for c in ["year", "month", "day", "hour", "minute",
                             "up_count", "down_count", "datetime"] if c in df.columns]
    if drop_cols:
        df = df.drop(columns=drop_cols)
    # rename后再次去重(vol→volume 可能与原 volume 重复)
    df = df.loc[:, ~df.columns.duplicated()]

    keep = ["date", "open", "close", "high", "low", "volume", "amount"]
    for col in keep:
        if col not in df.columns:
            df[col] = 0
    return df[keep].reset_index(drop=True)


def get_tdx_kline(code: str, days: int = 500, period: str = "day") -> "pd.DataFrame":
    """
    获取历史K线 — mootdx TCP直连.
    指数代码(399xxx/000300等)自动走index_bars接口.
    返回DataFrame格式({date, open, close, high, low, volume}), 兼容 sources.py.
    v14.43: RLock包裹 — 多线程(如WF并行寻优)串行化mootdx连接, 防TCP数据串扰
    """
    import pandas as pd
    with _TDX_LOCK:
        return _get_tdx_kline_locked(code, days, period)


def _get_tdx_kline_locked(code: str, days: int, period: str) -> "pd.DataFrame":
    import pandas as pd
    client = _get_client()
    if client is None:
        return pd.DataFrame()

    period_map = {
        "day": 4, "week": 5, "month": 6,
        "1min": 7, "5min": 8, "15min": 9, "30min": 10, "60min": 11,
    }
    category = period_map.get(period, 4)
    is_index = code in _INDEX_CODES or code.startswith("399")

    try:
        if is_index:
            df = client.index_bars(symbol=code, category=category, offset=min(days, 800))
        else:
            df = client.bars(symbol=code, category=category, offset=min(days, 800))
        if df is None or (hasattr(df, 'empty') and df.empty):
            return pd.DataFrame()

        df = _normalize_tdx_df(df)
        logger.debug(f"[TDX] K-line {code} {period}: {len(df)} bars")
        return df
    except Exception as e:
        logger.warning(f"[TDX] get_kline failed for {code}: {e}")
        return pd.DataFrame()


def get_tdx_kline_period(code: str, period: str = "day", days: int = 250) -> "pd.DataFrame":
    """多周期K线兼容接口"""
    return get_tdx_kline(code, days=days, period=period)


# ── 实时行情(含五档盘口) ──

def get_tdx_quotes(codes: list) -> dict:
    """
    批量实时行情 — mootdx TCP.
    返回 {code: {price, open, high, low, last_close, volume, amount, ...}}.
    """
    client = _get_client()
    if client is None:
        return {}

    try:
        quotes_df = client.quotes(symbol=codes)
        if quotes_df is None:
            return {}
        # mootdx返回DataFrame: {code, price, open, high, low, last_close, vol, amount, bid1~5, ask1~5, bid_vol1~5, ...}
        if hasattr(quotes_df, 'empty') and quotes_df.empty:
            return {}

        result = {}
        for _, row in quotes_df.iterrows():
            code = str(row.get("code", ""))
            if not code:
                continue
            code = code.replace("SH", "").replace("SZ", "").replace("BJ", "")
            result[code] = {
                "code": code,
                "name": str(row.get("name", "")),
                "price": float(row.get("price", 0) or 0),
                "open": float(row.get("open", 0) or 0),
                "high": float(row.get("high", 0) or 0),
                "low": float(row.get("low", 0) or 0),
                "last_close": float(row.get("last_close", 0) or 0),
                "volume": int(row.get("vol", 0) or 0),
                "amount": float(row.get("amount", 0) or 0),
            }
        logger.info(f"[TDX] {len(result)}/{len(codes)} quotes")
        return result
    except Exception as e:
        logger.warning(f"[TDX] get_quotes failed: {e}")
        return {}


# ── 股票列表 ──

def get_tdx_stock_list() -> list:
    """全市场股票列表(mootdx)"""
    client = _get_client()
    if client is None:
        return []

    codes = []
    try:
        # mootdx: stocks() 返回全市场股票列表DataFrame
        try:
            stocks_df = client.stocks()
            if stocks_df is not None and hasattr(stocks_df, 'empty') and not stocks_df.empty:
                for _, row in stocks_df.iterrows():
                    c = str(row.get("code", ""))
                    c = c.replace("SH", "").replace("SZ", "").replace("BJ", "")
                    if c and len(c) == 6 and c.isdigit():
                        codes.append(c)
        except Exception:
            pass
        
        if not codes:
            # 备用: stock_all() 接口
            stocks_df = client.stock_all()
            if stocks_df is not None and hasattr(stocks_df, 'empty') and not stocks_df.empty:
                for _, row in stocks_df.iterrows():
                    c = str(row.get("code", ""))
                    c = c.replace("SH", "").replace("SZ", "").replace("BJ", "")
                    if c and len(c) == 6 and c.isdigit():
                        codes.append(c)
        
        logger.info(f"[TDX] Stock list: {len(codes)} stocks")
    except Exception as e:
        logger.warning(f"[TDX] Stock list failed: {e}")

    return codes


# ── 财务数据 ──

def get_tdx_finance(code: str) -> dict:
    """
    mootdx 财务快照(37字段).
    返回 {eps, roe, profit, income, bvps, 总股本, 流通股本, ...}
    """
    client = _get_client()
    if client is None:
        return {}

    try:
        fin = client.finance(symbol=code)
        if fin is None or (hasattr(fin, 'empty') and fin.empty):
            return {}
        # mootdx返回Series或DataFrame
        if hasattr(fin, 'iloc'):
            row = fin.iloc[-1] if len(fin) > 0 else fin
        else:
            row = fin
        result = dict(row)
        logger.debug(f"[TDX] Finance {code}: {len(result)} fields")
        return result
    except Exception as e:
        logger.debug(f"[TDX] Finance {code}: {e}")
        return {}


# ── 逐笔成交 ──

def get_tdx_transactions(code: str, date: str = "") -> list:
    """逐笔成交数据(非交易时间返回空)"""
    client = _get_client()
    if client is None:
        return []
    try:
        trades = client.transaction(symbol=code, date=date)
        if trades is not None and len(trades) > 0:
            return trades.to_dict("records") if hasattr(trades, "to_dict") else list(trades)
    except Exception:
        pass
    return []


# ── 兼容接口 ──

def get_tdx_index_snapshot(codes: list) -> dict:
    """指数快照 — mootdx"""
    # mootdx不直接提供指数接口, 返回空(由腾讯处理)
    return {}
