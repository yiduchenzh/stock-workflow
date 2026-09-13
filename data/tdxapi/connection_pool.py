"""
通达信异步连接池管理模块

支持多连接并发、连接复用、负载均衡和健康检查。
参考 aioredis 和 asyncpg 的连接池设计。
"""

import asyncio
import time
import random
from typing import Optional, List, Dict, Callable, Any, AsyncGenerator, Set
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
import logging

from data.tdxapi.async_client import AsyncTdxClient
from data.tdxapi.protocol.constants import DEFAULT_SERVERS, CONNECT_TIMEOUT

logger = logging.getLogger(__name__)


@dataclass
class PoolConnection:
    """连接池中的连接包装器"""

    client: AsyncTdxClient
    pool: "TdxConnectionPool"
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    use_count: int = 0
    _in_use: bool = False
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def in_use(self) -> bool:
        return self._in_use

    async def acquire(self) -> bool:
        """尝试获取连接使用权"""
        async with self._lock:
            if self._in_use:
                return False
            self._in_use = True
            self.last_used_at = time.time()
            self.use_count += 1
            return True

    async def release(self) -> None:
        """释放连接使用权"""
        async with self._lock:
            self._in_use = False
            self.last_used_at = time.time()

    async def is_healthy(self, timeout: float = 5.0) -> bool:
        """检查连接健康状态"""
        try:
            # 尝试获取股票数量来验证连接
            await asyncio.wait_for(
                self.client.get_stock_count("SH"),
                timeout=timeout
            )
            return True
        except Exception as e:
            logger.debug(f"Connection health check failed: {e}")
            return False

    @property
    def idle_time(self) -> float:
        """连接空闲时间（秒）"""
        return time.time() - self.last_used_at

    @property
    def age(self) -> float:
        """连接存活时间（秒）"""
        return time.time() - self.created_at


@dataclass
class PoolStats:
    """连接池统计信息"""

    total_connections: int = 0
    available_connections: int = 0
    in_use_connections: int = 0
    waiting_requests: int = 0
    total_requests: int = 0
    total_hits: int = 0  # 复用连接的次数
    total_misses: int = 0  # 新建连接的次数
    total_errors: int = 0

    @property
    def hit_rate(self) -> float:
        """连接复用率"""
        total = self.total_hits + self.total_misses
        if total == 0:
            return 0.0
        return self.total_hits / total


