from .cache import TdxCache
from .network.client import TdxClient
from .async_client import AsyncTdxClient, BatchResult
from .connection_pool import TdxConnectionPool, PooledClient, PoolStats
from .models import StockQuote, Bar, Tick
from .protocol.constants import Market
from .subscription import (
    QuoteSubscription,
    MultiQuoteSubscription,
    SubscriptionConfig,
    SubscriptionStats,
)
from .bulk_download import (
    BulkDownloader,
    DownloadProgress,
    DateRangeHelper,
    download_all_stocks_bars,
)
from .advanced import (
    # DataFrame conversion
    DataFrameConverter,
    # Screener
    FilterOperator,
    FilterCondition,
    ScreenerRule,
    StockScreener,
    # Alert system
    AlertType,
    Alert,
    AlertResult,
    AlertSystem,
    # Helper functions
    create_price_alert,
    create_ma_cross_alert,
    create_macd_cross_alert,
    create_kdj_cross_alert,
    detect_cross,
)

__version__ = "0.2.0"
__all__ = [
    "TdxClient",
    "AsyncTdxClient",
    "BatchResult",
    "TdxCache",
    "TdxConnectionPool",
    "PooledClient",
    "PoolStats",
    "StockQuote",
    "Bar",
    "Tick",
    "Market",
    "QuoteSubscription",
    "MultiQuoteSubscription",
    "SubscriptionConfig",
    "SubscriptionStats",
    "BulkDownloader",
    "DownloadProgress",
    "DateRangeHelper",
    "download_all_stocks_bars",
    # Advanced features
    "DataFrameConverter",
    "FilterOperator",
    "FilterCondition",
    "ScreenerRule",
    "StockScreener",
    "AlertType",
    "Alert",
    "AlertResult",
    "AlertSystem",
    "create_price_alert",
    "create_ma_cross_alert",
    "create_macd_cross_alert",
    "create_kdj_cross_alert",
    "detect_cross",
]

# Export functions loaded on demand
# from .export import to_dataframe, to_parquet, to_csv, to_excel, read_parquet
