"""
通达信行情异步客户端
基于 asyncio 实现，功能与 TdxClient 相同但支持异步操作
"""

import asyncio
import zlib
from typing import Optional, Union, List, Tuple, Callable, Dict, Any, AsyncGenerator
from dataclasses import dataclass

from data.tdxapi.protocol.constants import (
    DEFAULT_SERVERS,
    RSP_HEADER_LEN,
    SETUP_CMD1,
    SETUP_CMD2,
    SETUP_CMD3,
    CONNECT_TIMEOUT,
    HEARTBEAT_INTERVAL,
)
from data.tdxapi.protocol.requests import (
    build_quote_request,
    build_bars_request,
    build_stock_count_request,
    build_security_list_request,
    build_minute_time_request,
    build_transaction_request,
    build_history_minute_request,
    build_xdxr_request,
    build_finance_request,
)
from data.tdxapi.protocol.packet import RspHeader
from data.tdxapi.parser import parse_quotes, parse_bars, parse_ticks
from data.tdxapi.parser.quote_parser import (
    parse_minute_time,
    parse_history_minute_time,
    parse_security_list,
    parse_stock_count,
    parse_xdxr_info,
    parse_finance_info,
)
from data.tdxapi.models import StockQuote, Bar, Tick


@dataclass
class BatchResult:
    """批量请求结果"""

    success: Dict[str, Any]  # 成功的结果 {code: result}
    failed: Dict[str, Exception]  # 失败的 {code: exception}
    total: int  # 总数
    success_count: int  # 成功数
    failed_count: int  # 失败数

    def __repr__(self):
        return f"BatchResult(total={self.total}, success={self.success_count}, failed={self.failed_count})"


