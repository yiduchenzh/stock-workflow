"""
实时行情订阅模块

提供轮询模式的行情订阅功能，支持多股票同时订阅和回调函数注册。
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set, Tuple, Union, Any
from datetime import datetime

from data.tdxapi.async_client import AsyncTdxClient
from data.tdxapi.models import StockQuote


logger = logging.getLogger(__name__)


# 类型别名
QuoteCallback = Callable[[StockQuote], None]
QuotesCallback = Callable[[List[StockQuote]], None]
ErrorCallback = Callable[[Exception, Optional[str]], None]


@dataclass
class SubscriptionConfig:
    """订阅配置"""

    interval: float = 1.0  # 轮询间隔（秒）
    max_retries: int = 3  # 最大重试次数
    retry_delay: float = 0.5  # 重试延迟（秒）
    batch_size: int = 50  # 每批获取的股票数量
    continue_on_error: bool = True  # 遇到错误时是否继续


@dataclass
class SubscriptionStats:
    """订阅统计信息"""

    start_time: Optional[datetime] = None
    stop_time: Optional[datetime] = None
    total_updates: int = 0
    success_count: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    last_update_time: Optional[datetime] = None

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self.start_time is not None and self.stop_time is None

    @property
    def elapsed_seconds(self) -> float:
        """已运行秒数"""
        if self.start_time is None:
            return 0.0
        end = self.stop_time or datetime.now()
        return (end - self.start_time).total_seconds()


class QuoteSubscription:
    """
    实时行情订阅管理器

    使用轮询模式定时获取多只股票实时行情，支持回调函数注册。

    Example:
        ```python
        # 基本用法
        async with AsyncTdxClient() as client:
            sub = QuoteSubscription(client)

            # 注册回调函数
            def on_quote(quote: StockQuote):
                print(f"{quote.code}: {quote.price}")

            sub.register_callback(on_quote)

            # 启动订阅
            await sub.subscribe_quotes(["600519", "000001"], interval=1.0)

            # 运行一段时间后停止
            await asyncio.sleep(60)
            await sub.stop()
        ```
    """

    def __init__(
        self,
        client: AsyncTdxClient,
        config: Optional[SubscriptionConfig] = None,
    ):
        """
        初始化订阅管理器

        Args:
            client: AsyncTdxClient 实例
            config: 订阅配置，None 则使用默认配置
        """
        self._client = client
        self._config = config or SubscriptionConfig()
        self._stats = SubscriptionStats()

        # 订阅状态
        self._codes: Set[str] = set()  # 订阅的股票代码集合
        self._code_market_map: Dict[str, str] = {}  # 代码到市场的映射
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._stop_event: Optional[asyncio.Event] = None

        # 回调函数
        self._quote_callbacks: List[QuoteCallback] = []
        self._quotes_callbacks: List[QuotesCallback] = []
        self._error_callbacks: List[ErrorCallback] = []

        # 变化检测
        self._last_quotes: Dict[str, StockQuote] = {}
        self._price_changed_only: bool = False

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running

    @property
    def stats(self) -> SubscriptionStats:
        """获取统计信息"""
        return self._stats

    @property
    def subscribed_codes(self) -> List[str]:
        """获取已订阅的股票代码列表"""
        return list(self._codes)

    @property
    def config(self) -> SubscriptionConfig:
        """获取当前配置"""
        return self._config

    def register_callback(self, callback: QuoteCallback) -> None:
        """
        注册单条行情回调函数

        Args:
            callback: 回调函数，接收 StockQuote 参数

        Example:
            ```python
            def on_quote(quote: StockQuote):
                print(f"{quote.code}: {quote.price}")

            sub.register_callback(on_quote)
            ```
        """
        self._quote_callbacks.append(callback)

    def register_quotes_callback(self, callback: QuotesCallback) -> None:
        """
        注册批量行情回调函数

        Args:
            callback: 回调函数，接收 List[StockQuote] 参数

        Example:
            ```python
            def on_quotes(quotes: List[StockQuote]):
                for q in quotes:
                    print(f"{q.code}: {q.price}")

            sub.register_quotes_callback(on_quotes)
            ```
        """
        self._quotes_callbacks.append(callback)

    def register_error_callback(self, callback: ErrorCallback) -> None:
        """
        注册错误回调函数

        Args:
            callback: 回调函数，接收 (Exception, code) 参数

        Example:
            ```python
            def on_error(error: Exception, code: Optional[str]):
                print(f"Error for {code}: {error}")

            sub.register_error_callback(on_error)
            ```
        """
        self._error_callbacks.append(callback)

    def unregister_callback(self, callback: Union[QuoteCallback, QuotesCallback, ErrorCallback]) -> bool:
        """
        注销回调函数

        Args:
            callback: 要注销的回调函数

        Returns:
            是否成功找到并移除
        """
        found = False
        if callback in self._quote_callbacks:
            self._quote_callbacks.remove(callback)
            found = True
        if callback in self._quotes_callbacks:
            self._quotes_callbacks.remove(callback)
            found = True
        if callback in self._error_callbacks:
            self._error_callbacks.remove(callback)
            found = True
        return found

    def clear_callbacks(self) -> None:
        """清除所有回调函数"""
        self._quote_callbacks.clear()
        self._quotes_callbacks.clear()
        self._error_callbacks.clear()

    def set_price_changed_only(self, enabled: bool = True) -> None:
        """
        设置是否只在价格变化时触发回调

        Args:
            enabled: True 表示只在价格变化时触发回调
        """
        self._price_changed_only = enabled

    def _parse_code(self, code: str) -> Tuple[int, str]:
        """
        解析股票代码，返回 (market, code)

        Args:
            code: 股票代码，如 "600519" 或 "SH:600519"

        Returns:
            (market_code, code) 元组，market_code: 0=SZ, 1=SH
        """
        if ":" in code:
            market_str, code_str = code.split(":", 1)
            market = 1 if market_str.upper() == "SH" else 0
            return (market, code_str)

        # 自动判断市场
        if code.startswith("6"):
            return (1, code)  # SH
        else:
            return (0, code)  # SZ

    def _code_key(self, market: int, code: str) -> str:
        """生成代码键"""
        market_str = "SH" if market == 1 else "SZ"
        return f"{market_str}:{code}"

    async def subscribe_quotes(
        self,
        codes: List[str],
        interval: Optional[float] = None,
        auto_start: bool = True,
    ) -> None:
        """
        订阅股票实时行情

        Args:
            codes: 股票代码列表，如 ["600519", "SZ:000001"]
            interval: 轮询间隔（秒），None 则使用配置默认值
            auto_start: 是否自动启动订阅

        Example:
            ```python
            # 订阅单只股票
            await sub.subscribe_quotes(["600519"], interval=1.0)

            # 订阅多只股票
            await sub.subscribe_quotes(
                ["600519", "000001", "300001"],
                interval=2.0
            )

            # 显式指定市场
            await sub.subscribe_quotes(["SH:600519", "SZ:000001"])
            ```
        """
        if interval is not None:
            self._config.interval = interval

        # 解析并存储代码
        for code in codes:
            market, code_str = self._parse_code(code)
            key = self._code_key(market, code_str)
            self._codes.add(key)
            self._code_market_map[key] = "SH" if market == 1 else "SZ"

        logger.info(f"已添加 {len(codes)} 只股票到订阅列表，当前共 {len(self._codes)} 只")

        if auto_start and not self._running:
            await self.start()

    async def unsubscribe_quotes(self, codes: List[str]) -> None:
        """
        取消订阅指定股票

        Args:
            codes: 要取消订阅的股票代码列表
        """
        for code in codes:
            market, code_str = self._parse_code(code)
            key = self._code_key(market, code_str)
            self._codes.discard(key)
            self._code_market_map.pop(key, None)
            self._last_quotes.pop(key, None)

        logger.info(f"已移除 {len(codes)} 只股票，当前共 {len(self._codes)} 只")

        # 如果没有股票了，自动停止
        if not self._codes and self._running:
            await self.stop()

    async def start(self) -> None:
        """启动订阅"""
        if self._running:
            logger.warning("订阅已经在运行中")
            return

        if not self._codes:
            raise ValueError("没有订阅任何股票，请先调用 subscribe_quotes")

        self._running = True
        self._stop_event = asyncio.Event()
        self._stats = SubscriptionStats(start_time=datetime.now())

        self._task = asyncio.create_task(self._poll_loop())
        logger.info(f"订阅已启动，轮询间隔: {self._config.interval}s")

    async def stop(self) -> None:
        """停止订阅"""
        if not self._running:
            return

        self._running = False

        if self._stop_event:
            self._stop_event.set()

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None

        self._stats.stop_time = datetime.now()
        logger.info(f"订阅已停止，运行时间: {self._stats.elapsed_seconds:.1f}s")

    async def _poll_loop(self) -> None:
        """轮询主循环"""
        while self._running and not self._stop_event.is_set():
            try:
                await self._fetch_and_notify()
            except Exception as e:
                logger.error(f"轮询循环错误: {e}")
                self._stats.error_count += 1
                self._stats.last_error = str(e)
                self._notify_error(e)

            # 等待下一次轮询
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._config.interval
                )
            except asyncio.TimeoutError:
                # 正常超时，继续下一次轮询
                pass
            except asyncio.CancelledError:
                break

    async def _fetch_and_notify(self) -> None:
        """获取数据并通知回调"""
        if not self._codes:
            return

        # 将代码分批
        code_list = list(self._codes)
        batches = [
            code_list[i:i + self._config.batch_size]
            for i in range(0, len(code_list), self._config.batch_size)
        ]

        all_quotes: List[StockQuote] = []

        for batch in batches:
            quotes = await self._fetch_batch(batch)
            all_quotes.extend(quotes)

        if all_quotes:
            self._stats.total_updates += 1
            self._stats.success_count += len(all_quotes)
            self._stats.last_update_time = datetime.now()
            self._notify_quotes(all_quotes)

    async def _fetch_batch(self, codes: List[str]) -> List[StockQuote]:
        """获取一批股票的行情"""
        stocks: List[Tuple[int, str]] = []
        for key in codes:
            market = 1 if key.startswith("SH:") else 0
            code = key.split(":", 1)[1]
            stocks.append((market, code))

        for attempt in range(self._config.max_retries):
            try:
                quotes = await self._client.get_quotes(stocks)
                return quotes
            except Exception as e:
                logger.warning(f"获取行情失败 (尝试 {attempt + 1}/{self._config.max_retries}): {e}")
                if attempt < self._config.max_retries - 1:
                    await asyncio.sleep(self._config.retry_delay * (attempt + 1))
                else:
                    self._stats.error_count += 1
                    self._stats.last_error = str(e)
                    if not self._config.continue_on_error:
                        raise
                    self._notify_error(e)

        return []

    def _notify_quotes(self, quotes: List[StockQuote]) -> None:
        """通知行情回调"""
        # 批量回调
        for callback in self._quotes_callbacks:
            try:
                callback(quotes)
            except Exception as e:
                logger.error(f"批量回调函数错误: {e}")

        # 单条回调
        for quote in quotes:
            key = self._code_key(
                1 if quote.market.upper() == "SH" else 0,
                quote.code
            )

            # 检查价格是否变化
            if self._price_changed_only:
                last = self._last_quotes.get(key)
                if last and last.price == quote.price:
                    continue

            self._last_quotes[key] = quote

            for callback in self._quote_callbacks:
                try:
                    callback(quote)
                except Exception as e:
                    logger.error(f"单条回调函数错误: {e}")

    def _notify_error(self, error: Exception, code: Optional[str] = None) -> None:
        """通知错误回调"""
        for callback in self._error_callbacks:
            try:
                callback(error, code)
            except Exception as e:
                logger.error(f"错误回调函数错误: {e}")

    async def __aenter__(self) -> "QuoteSubscription":
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.stop()


class MultiQuoteSubscription:
    """
    多客户端订阅管理器

    支持使用多个客户端并发订阅，提高数据获取效率。

    Example:
        ```python
        # 使用多个客户端
        client1 = AsyncTdxClient()
        client2 = AsyncTdxClient()

        await client1.connect()
        await client2.connect()

        multi_sub = MultiQuoteSubscription([client1, client2])
        await multi_sub.subscribe_quotes(["600519", "000001", "300001"])

        # 注册回调
        def on_quote(quote: StockQuote):
            print(f"{quote.code}: {quote.price}")

        multi_sub.register_callback(on_quote)
        await multi_sub.start()

        # 运行一段时间后停止
        await asyncio.sleep(60)
        await multi_sub.stop()
        ```
    """

    def __init__(
        self,
        clients: List[AsyncTdxClient],
        config: Optional[SubscriptionConfig] = None,
    ):
        """
        初始化多客户端订阅管理器

        Args:
            clients: AsyncTdxClient 实例列表
            config: 订阅配置
        """
        self._clients = clients
        self._config = config or SubscriptionConfig()
        self._subscriptions: List[QuoteSubscription] = []
        self._codes: List[str] = []

        # 回调函数
        self._quote_callbacks: List[QuoteCallback] = []
        self._quotes_callbacks: List[QuotesCallback] = []
        self._error_callbacks: List[ErrorCallback] = []

    def register_callback(self, callback: QuoteCallback) -> None:
        """注册单条行情回调函数"""
        self._quote_callbacks.append(callback)
        for sub in self._subscriptions:
            sub.register_callback(callback)

    def register_quotes_callback(self, callback: QuotesCallback) -> None:
        """注册批量行情回调函数"""
        self._quotes_callbacks.append(callback)
        for sub in self._subscriptions:
            sub.register_quotes_callback(callback)

    def register_error_callback(self, callback: ErrorCallback) -> None:
        """注册错误回调函数"""
        self._error_callbacks.append(callback)
        for sub in self._subscriptions:
            sub.register_error_callback(callback)

    async def subscribe_quotes(
        self,
        codes: List[str],
        interval: Optional[float] = None,
        auto_start: bool = True,
    ) -> None:
        """
        订阅股票实时行情（分配到多个客户端）

        Args:
            codes: 股票代码列表
            interval: 轮询间隔
            auto_start: 是否自动启动
        """
        self._codes = codes.copy()

        if not self._clients:
            raise ValueError("没有可用的客户端")

        # 将代码平均分配到各个客户端
        codes_per_client = len(codes) // len(self._clients)
        remainder = len(codes) % len(self._clients)

        start = 0
        for i, client in enumerate(self._clients):
            # 计算该客户端负责的代码数量
            count = codes_per_client + (1 if i < remainder else 0)
            client_codes = codes[start:start + count]
            start += count

            if client_codes:
                sub = QuoteSubscription(client, self._config)

                # 复制回调
                for cb in self._quote_callbacks:
                    sub.register_callback(cb)
                for cb in self._quotes_callbacks:
                    sub.register_quotes_callback(cb)
                for cb in self._error_callbacks:
                    sub.register_error_callback(cb)

                await sub.subscribe_quotes(client_codes, interval, auto_start=False)
                self._subscriptions.append(sub)

        if auto_start:
            await self.start()

    async def start(self) -> None:
        """启动所有订阅"""
        for sub in self._subscriptions:
            await sub.start()

    async def stop(self) -> None:
        """停止所有订阅"""
        for sub in self._subscriptions:
            await sub.stop()
        self._subscriptions.clear()

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return any(sub.is_running for sub in self._subscriptions)

    def get_stats(self) -> List[SubscriptionStats]:
        """获取所有订阅的统计信息"""
        return [sub.stats for sub in self._subscriptions]

    async def __aenter__(self) -> "MultiQuoteSubscription":
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.stop()
