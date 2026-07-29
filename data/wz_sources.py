"""WZ歪枣网数据源 — ⚠️ 已弃用 (2026-07-28)
所有功能已迁移到:
- data.sources (腾讯+TDX TCP)
- data.fallback_sources (同花顺北向+东财板块+同花顺热点)
- data.financial_sources (mootdx财务+新浪财报三表+东财基本面)
"""
import logging
logger = logging.getLogger("aurora.wz")

logger.warning("WZ sources disabled — use data.sources / data.fallback_sources instead")


def _parse(r):
    """已弃用"""
    import pandas as pd
    return pd.DataFrame()


def get_quotes(codes):
    """已弃用"""
    return {}


def get_klines(code, days=60):
    """已弃用"""
    import pandas as pd
    return pd.DataFrame()


def get_sector_ranking(top_n=50):
    """已弃用 — 使用 data.sources.get_sector_ranking()"""
    return []


def get_northbound_flow():
    """已弃用 — 使用 data.fallback_sources.get_northbound_minute()"""
    return {}


def get_market_breadth():
    """已弃用 — 使用 data.sources.get_market_breadth()"""
    return {}