class TdxConnectionPool:
    """
    通达信异步连接池

    特性：
    - 连接复用：使用 asyncio.Queue 管理空闲连接
    - 连接限制：最大连接数控制
    - 超时回收：空闲连接自动关闭
    - 负载均衡：多服务器间的请求分发
    - 健康检查：自动检测和替换不健康连接

    示例：
        # 基本使用
        pool = TdxConnectionPool(max_size=10)
        await pool.initialize()

        async with pool.acquire() as client:
            quote = await client.get_quote("000001", "SZ")

        await pool.close()

        # 从连接池创建客户端
        client = await pool.create_client()
        async with client:
            quote = await client.get_quote("000001", "SZ")
    """

    def __init__(
        self,
        max_size: int = 10,
        min_size: int = 1,
        max_idle_time: float = 300.0,  # 5分钟
        max_connection_age: float = 3600.0,  # 1小时
        connection_timeout: float = CONNECT_TIMEOUT,
        acquire_timeout: float = 10.0,
        health_check_interval: float = 30.0,
        servers: Optional[List[tuple]] = None,
        load_balance_strategy: str = "round_robin",
    ):
        """
        初始化连接池

        Args:
            max_size: 最大连接数
            min_size: 最小连接数（保持的连接数）
            max_idle_time: 连接最大空闲时间（秒），超过则关闭
            max_connection_age: 连接最大存活时间（秒），超过则重建
            connection_timeout: 连接超时（秒）
            acquire_timeout: 获取连接超时（秒）
            health_check_interval: 健康检查间隔（秒）
            servers: 服务器列表 [(ip, port), ...]，None则使用默认列表
            load_balance_strategy: 负载均衡策略 ("round_robin", "random", "least_connections")
        """
        self._max_size = max_size
        self._min_size = min_size
        self._max_idle_time = max_idle_time
        self._max_connection_age = max_connection_age
        self._connection_timeout = connection_timeout
        self._acquire_timeout = acquire_timeout
        self._health_check_interval = health_check_interval
        self._servers = servers or DEFAULT_SERVERS.copy()
        self._load_balance_strategy = load_balance_strategy

        # 连接管理
        self._pool: asyncio.Queue[PoolConnection] = asyncio.Queue()
        self._all_connections: Set[PoolConnection] = set()
        self._semaphore = asyncio.Semaphore(max_size)
        self._waiting_count = 0

        # 负载均衡状态
        self._server_index = 0
        self._server_connection_counts: Dict[tuple, int] = {}

        # 后台任务
        self._maintenance_task: Optional[asyncio.Task] = None
        self._closed = True
        self._lock = asyncio.Lock()

        # 统计
        self._stats = PoolStats()

    async def initialize(self) -> "TdxConnectionPool":
        """
        初始化连接池，创建最小连接数

        Returns:
            self 用于链式调用
        """
        if not self._closed:
            return self

        self._closed = False

        # 创建最小连接数
        for _ in range(self._min_size):
            try:
                conn = await self._create_connection()
                if conn:
                    await self._pool.put(conn)
            except Exception as e:
                logger.warning(f"Failed to create initial connection: {e}")

        # 启动维护任务
        self._maintenance_task = asyncio.create_task(self._maintenance_loop())

        logger.info(f"Connection pool initialized with {self._pool.qsize()} connections")
        return self

    async def close(self) -> None:
        """关闭连接池，释放所有连接"""
        if self._closed:
            return

        self._closed = True

        # 停止维护任务
        if self._maintenance_task:
            self._maintenance_task.cancel()
            try:
                await self._maintenance_task
            except asyncio.CancelledError:
                pass
            self._maintenance_task = None

        # 关闭所有连接
        close_tasks = []
        for conn in list(self._all_connections):
            close_tasks.append(self._close_connection(conn))

        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)

        self._all_connections.clear()

        # 清空队列
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                await self._close_connection(conn)
            except asyncio.QueueEmpty:
                break

        logger.info("Connection pool closed")

    async def _create_connection(self) -> Optional[PoolConnection]:
        """创建新连接"""
        ip, port = self._select_server()

        try:
            client = AsyncTdxClient(
                ip=ip,
                port=port,
                timeout=self._connection_timeout,
                auto_reconnect=True,
                heartbeat=True,
            )
            await client.connect()

            conn = PoolConnection(client=client, pool=self)
            async with self._lock:
                self._all_connections.add(conn)
                self._server_connection_counts[(ip, port)] = (
                    self._server_connection_counts.get((ip, port), 0) + 1
                )

            self._stats.total_misses += 1
            logger.debug(f"Created new connection to {ip}:{port}")
            return conn

        except Exception as e:
            self._stats.total_errors += 1
            logger.error(f"Failed to create connection to {ip}:{port}: {e}")
            return None

    async def _close_connection(self, conn: PoolConnection) -> None:
        """关闭单个连接"""
        try:
            async with self._lock:
                if conn in self._all_connections:
                    self._all_connections.remove(conn)
                    # 更新服务器连接计数
                    for server, count in list(self._server_connection_counts.items()):
                        if conn.client._ip == server[0] and conn.client._port == server[1]:
                            if count <= 1:
                                del self._server_connection_counts[server]
                            else:
                                self._server_connection_counts[server] = count - 1
                            break

            await conn.client.close()
            logger.debug("Connection closed")
        except Exception as e:
            logger.debug(f"Error closing connection: {e}")

    def _select_server(self) -> tuple:
        """
        根据负载均衡策略选择服务器

        Returns:
            (ip, port) 元组
        """
        if not self._servers:
            raise ValueError("No servers available")

        if self._load_balance_strategy == "round_robin":
            server = self._servers[self._server_index % len(self._servers)]
            self._server_index += 1
            return server

        elif self._load_balance_strategy == "random":
            return random.choice(self._servers)

        elif self._load_balance_strategy == "least_connections":
            # 选择连接数最少的服务器
            min_count = float("inf")
            best_server = self._servers[0]
            for server in self._servers:
                count = self._server_connection_counts.get(server, 0)
                if count < min_count:
                    min_count = count
                    best_server = server
            return best_server

        else:
            # 默认轮询
            server = self._servers[self._server_index % len(self._servers)]
            self._server_index += 1
            return server

    async def acquire(self) -> PoolConnection:
        """
        从连接池获取连接

        Returns:
            PoolConnection 对象

        Raises:
            asyncio.TimeoutError: 获取连接超时
            ConnectionError: 无法创建新连接
        """
        self._stats.total_requests += 1

        # 使用信号量限制并发数
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self._acquire_timeout
            )
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError(
                f"Failed to acquire connection slot within {self._acquire_timeout}s"
            )

        try:
            # 首先尝试从池中获取空闲连接
            while not self._pool.empty():
                try:
                    conn = self._pool.get_nowait()
                    if await conn.acquire():
                        # 检查连接是否过期或空闲太久
                        if self._should_recycle(conn):
                            await self._close_connection(conn)
                            continue
                        self._stats.total_hits += 1
                        return conn
                    else:
                        # 连接已被占用，放回队列
                        await self._pool.put(conn)
                        break
                except asyncio.QueueEmpty:
                    break

            # 创建新连接
            conn = await self._create_connection()
            if conn:
                await conn.acquire()
                return conn

            raise ConnectionError("Failed to create new connection")

        except Exception:
            self._semaphore.release()
            raise

    async def release(self, conn: PoolConnection) -> None:
        """
        将连接释放回连接池

        Args:
            conn: 要释放的连接
        """
        if conn.pool is not self:
            logger.warning("Attempting to release connection from different pool")
            return

        await conn.release()

        # 检查是否需要回收连接
        if self._should_recycle(conn):
            await self._close_connection(conn)
        else:
            await self._pool.put(conn)

        self._semaphore.release()

    def _should_recycle(self, conn: PoolConnection) -> bool:
        """判断连接是否需要回收（关闭）"""
        if conn.age > self._max_connection_age:
            return True
        if conn.idle_time > self._max_idle_time:
            return True
        return False

    @asynccontextmanager
    async def acquire_ctx(self) -> AsyncGenerator[AsyncTdxClient, None]:
        """
        获取连接的异步上下文管理器

        示例：
            async with pool.acquire_ctx() as client:
                quote = await client.get_quote("000001", "SZ")
        """
        conn = await self.acquire()
        try:
            yield conn.client
        finally:
            await self.release(conn)

    async def create_client(self) -> "PooledClient":
        """
        从连接池创建一个客户端包装器

        Returns:
            PooledClient 对象，支持异步上下文管理器
        """
        conn = await self.acquire()
        return PooledClient(conn, self)

    async def _maintenance_loop(self) -> None:
        """连接池维护循环"""
        while not self._closed:
            try:
                await asyncio.sleep(self._health_check_interval)
                await self._do_maintenance()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Maintenance loop error: {e}")

    async def _do_maintenance(self) -> None:
        """执行维护任务"""
        if self._closed:
            return

        async with self._lock:
            # 检查并关闭过期连接
            to_close = []
            to_check = []

            for conn in self._all_connections:
                if not conn.in_use:
                    if self._should_recycle(conn):
                        to_close.append(conn)
                    elif conn.idle_time > self._health_check_interval:
                        to_check.append(conn)

            # 关闭过期连接
            for conn in to_close:
                await self._close_connection(conn)

            # 健康检查
            unhealthy = []
            for conn in to_check:
                if not await conn.is_healthy():
                    unhealthy.append(conn)

            for conn in unhealthy:
                await self._close_connection(conn)

            # 确保最小连接数
            current_size = len(self._all_connections)
            needed = self._min_size - current_size

            for _ in range(needed):
                try:
                    new_conn = await self._create_connection()
                    if new_conn:
                        await self._pool.put(new_conn)
                except Exception as e:
                    logger.warning(f"Failed to create maintenance connection: {e}")

    @property
    def stats(self) -> PoolStats:
        """获取连接池统计信息"""
        self._stats.total_connections = len(self._all_connections)
        self._stats.available_connections = self._pool.qsize()
        self._stats.in_use_connections = (
            self._stats.total_connections - self._stats.available_connections
        )
        self._stats.waiting_requests = max(0, self._waiting_count)
        return self._stats

    def get_stats_dict(self) -> Dict[str, Any]:
        """获取统计信息字典"""
        stats = self.stats
        return {
            "total_connections": stats.total_connections,
            "available_connections": stats.available_connections,
            "in_use_connections": stats.in_use_connections,
            "waiting_requests": stats.waiting_requests,
            "total_requests": stats.total_requests,
            "total_hits": stats.total_hits,
            "total_misses": stats.total_misses,
            "hit_rate": f"{stats.hit_rate:.2%}",
            "total_errors": stats.total_errors,
        }