class AsyncTdxClient:
    """通达信行情异步客户端（不依赖任何通达信软件）"""

    def __init__(
        self,
        ip: Optional[str] = None,
        port: int = 7709,
        timeout: float = CONNECT_TIMEOUT,
        auto_reconnect: bool = True,
        max_retries: int = 3,
        heartbeat: bool = True,
    ):
        """
        初始化异步客户端

        Args:
            ip: 服务器IP，None则自动选择最优服务器
            port: 服务器端口
            timeout: 连接超时（秒）
            auto_reconnect: 是否自动重连
            max_retries: 最大重试次数
            heartbeat: 是否启用心跳
        """
        self._ip = ip
        self._port = port
        self._timeout = timeout
        self._auto_reconnect = auto_reconnect
        self._max_retries = max_retries
        self._heartbeat_enabled = heartbeat
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._seq = 0
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def connect(self, ip: Optional[str] = None, port: Optional[int] = None) -> "AsyncTdxClient":
        """
        异步连接行情服务器并完成三次握手

        Args:
            ip: 服务器IP，None则使用初始化时的IP或自动选择
            port: 服务器端口，None则使用初始化时的端口

        Returns:
            self 用于链式调用
        """
        target_ip = ip or self._ip
        target_port = port or self._port

        if not target_ip:
            target_ip, target_port = await self._find_best_server()

        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(target_ip, target_port),
            timeout=self._timeout
        )
        self._ip = target_ip
        self._port = target_port
        self._seq = 0

        # 三次握手
        for cmd in [SETUP_CMD1, SETUP_CMD2, SETUP_CMD3]:
            await self._send_raw(cmd)
            await self._recv_response()

        if self._heartbeat_enabled:
            self._start_heartbeat()

        return self

    async def close(self) -> None:
        """异步断开连接"""
        self._stop_heartbeat()
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except (OSError, asyncio.CancelledError):
                pass
            finally:
                self._writer = None
                self._reader = None

    def _start_heartbeat(self) -> None:
        """启动心跳任务"""
        self._stop_heartbeat()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    def _stop_heartbeat(self) -> None:
        """停止心跳任务"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

    async def _heartbeat_loop(self) -> None:
        """心跳循环"""
        from data.tdxapi.protocol.requests import build_heartbeat_request

        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                async with self._lock:
                    if self._writer:
                        try:
                            await self._send_raw(build_heartbeat_request())
                        except Exception:
                            pass
        except asyncio.CancelledError:
            pass

    async def _ensure_connected(self) -> None:
        """确保已连接，未连接时自动重连"""
        if self._writer is None:
            await self.connect()

    async def _send_raw(self, data: bytes) -> None:
        """异步发送原始数据"""
        if not self._writer:
            raise ConnectionError("未连接服务器")
        self._writer.write(data)
        await self._writer.drain()

    async def _recv_exact(self, n: int) -> bytes:
        """异步精确接收 n 字节"""
        if not self._reader:
            raise ConnectionError("未连接服务器")
        data = await self._reader.readexactly(n)
        return data

    async def _recv_response(self) -> Tuple[RspHeader, bytes]:
        """
        异步接收响应

        Returns:
            (header, body) 元组
        """
        head_buf = await self._recv_exact(RSP_HEADER_LEN)
        header = RspHeader.unpack(head_buf)

        if header.zip_size >= header.unzip_size:
            actual_size = header.unzip_size
        else:
            actual_size = header.zip_size

        body_buf = bytearray()
        while len(body_buf) < actual_size:
            remaining = actual_size - len(body_buf)
            chunk = await self._reader.read(min(remaining, 8192))
            if not chunk:
                if len(body_buf) > 0:
                    break
                raise ConnectionError("连接断开")
            body_buf.extend(chunk)

        body = bytes(body_buf)
        needs_decompress = header.zip_size < header.unzip_size
        if not needs_decompress and len(body) >= 2 and body[:2] == b"x\x9c":
            needs_decompress = True
        if needs_decompress:
            try:
                body = zlib.decompress(body)
            except zlib.error:
                pass

        return header, body

    async def _send_recv(self, body: bytes, retries: Optional[int] = None) -> bytes:
        """
        异步发送请求并接收响应

        Args:
            body: 请求体
            retries: 重试次数，None则使用默认值

        Returns:
            响应体字节数据
        """
        async with self._lock:
            return await self._send_recv_unlocked(body, retries)

    async def _send_recv_unlocked(self, body: bytes, retries: Optional[int] = None) -> bytes:
        """异步发送请求并接收响应（无锁）"""
        await self._ensure_connected()
        retries = retries if retries is not None else self._max_retries

        for attempt in range(retries):
            try:
                await self._send_raw(body)
                _, body = await self._recv_response()
                return body
            except (ConnectionError, OSError, asyncio.TimeoutError) as e:
                if attempt < retries - 1:
                    await asyncio.sleep(0.1 * (attempt + 1))
                    await self._reconnect_unlocked()
                else:
                    raise ConnectionError(f"请求失败（已重试 {retries} 次）: {e}")

    async def _reconnect(self) -> None:
        """异步重新连接（带锁）"""
        async with self._lock:
            await self._reconnect_unlocked()

    async def _reconnect_unlocked(self) -> None:
        """异步重新连接（无锁）"""
        self._stop_heartbeat()
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except (OSError, asyncio.CancelledError):
                pass
        self._writer = None
        self._reader = None
        await self.connect(self._ip, self._port)

    async def _find_best_server(self) -> Tuple[str, int]:
        """异步测速选择最优服务器"""
        best = None
        best_time = float("inf")

        async def ping_server(ip: str, port: int) -> Optional[Tuple[float, str, int]]:
            try:
                start = asyncio.get_event_loop().time()
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(ip, port),
                    timeout=5
                )
                elapsed = (asyncio.get_event_loop().time() - start) * 1000
                writer.close()
                await writer.wait_closed()
                return (elapsed, ip, port)
            except (asyncio.TimeoutError, OSError):
                return None

        # 并发测速所有服务器
        tasks = [ping_server(ip, port) for ip, port in DEFAULT_SERVERS]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                continue
            if result is not None:
                elapsed, ip, port = result
                if elapsed < best_time:
                    best_time = elapsed
                    best = (ip, port)

        if best is None:
            raise ConnectionError("所有服务器均不可用")
        return best

    @staticmethod
    def _parse_market(market: Union[str, int]) -> int:
        """解析市场代码"""
        if isinstance(market, int):
            return market
        return 1 if market.upper() == "SH" else 0

    # === 行情数据 ===

    async def get_quote(self, code: str, market: str = "SH") -> Optional[StockQuote]:
        """
        异步获取单只股票实时行情

        Args:
            code: 股票代码
            market: 市场代码 (SH/SZ)

        Returns:
            StockQuote 对象，失败返回 None
        """
        m = self._parse_market(market)
        results = await self.get_quotes([(m, code)])
        return results[0] if results else None

    async def get_quotes(self, stocks: List[Tuple[int, str]]) -> List[StockQuote]:
        """
        异步批量获取实时行情

        Args:
            stocks: 股票列表 [(market, code), ...]

        Returns:
            StockQuote 列表
        """
        body = build_quote_request(stocks)
        resp = await self._send_recv(body)
        return parse_quotes(resp)

    async def get_index_quote(self, code: str) -> Optional[StockQuote]:
        """
        异步获取指数实时行情

        Args:
            code: 指数代码（如 000001 上证指数）

        Returns:
            StockQuote 对象
        """
        m = self._parse_market("SH")
        results = await self.get_quotes([(m, code)])
        return results[0] if results else None

    async def get_futures_quote(self, code: str, market: int = 6) -> Optional[StockQuote]:
        """
        异步获取期货实时行情

        Args:
            code: 期货代码
            market: 市场代码 (6=上海期货, 7=中金所, 8=大连, 9=郑州)

        Returns:
            StockQuote 对象
        """
        results = await self.get_quotes([(market, code)])
        return results[0] if results else None

    # === K线数据 ===

    async def get_bars(
        self,
        code: str,
        market: str = "SH",
        period: str = "1d",
        count: int = 100,
        start: int = 0,
    ) -> List[Bar]:
        """
        异步获取K线数据

        Args:
            code: 股票代码
            market: 市场代码 (SH/SZ)
            period: 周期 (1d/1w/1m/5m/15m/30m/60m/1min)
            count: 获取条数
            start: 起始位置

        Returns:
            Bar 列表
        """
        m = 1 if market.upper() == "SH" else 0
        period_map = {
            "1d": 9,
            "1w": 5,
            "1m": 6,
            "1min": 7,
            "5m": 0,
            "15m": 1,
            "30m": 2,
            "60m": 3,
        }
        category = period_map.get(period, 9)
        body = build_bars_request(category, m, code, start, count)
        resp = await self._send_recv(body)
        bars = parse_bars(resp, category)
        for bar in bars:
            bar.code = code
            bar.market = market.upper()
        return bars

    async def get_index_bars(
        self,
        code: str,
        market: str = "SH",
        period: str = "1d",
        count: int = 100,
        start: int = 0,
    ) -> List[Bar]:
        """
        异步获取指数K线

        Args:
            code: 指数代码
            market: 市场代码 (SH/SZ)
            period: 周期 (1d/5m/15m/30m/60m)
            count: 获取条数
            start: 起始位置

        Returns:
            Bar 列表
        """
        from data.tdxapi.protocol.requests import build_index_bars_request

        m = 1 if market.upper() == "SH" else 0
        period_map = {"1d": 9, "5m": 0, "15m": 1, "30m": 2, "60m": 3}
        category = period_map.get(period, 9)
        body = build_index_bars_request(category, m, code, start, count)
        resp = await self._send_recv(body)
        bars = parse_bars(resp, category)
        for bar in bars:
            bar.code = code
            bar.market = market.upper()
        return bars

    # === 分时数据 ===

    async def get_minute_time(
        self, code: str, market: str = "SH", use_bars: bool = True
    ) -> List[dict]:
        """
        异步获取当日分时数据

        Args:
            code: 股票代码
            market: 市场 (SH/SZ)
            use_bars: 是否使用1分钟K线代替（更可靠）

        Returns:
            分时数据列表，每项包含 price 和 volume
        """
        if use_bars:
            bars = await self.get_bars(code, market, "1min", 240)
            return [{"price": b.close, "volume": b.volume} for b in bars]

        m = 1 if market.upper() == "SH" else 0
        body = build_minute_time_request(m, code)
        resp = await self._send_recv(body)
        return parse_minute_time(resp)

    async def get_history_minute_time(
        self, code: str, market: str = "SH", date: Optional[int] = None
    ) -> List[dict]:
        """
        异步获取历史分时数据

        Args:
            code: 股票代码
            market: 市场 (SH/SZ)
            date: 日期 (YYYYMMDD格式)，None则使用今天

        Returns:
            分时数据列表
        """
        m = 1 if market.upper() == "SH" else 0
        import datetime

        date = date or int(datetime.datetime.now().strftime("%Y%m%d"))
        body = build_history_minute_request(m, code, date)
        resp = await self._send_recv(body)
        return parse_history_minute_time(resp)

    # === 分笔成交 ===

    async def get_transactions(
        self, code: str, market: str = "SH", start: int = 0, count: int = 100
    ) -> List[Tick]:
        """
        异步获取分笔成交数据

        Args:
            code: 股票代码
            market: 市场 (SH/SZ)
            start: 起始位置
            count: 获取条数

        Returns:
            Tick 列表
        """
        m = 1 if market.upper() == "SH" else 0
        body = build_transaction_request(m, code, start, count)
        resp = await self._send_recv(body)
        return parse_ticks(resp, m, code)

    async def get_history_transactions(
        self,
        code: str,
        market: str = "SH",
        date: Optional[int] = None,
        start: int = 0,
        count: int = 100,
    ) -> List[Tick]:
        """
        异步获取历史分笔成交

        Args:
            code: 股票代码
            market: 市场 (SH/SZ)
            date: 日期 (YYYYMMDD格式)，None则使用今天
            start: 起始位置
            count: 获取条数

        Returns:
            Tick 列表
        """
        from data.tdxapi.protocol.requests import build_history_transaction_request

        m = 1 if market.upper() == "SH" else 0
        import datetime

        date = date or int(datetime.datetime.now().strftime("%Y%m%d"))
        body = build_history_transaction_request(m, code, start, count, date)
        resp = await self._send_recv(body)
        return parse_ticks(resp, m, code)

    # === 股票列表 ===

    async def get_stock_count(self, market: str = "SH") -> int:
        """
        异步获取市场股票总数

        Args:
            market: 市场 (SH/SZ)

        Returns:
            股票数量
        """
        m = self._parse_market(market)
        body = build_stock_count_request(m)
        resp = await self._send_recv(body)
        return parse_stock_count(resp)

    async def get_security_list(
        self, market: str = "SH", start: int = 0, count: Optional[int] = None
    ) -> List[dict]:
        """
        异步获取股票列表（分页）

        Args:
            market: 市场 (SH/SZ)
            start: 起始位置
            count: 获取数量，None则获取全部

        Returns:
            股票信息列表
        """
        m = self._parse_market(market)
        if count is None:
            count = await self.get_stock_count(market)
        results = []
        pos = start
        while pos < count:
            body = build_security_list_request(m, pos)
            resp = await self._send_recv(body)
            page = parse_security_list(resp, m)
            if not page:
                break
            results.extend(page)
            pos += len(page)
        return results

    async def get_security_list_by_region(
        self, region: int, start: int = 0, count: int = 100
    ) -> List[dict]:
        """
        按板块获取股票列表

        Args:
            region: 板块代码
            start: 起始位置
            count: 获取数量

        Returns:
            股票信息列表
        """
        from data.tdxapi.protocol.requests import build_security_list_request

        results = []
        pos = start
        while len(results) < count:
            body = build_security_list_request(region, pos)
            resp = await self._send_recv(body)
            page = parse_security_list(resp, region)
            if not page:
                break
            results.extend(page)
            pos += len(page)
        return results[:count]

    # === 财务数据 ===

    async def get_xdxr_info(self, code: str, market: str = "SH") -> List[dict]:
        """
        异步获取除权除息数据

        Args:
            code: 股票代码
            market: 市场 (SH/SZ)

        Returns:
            除权除息信息列表
        """
        m = self._parse_market(market)
        body = build_xdxr_request(m, code)
        resp = await self._send_recv(body)
        return parse_xdxr_info(resp)

    async def get_finance_info(self, code: str, market: str = "SH") -> dict:
        """
        异步获取财务数据

        Args:
            code: 股票代码
            market: 市场 (SH/SZ)

        Returns:
            财务信息字典
        """
        m = self._parse_market(market)
        body = build_finance_request(m, code)
        resp = await self._send_recv(body)
        return parse_finance_info(resp)

    # === 公司信息/板块信息 ===

    async def get_company_info_category(self, code: str, market: str = "SH") -> List[dict]:
        """
        异步获取公司信息目录

        Args:
            code: 股票代码
            market: 市场 (SH/SZ)

        Returns:
            信息目录列表
        """
        from data.tdxapi.protocol.requests import build_company_info_category_request
        from data.tdxapi.parser import parse_company_info_category

        m = self._parse_market(market)
        body = build_company_info_category_request(m, code)
        resp = await self._send_recv(body)
        return parse_company_info_category(resp)

    async def get_company_info_content(
        self,
        code: str,
        market: str = "SH",
        filename: str = "",
        start: int = 0,
        length: int = 6000,
    ) -> bytes:
        """
        异步获取公司信息内容

        Args:
            code: 股票代码
            market: 市场 (SH/SZ)
            filename: 文件名
            start: 起始位置
            length: 读取长度

        Returns:
            内容字节数据
        """
        from data.tdxapi.protocol.requests import build_company_info_content_request
        from data.tdxapi.parser import parse_company_info_content

        m = self._parse_market(market)
        body = build_company_info_content_request(m, code, filename, start, length)
        resp = await self._send_recv(body)
        return parse_company_info_content(resp)

    async def get_block_info_meta(self, blockfile: str = "block.dat") -> dict:
        """
        异步获取板块信息元数据

        Args:
            blockfile: 板块文件名

        Returns:
            元数据字典
        """
        from data.tdxapi.protocol.requests import build_block_info_meta_request
        from data.tdxapi.parser import parse_block_info_meta

        body = build_block_info_meta_request(blockfile)
        resp = await self._send_recv(body)
        return parse_block_info_meta(resp)

    async def get_block_info(
        self, blockfile: str = "block.dat", start: int = 0, size: int = 100
    ) -> List[dict]:
        """
        异步获取板块信息内容

        Args:
            blockfile: 板块文件名
            start: 起始位置
            size: 获取数量

        Returns:
            板块信息列表
        """
        from data.tdxapi.protocol.requests import build_block_info_request
        from data.tdxapi.parser import parse_block_info

        body = build_block_info_request(blockfile, start, size)
        resp = await self._send_recv(body)
        return parse_block_info(resp)

    # === 异步上下文管理器 ===

    async def __aenter__(self) -> "AsyncTdxClient":
        """异步上下文管理器入口"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.close()

    # === 批量请求方法 ===

    async def batch_get_quotes(
        self,
        codes: List[Tuple[str, str]],
        max_concurrent: int = 10,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        continue_on_error: bool = True,
    ) -> BatchResult:
        """
        并发获取多只股票实时行情

        Args:
            codes: 股票代码列表 [(market, code), ...] 如 [("SH", "600519"), ("SZ", "000001")]
            max_concurrent: 最大并发数，默认10
            progress_callback: 进度回调函数，参数为 (completed, total, current_code)
            continue_on_error: 是否继续处理其他股票当某个失败时

        Returns:
            BatchResult 包含成功和失败的结果

        Example:
            result = await client.batch_get_quotes([("SH", "600519"), ("SZ", "000001")])
            for code, quote in result.success.items():
                print(f"{code}: {quote.price}")
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        success: Dict[str, StockQuote] = {}
        failed: Dict[str, Exception] = {}
        completed = 0

        async def fetch_single(market: str, code: str) -> None:
            nonlocal completed
            async with semaphore:
                try:
                    quote = await self.get_quote(code, market)
                    if quote:
                        key = f"{market.upper()}:{code}"
                        success[key] = quote
                    else:
                        failed[f"{market.upper()}:{code}"] = Exception("返回空结果")
                except Exception as e:
                    if not continue_on_error:
                        raise
                    failed[f"{market.upper()}:{code}"] = e
                finally:
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, len(codes), code)

        tasks = [fetch_single(m, c) for m, c in codes]
        await asyncio.gather(*tasks, return_exceptions=continue_on_error)

        return BatchResult(
            success=success,
            failed=failed,
            total=len(codes),
            success_count=len(success),
            failed_count=len(failed),
        )

    async def batch_get_bars(
        self,
        codes: List[Tuple[str, str]],
        period: str = "1d",
        count: int = 100,
        max_concurrent: int = 5,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        continue_on_error: bool = True,
    ) -> BatchResult:
        """
        并发获取多只股票K线数据

        Args:
            codes: 股票代码列表 [(market, code), ...] 如 [("SH", "600519"), ("SZ", "000001")]
            period: K线周期 (1d/1w/1m/5m/15m/30m/60m/1min)
            count: 获取条数
            max_concurrent: 最大并发数，默认5（K线数据较大，并发数建议更低）
            progress_callback: 进度回调函数，参数为 (completed, total, current_code)
            continue_on_error: 是否继续处理其他股票当某个失败时

        Returns:
            BatchResult 包含成功和失败的结果

        Example:
            result = await client.batch_get_bars(
                [("SH", "600519"), ("SZ", "000001")],
                period="1d",
                count=100
            )
            for code, bars in result.success.items():
                print(f"{code}: {len(bars)} bars")
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        success: Dict[str, List[Bar]] = {}
        failed: Dict[str, Exception] = {}
        completed = 0

        async def fetch_single(market: str, code: str) -> None:
            nonlocal completed
            async with semaphore:
                try:
                    bars = await self.get_bars(code, market, period, count)
                    key = f"{market.upper()}:{code}"
                    success[key] = bars
                except Exception as e:
                    if not continue_on_error:
                        raise
                    failed[f"{market.upper()}:{code}"] = e
                finally:
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, len(codes), code)

        tasks = [fetch_single(m, c) for m, c in codes]
        await asyncio.gather(*tasks, return_exceptions=continue_on_error)

        return BatchResult(
            success=success,
            failed=failed,
            total=len(codes),
            success_count=len(success),
            failed_count=len(failed),
        )

    async def batch_get_quotes_by_codes(
        self,
        codes: List[str],
        default_market: str = "SH",
        max_concurrent: int = 10,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        continue_on_error: bool = True,
    ) -> BatchResult:
        """
        通过纯代码列表并发获取行情（自动判断市场）

        Args:
            codes: 股票代码列表 ["600519", "000001", ...]
            default_market: 默认市场，当无法判断时使用
            max_concurrent: 最大并发数
            progress_callback: 进度回调函数
            continue_on_error: 是否继续处理其他股票当某个失败时

        Returns:
            BatchResult 包含成功和失败的结果

        Note:
            自动判断规则：6开头为SH，0/3开头为SZ
        """
        codes_with_market: List[Tuple[str, str]] = []
        for code in codes:
            if code.startswith("6"):
                codes_with_market.append(("SH", code))
            elif code.startswith(("0", "3")):
                codes_with_market.append(("SZ", code))
            else:
                codes_with_market.append((default_market, code))

        return await self.batch_get_quotes(
            codes_with_market,
            max_concurrent=max_concurrent,
            progress_callback=progress_callback,
            continue_on_error=continue_on_error,
        )

    # === 流式数据接口 ===

    async def stream_quotes(
        self,
        codes: List[Tuple[int, str]],
        interval: float = 1.0,
        stop_event: Optional[asyncio.Event] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> AsyncGenerator[List[StockQuote], None]:
        """
        异步生成器持续获取实时行情数据

        支持 `async for` 语法，可以通过 stop_event 控制停止。

        Args:
            codes: 股票列表 [(market, code), ...]
            interval: 轮询间隔（秒），默认 1 秒
            stop_event: 停止事件，设置后流式接口会优雅退出
            on_error: 错误回调函数，接收异常对象

        Yields:
            List[StockQuote]: 每次获取的行情数据列表

        Example:
            ```python
            # 使用 async for 获取实时行情
            async for quotes in client.stream_quotes([(1, "600519")], interval=2):
                for q in quotes:
                    print(f"{q.code}: {q.price}")

            # 使用 stop_event 控制停止
            stop_event = asyncio.Event()
            async for quotes in client.stream_quotes(codes, stop_event=stop_event):
                # 处理数据...
                if some_condition:
                    stop_event.set()  # 停止流式接口
            ```
        """
        if stop_event is None:
            stop_event = asyncio.Event()

        while not stop_event.is_set():
            try:
                quotes = await self.get_quotes(codes)
                yield quotes
            except Exception as e:
                if on_error:
                    on_error(e)
                else:
                    # 默认行为：记录错误但继续
                    pass

            # 等待下一次轮询，同时监听停止事件
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=interval
                )
            except asyncio.TimeoutError:
                # 正常超时，继续下一次轮询
                pass

    async def stream_bars(
        self,
        code: str,
        market: str = "SH",
        period: str = "1d",
        start: int = 0,
        end: Optional[int] = None,
        page_size: int = 100,
        stop_event: Optional[asyncio.Event] = None,
    ) -> AsyncGenerator[List[Bar], None]:
        """
        分页流式获取K线数据

        支持 `async for` 语法，分批获取大量K线数据，避免一次性加载过多数据。

        Args:
            code: 股票代码
            market: 市场代码 (SH/SZ)
            period: 周期 (1d/1w/1m/5m/15m/30m/60m/1min)
            start: 起始位置
            end: 结束位置，None 表示获取到最新数据
            page_size: 每页获取的条数
            stop_event: 停止事件，设置后流式接口会优雅退出

        Yields:
            List[Bar]: 每页K线数据列表

        Example:
            ```python
            # 分页流式获取历史K线
            async for bars in client.stream_bars("600519", "SH", "1d", page_size=50):
                for bar in bars:
                    print(f"{bar.datetime}: O={bar.open} C={bar.close}")

            # 获取指定范围的K线
            stop_event = asyncio.Event()
            async for bars in client.stream_bars(
                "600519", "SH", "1d",
                start=0, end=500, page_size=100,
                stop_event=stop_event
            ):
                process_bars(bars)
            ```
        """
        if stop_event is None:
            stop_event = asyncio.Event()

        pos = start
        while not stop_event.is_set():
            # 检查是否到达结束位置
            if end is not None and pos >= end:
                break

            # 计算本次获取的数量
            count = page_size
            if end is not None:
                count = min(page_size, end - pos)

            try:
                bars = await self.get_bars(code, market, period, count, pos)

                if not bars:
                    # 没有更多数据了
                    break

                yield bars
                pos += len(bars)

                # 如果获取的数据少于请求的数量，说明已经到末尾
                if len(bars) < count:
                    break

            except Exception:
                # 发生错误时停止
                break

    async def stream_transactions(
        self,
        code: str,
        market: str = "SH",
        start: int = 0,
        max_count: Optional[int] = None,
        page_size: int = 100,
        stop_event: Optional[asyncio.Event] = None,
    ) -> AsyncGenerator[List[Tick], None]:
        """
        分页流式获取分笔成交数据

        Args:
            code: 股票代码
            market: 市场代码 (SH/SZ)
            start: 起始位置
            max_count: 最大获取条数，None 表示无限制
            page_size: 每页获取的条数
            stop_event: 停止事件

        Yields:
            List[Tick]: 每页分笔成交数据

        Example:
            ```python
            async for ticks in client.stream_transactions("600519", "SH", page_size=50):
                for tick in ticks:
                    print(f"{tick.time}: {tick.price} vol:{tick.volume}")
            ```
        """
        if stop_event is None:
            stop_event = asyncio.Event()

        pos = start
        total_fetched = 0

        while not stop_event.is_set():
            # 检查是否达到最大数量
            if max_count is not None and total_fetched >= max_count:
                break

            # 计算本次获取的数量
            count = page_size
            if max_count is not None:
                count = min(page_size, max_count - total_fetched)

            try:
                ticks = await self.get_transactions(code, market, pos, count)

                if not ticks:
                    # 没有更多数据了
                    break

                yield ticks
                pos += len(ticks)
                total_fetched += len(ticks)

                # 如果获取的数据少于请求的数量，说明已经到末尾
                if len(ticks) < count:
                    break

            except Exception:
                # 发生错误时停止
                break
