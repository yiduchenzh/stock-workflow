"""测试数据夹具 — 自动下载真实K线数据并缓存
首次运行会从腾讯API拉取数据，之后从本地缓存读取(1天内不过期)
覆盖3只代表不同特性的股票:
  - 600519: 贵州茅台 (高价蓝筹)
  - 000001: 平安银行 (低价蓝筹)
  - 300059: 东方财富 (成长股)"""
import os, json, time, logging
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd

logger = logging.getLogger("test.fixtures")

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "test_cache"
CACHE_TTL_HOURS = 24  # 缓存有效期24小时

TEST_CODES = {
    "600519": "贵州茅台",
    "000001": "平安银行",
    "300059": "东方财富",
}

def _cache_path(code):
    return CACHE_DIR / f"{code}.json"

def _is_cache_valid(code):
    """检查缓存是否在有效期内"""
    path = _cache_path(code)
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return (datetime.now() - mtime) < timedelta(hours=CACHE_TTL_HOURS)

def _load_from_cache(code):
    """从缓存加载K线数据"""
    path = _cache_path(code)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if not data:
            return None
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception as e:
        logger.warning(f"Cache load failed for {code}: {e}")
        return None

def _save_to_cache(code, df):
    """保存K线数据到缓存"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    records = df.to_dict("records")
    _cache_path(code).write_text(
        json.dumps(records, indent=2, default=str, ensure_ascii=False)
    )
    logger.info(f"Cached {len(records)} rows for {code}")

def load_real_kline(code, days=250):
    """加载真实K线数据（优先缓存，缓存过期则重拉）"""
    df = _load_from_cache(code) if _is_cache_valid(code) else None
    if df is not None and len(df) >= days:
        return df.tail(days).reset_index(drop=True)

    # 从数据源拉取
    try:
        from data.sources import get_kline
        df = get_kline(code, days + 50)  # 多拉一些确保有足够数据
        if df is not None and not df.empty:
            _save_to_cache(code, df)
            return df.tail(days).reset_index(drop=True)
    except Exception as e:
        logger.warning(f"Failed to fetch {code}: {e}")

    return None

def load_all_test_data(days=250):
    """加载所有测试股票的K线数据"""
    result = {}
    for code, name in TEST_CODES.items():
        df = load_real_kline(code, days)
        if df is not None:
            result[code] = {"name": name, "kline": df}
            logger.info(f"Loaded {code} {name}: {len(df)} rows")
        else:
            logger.warning(f"Failed to load {code} {name}")
    return result

def get_market_index(days=300):
    """加载大盘指数数据(上证)用于市场状态判断"""
    return load_real_kline("000001", days)

def clean_cache():
    """清除测试数据缓存"""
    for f in CACHE_DIR.glob("*.json"):
        f.unlink()
    logger.info("Test cache cleaned")

__all__ = [
    "load_real_kline", "load_all_test_data",
    "get_market_index", "clean_cache",
    "TEST_CODES", "CACHE_DIR",
]