class PooledClient:
    """
    连接池客户端包装器

    支持异步上下文管理器，自动管理连接的获取和释放。
    """

    def __init__(self, conn: PoolConnection, pool: TdxConnectionPool):
        self._conn = conn
        self._pool = pool
        self._client = conn.client
        self._released = False

    def __getattr__(self, name: str) -> Any:
        """代理到实际的 AsyncTdxClient"""
        return getattr(self._client, name)

    async def __aenter__(self) -> "PooledClient":
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口，自动释放连接"""
        await self.close()

    async def close(self) -> None:
        """关闭客户端，释放连接回连接池"""
        if not self._released:
            self._released = True
            await self._pool.release(self._conn)


# 全局连接池实例（可选使用）
_default_pool: Optional[TdxConnectionPool] = None
_default_pool_lock = asyncio.Lock()


async def get_default_pool(
    max_size: int = 10,
    min_size: int = 1,
    **kwargs
) -> TdxConnectionPool:
    """
    获取默认连接池实例（单例模式）

    Args:
        max_size: 最大连接数
        min_size: 最小连接数
        **kwargs: 其他连接池参数

    Returns:
        TdxConnectionPool 实例
    """
    global _default_pool

    async with _default_pool_lock:
        if _default_pool is None or _default_pool._closed:
            _default_pool = TdxConnectionPool(
                max_size=max_size,
                min_size=min_size,
                **kwargs
            )
            await _default_pool.initialize()

    return _default_pool


async def close_default_pool() -> None:
    """关闭默认连接池"""
    global _default_pool

    async with _default_pool_lock:
        if _default_pool:
            await _default_pool.close()
            _default_pool = None
