# XTick 数据源适配器 — Aurora引擎第四级数据源
# 官网: http://www.xtick.top | API: http://api.xtick.top
# 接入文档: https://github.com/xticktop/skills
#
# 安装: pip install requests pandas
# 设置Token:
#   [System.Environment]::SetEnvironmentVariable("XTICK_TOKEN","your_token","User")

import os, json, logging, time
from datetime import datetime, timedelta

logger = logging.getLogger("aurora.xtick")

TOKEN = os.environ.get("XTICK_TOKEN", "")
API_BASE = "http://api.xtick.top/doc"

if not TOKEN:
    logger.debug("XTICK_TOKEN not set, XTick sources disabled")

def _req(endpoint: str, params: dict = None) -> dict:
    """发送请求到XTick API"""
    if not TOKEN:
        return {}
    import requests
    p = params or {}
    p["token"] = TOKEN
    try:
        url = f"{API_BASE}/{endpoint}"
        r = requests.get(url, params=p, timeout=15)
        if r.status_code == 200:
            return r.json()
        logger.warning(f"[XTick] {endpoint} HTTP {r.status_code}: {r.text[:100]}")
        return {}
    except Exception as e:
        logger.warning(f"[XTick] {endpoint} fail: {e}")
        return {}

def get_klines(code: str, days: int = 120, period: str = "1d") -> "pd.DataFrame":
    """获取K线数据 — 与wz_sources.get_klines兼容"""
    import pandas as pd
    end = datetime.now()
    start = end - timedelta(days=days * 2)
    
    period_map = {"1d": "1d", "1w": "1w", "1mon": "1mon", 
                  "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "1h": "1h"}
    p = period_map.get(period, "1d")
    
    data = _req("kline/market", {
        "type": 1, "code": code, "fq": 1,
        "period": p,
        "startDate": start.strftime("%Y-%m-%d"),
        "endDate": end.strftime("%Y-%m-%d"),
    })
    
    if not data or not isinstance(data, list):
        return pd.DataFrame()
    
    df = pd.DataFrame(data)
    # 统一列名
    col_map = {"time": "date", "open": "open", "close": "close", 
               "high": "high", "low": "low", "volume": "volume", "amount": "amount"}
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], unit="ms")
        df = df.sort_values("date").reset_index(drop=True)
    return df.tail(days)

def get_realtime_quotes(codes: list) -> dict:
    """实时行情 — 返回 {code: {price, change_pct, ...}}"""
    result = {}
    for code in codes[:10]:  # XTick单次只支持单只
        data = _req("kline/market", {
            "type": 1, "code": code, "fq": 1,
            "period": "1d",
            "startDate": datetime.now().strftime("%Y-%m-%d"),
            "endDate": datetime.now().strftime("%Y-%m-%d"),
        })
        if data and isinstance(data, list) and len(data) > 0:
            last = data[-1]
            result[code] = {
                "code": code,
                "price": last.get("close", 0),
                "change_pct": ((last.get("close", 0) - last.get("preClose", 1)) 
                               / max(last.get("preClose", 1), 0.01) * 100),
                "volume": last.get("volume", 0),
                "amount": last.get("amount", 0),
            }
    return result

def get_level2(code: str) -> dict:
    """买卖五档盘口（白银版+）"""
    data = _req("fivelevelrealtime", {"type": 1, "code": code})
    if not data:
        return {}
    return data if isinstance(data, dict) else {}

def get_auction(code: str = "all") -> list:
    """集合竞价数据（黄金版+）"""
    data = _req("corebidtime", {"code": code})
    return data if isinstance(data, list) else []

def get_live_day_kline(code: str = "all") -> list:
    """盘中实时日K线（白银版+，支持ALL全市场）"""
    data = _req("dayklinerealtime", {"type": 1, "code": code})
    return data if isinstance(data, list) else []

def get_sector_ranking() -> list:
    """板块排名 — 暂未直接提供，可通过行情数据聚合"""
    return []

def get_financial(code: str, indicator: str = "finance") -> "pd.DataFrame":
    """财务指标（青铜版+）"""
    import pandas as pd
    data = _req("coreindicator", {
        "code": code,
        "startDate": "2023-01-01",
        "endDate": datetime.now().strftime("%Y-%m-%d"),
    })
    if not data or not isinstance(data, list):
        return pd.DataFrame()
    return pd.DataFrame(data)

def get_money_flow(code: str) -> list:
    """资金流向（至尊版+）"""
    data = _req("moneyflow", {"code": code})
    return data if isinstance(data, list) else []

def get_longhubang(start: str = None, end: str = None) -> list:
    """龙虎榜数据（白银版+）"""
    e = end or datetime.now().strftime("%Y-%m-%d")
    s = start or (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    data = _req("longhubang", {"startDate": s, "endDate": e})
    return data if isinstance(data, list) else []

def get_market_emotion() -> dict:
    """市场情绪（至尊版+）"""
    data = _req("marketemotion", {"startDate": datetime.now().strftime("%Y-%m-%d")})
    return data if isinstance(data, dict) else {}

def get_lianban() -> list:
    """连板天梯（至尊版+）"""
    data = _req("lianbantianti", {})
    return data if isinstance(data, list) else []

def get_calendar(code: str = "ssb") -> list:
    """交易日历"""
    data = _req("calendar", {"code": code})
    return data if isinstance(data, list) else []

if __name__ == "__main__":
    # 自测
    logging.basicConfig(level=logging.INFO)
    if not TOKEN:
        print("[SELF-TEST] XTICK_TOKEN not set, skip")
    else:
        print("Testing klines for 000001...")
        df = get_klines("000001", days=5)
        print(f"  Got {len(df)} rows")
        if len(df) > 0:
            print(f"  Columns: {list(df.columns)}")
            print(f"  Last: {df.iloc[-1].to_dict()}")