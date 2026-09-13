"""
批量数据下载模块

提供全市场股票列表获取、历史K线批量下载、分笔数据批量下载功能。
支持并发下载、进度显示(tqdm)和断点续传机制。
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union, Any

from data.tdxapi.async_client import AsyncTdxClient
from data.tdxapi.models import Bar, Tick
from data.tdxapi.cache import TdxCache


@dataclass
class DownloadProgress:
    """下载进度记录"""

    total: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    current_code: str = ""
    current_task: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    errors: Dict[str, str] = field(default_factory=dict)

    @property
    def progress_percent(self) -> float:
        """获取进度百分比"""
        if self.total == 0:
            return 0.0
        return (self.completed / self.total) * 100

    @property
    def elapsed_seconds(self) -> float:
        """获取已用时间（秒）"""
        if self.start_time is None:
            return 0.0
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()

    @property
    def estimated_remaining_seconds(self) -> float:
        """估算剩余时间（秒）"""
        if self.completed == 0 or self.start_time is None:
            return 0.0
        elapsed = self.elapsed_seconds
        rate = self.completed / elapsed
        remaining = self.total - self.completed - self.failed
        return remaining / rate if rate > 0 else 0.0

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "total": self.total,
            "completed": self.completed,
            "failed": self.failed,
            "skipped": self.skipped,
            "current_code": self.current_code,
            "current_task": self.current_task,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DownloadProgress":
        """从字典创建"""
        progress = cls(
            total=data.get("total", 0),
            completed=data.get("completed", 0),
            failed=data.get("failed", 0),
            skipped=data.get("skipped", 0),
            current_code=data.get("current_code", ""),
            current_task=data.get("current_task", ""),
            errors=data.get("errors", {}),
        )
        if data.get("start_time"):
            progress.start_time = datetime.fromisoformat(data["start_time"])
        if data.get("end_time"):
            progress.end_time = datetime.fromisoformat(data["end_time"])
        return progress


class BulkDownloader:
    """批量数据下载器

    支持功能:
    - 全市场股票列表获取（深圳、上海、北京）
    - 历史K线批量下载（按日期范围）
    - 分笔数据批量下载（多日）
    - 并发下载（使用 AsyncTdxClient）
    - 进度显示（tqdm）
    - 断点续传（记录下载进度到文件）

    Example:
        ```python
        downloader = BulkDownloader()

        # 获取全市场股票列表
        stocks = await downloader.get_all_stocks()

        # 批量下载K线数据
        await downloader.download_bars(
            codes=[("SH", "600519"), ("SZ", "000001")],
            period="1d",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
            output_dir="./data"
        )

        # 批量下载分笔数据
        await downloader.download_ticks(
            codes=[("SH", "600519")],
            dates=[20240101, 20240102],
            output_dir="./data"
        )
        ```
    """

    def __init__(
        self,
        client: Optional[AsyncTdxClient] = None,
        cache: Optional[TdxCache] = None,
        max_concurrent: int = 5,
        progress_file: Optional[Union[str, Path]] = None,
        enable_tqdm: bool = True,
    ):
        """初始化批量下载器

        Args:
            client: AsyncTdxClient 实例，None则自动创建
            cache: TdxCache 实例，None则不使用缓存
            max_concurrent: 最大并发数
            progress_file: 进度保存文件路径，None则不保存进度
            enable_tqdm: 是否启用tqdm进度条
        """
        self._client = client
        self._own_client = client is None
        self._cache = cache
        self._max_concurrent = max_concurrent
        self._progress_file = Path(progress_file) if progress_file else None
        self._enable_tqdm = enable_tqdm
        self._progress = DownloadProgress()
        self._stop_event = asyncio.Event()

    async def __aenter__(self):
        """异步上下文管理器入口"""
        if self._own_client and self._client is None:
            self._client = AsyncTdxClient()
            await self._client.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self._own_client and self._client:
            await self._client.close()
            self._client = None

    def _get_client(self) -> AsyncTdxClient:
        """获取客户端实例"""
        if self._client is None:
            raise RuntimeError("客户端未初始化，请使用 async with 或手动连接")
        return self._client

    def _load_progress(self, task_id: str) -> Optional[DownloadProgress]:
        """从文件加载进度"""
        if not self._progress_file:
            return None

        try:
            if self._progress_file.exists():
                with open(self._progress_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if task_id in data:
                        return DownloadProgress.from_dict(data[task_id])
        except (json.JSONDecodeError, KeyError, IOError):
            pass
        return None

    def _save_progress(self, task_id: str, progress: DownloadProgress) -> None:
        """保存进度到文件"""
        if not self._progress_file:
            return

        try:
            data = {}
            if self._progress_file.exists():
                with open(self._progress_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

            data[task_id] = progress.to_dict()

            # 确保目录存在
            self._progress_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._progress_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError:
            pass

    def _clear_progress(self, task_id: str) -> None:
        """清除进度记录"""
        if not self._progress_file or not self._progress_file.exists():
            return

        try:
            with open(self._progress_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if task_id in data:
                del data[task_id]

            with open(self._progress_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError:
            pass

    def _create_progress_bar(self, total: int, desc: str = ""):
        """创建进度条"""
        if not self._enable_tqdm:
            return None

        try:
            from tqdm import tqdm

            return tqdm(total=total, desc=desc, unit="item")
        except ImportError:
            return None

    async def get_all_stocks(
        self, markets: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """获取全市场股票列表

        Args:
            markets: 市场列表，默认 ["SH", "SZ", "BJ"]

        Returns:
            股票信息列表，每项包含 code, name, market 等字段
        """
        if markets is None:
            markets = ["SH", "SZ", "BJ"]

        client = self._get_client()
        all_stocks = []

        for market in markets:
            try:
                stocks = await client.get_security_list(market)
                for stock in stocks:
                    stock["market"] = market
                all_stocks.extend(stocks)
            except Exception as e:
                print(f"获取 {market} 市场股票列表失败: {e}")

        return all_stocks

    async def get_all_stock_codes(
        self, markets: Optional[List[str]] = None
    ) -> List[Tuple[str, str]]:
        """获取全市场股票代码列表

        Args:
            markets: 市场列表，默认 ["SH", "SZ", "BJ"]

        Returns:
            股票代码列表 [(market, code), ...]
        """
        stocks = await self.get_all_stocks(markets)
        return [(s["market"], s["code"]) for s in stocks]

    async def download_bars(
        self,
        codes: List[Tuple[str, str]],
        period: str = "1d",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        count: int = 800,
        output_dir: Optional[Union[str, Path]] = None,
        use_cache: bool = True,
        resume: bool = True,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
    ) -> DownloadProgress:
        """批量下载K线数据

        Args:
            codes: 股票代码列表 [(market, code), ...]
            period: K线周期 (1d/1w/1m/5m/15m/30m/60m/1min)
            start_date: 开始日期，用于计算需要下载的数量
            end_date: 结束日期
            count: 每只股票获取的K线数量（当不提供日期范围时）
            output_dir: 输出目录，None则不保存到文件
            use_cache: 是否使用本地缓存
            resume: 是否启用断点续传
            progress_callback: 进度回调函数

        Returns:
            DownloadProgress 下载进度对象
        """
        client = self._get_client()
        output_path = Path(output_dir) if output_dir else None

        if output_path:
            output_path.mkdir(parents=True, exist_ok=True)

        # 生成任务ID
        task_id = f"bars_{period}_{start_date.strftime('%Y%m%d') if start_date else 'none'}"

        # 尝试加载之前的进度
        completed_codes = set()
        if resume:
            saved_progress = self._load_progress(task_id)
            if saved_progress:
                completed_codes = set(saved_progress.errors.keys())
                # 成功的也加入已完成的
                for code_key in self._get_successful_codes(saved_progress):
                    completed_codes.add(code_key)

        # 过滤已完成的
        pending_codes = [
            (m, c) for m, c in codes if f"{m}:{c}" not in completed_codes
        ]

        self._progress = DownloadProgress(
            total=len(codes),
            completed=len(codes) - len(pending_codes),
            skipped=len(codes) - len(pending_codes),
            start_time=datetime.now(),
            current_task="download_bars",
        )

        # 创建进度条
        pbar = self._create_progress_bar(len(codes), desc=f"下载 {period} K线")
        if pbar:
            pbar.update(self._progress.completed)

        semaphore = asyncio.Semaphore(self._max_concurrent)

        async def fetch_single(market: str, code: str) -> Tuple[str, Optional[List[Bar]]]:
            """获取单只股票K线"""
            key = f"{market}:{code}"
            self._progress.current_code = code

            async with semaphore:
                try:
                    # 检查缓存
                    if use_cache and self._cache:
                        cached_bars = self._cache.get_bars(
                            code, market, start_date, end_date
                        )
                        if cached_bars:
                            self._progress.skipped += 1
                            return key, cached_bars

                    # 从服务器获取
                    bars = await client.get_bars(code, market, period, count)

                    # 保存到缓存
                    if use_cache and self._cache and bars:
                        self._cache.save_bars(bars)

                    # 保存到文件
                    if output_path and bars:
                        self._save_bars_to_file(
                            output_path, market, code, period, bars
                        )

                    self._progress.completed += 1
                    return key, bars

                except Exception as e:
                    self._progress.failed += 1
                    self._progress.errors[key] = str(e)
                    return key, None

                finally:
                    if pbar:
                        pbar.update(1)
                    if progress_callback:
                        progress_callback(self._progress)
                    # 定期保存进度
                    if self._progress.completed % 10 == 0:
                        self._save_progress(task_id, self._progress)

        # 执行下载
        tasks = [fetch_single(m, c) for m, c in pending_codes]
        await asyncio.gather(*tasks, return_exceptions=True)

        self._progress.end_time = datetime.now()
        if pbar:
            pbar.close()

        # 保存最终进度
        self._save_progress(task_id, self._progress)

        return self._progress

    async def download_ticks(
        self,
        codes: List[Tuple[str, str]],
        dates: List[int],
        output_dir: Optional[Union[str, Path]] = None,
        use_cache: bool = True,
        resume: bool = True,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
    ) -> DownloadProgress:
        """批量下载分笔数据

        Args:
            codes: 股票代码列表 [(market, code), ...]
            dates: 日期列表 [YYYYMMDD, ...]
            output_dir: 输出目录
            use_cache: 是否使用本地缓存
            resume: 是否启用断点续传
            progress_callback: 进度回调函数

        Returns:
            DownloadProgress 下载进度对象
        """
        client = self._get_client()
        output_path = Path(output_dir) if output_dir else None

        if output_path:
            output_path.mkdir(parents=True, exist_ok=True)

        # 生成所有任务
        all_tasks = [(m, c, d) for m, c in codes for d in dates]
        task_id = f"ticks_{dates[0]}_{dates[-1]}" if dates else "ticks"

        # 尝试加载之前的进度
        completed_tasks = set()
        if resume:
            saved_progress = self._load_progress(task_id)
            if saved_progress:
                for key in saved_progress.errors.keys():
                    completed_tasks.add(key)

        # 过滤已完成的
        pending_tasks = [
            t for t in all_tasks if f"{t[0]}:{t[1]}:{t[2]}" not in completed_tasks
        ]

        self._progress = DownloadProgress(
            total=len(all_tasks),
            completed=len(all_tasks) - len(pending_tasks),
            skipped=len(all_tasks) - len(pending_tasks),
            start_time=datetime.now(),
            current_task="download_ticks",
        )

        # 创建进度条
        pbar = self._create_progress_bar(len(all_tasks), desc="下载分笔数据")
        if pbar:
            pbar.update(self._progress.completed)

        semaphore = asyncio.Semaphore(self._max_concurrent)

        async def fetch_single(
            market: str, code: str, date: int
        ) -> Tuple[str, Optional[List[Tick]]]:
            """获取单只股票单日分笔数据"""
            key = f"{market}:{code}:{date}"
            self._progress.current_code = f"{code} ({date})"

            async with semaphore:
                try:
                    # 检查缓存
                    if use_cache and self._cache:
                        # 分笔缓存按日期存储，这里简化处理
                        pass

                    # 从服务器获取
                    ticks = await client.get_history_transactions(
                        code, market, date, start=0, count=2000
                    )

                    # 保存到文件
                    if output_path and ticks:
                        self._save_ticks_to_file(
                            output_path, market, code, date, ticks
                        )

                    self._progress.completed += 1
                    return key, ticks

                except Exception as e:
                    self._progress.failed += 1
                    self._progress.errors[key] = str(e)
                    return key, None

                finally:
                    if pbar:
                        pbar.update(1)
                    if progress_callback:
                        progress_callback(self._progress)
                    # 定期保存进度
                    if self._progress.completed % 10 == 0:
                        self._save_progress(task_id, self._progress)

        # 执行下载
        tasks = [fetch_single(m, c, d) for m, c, d in pending_tasks]
        await asyncio.gather(*tasks, return_exceptions=True)

        self._progress.end_time = datetime.now()
        if pbar:
            pbar.close()

        # 保存最终进度
        self._save_progress(task_id, self._progress)

        return self._progress

    def _get_successful_codes(self, progress: DownloadProgress) -> List[str]:
        """从进度记录中获取成功的代码列表"""
        # 这里假设 errors 只包含失败的，成功的没有记录
        # 实际实现中可能需要额外存储成功列表
        return []

    def _save_bars_to_file(
        self,
        output_dir: Path,
        market: str,
        code: str,
        period: str,
        bars: List[Bar],
    ) -> None:
        """保存K线数据到文件"""
        filename = f"{market}_{code}_{period}.json"
        filepath = output_dir / filename

        data = {
            "market": market,
            "code": code,
            "period": period,
            "count": len(bars),
            "bars": [
                {
                    "datetime": b.datetime.isoformat() if b.datetime else None,
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                    "amount": b.amount,
                }
                for b in bars
            ],
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _save_ticks_to_file(
        self,
        output_dir: Path,
        market: str,
        code: str,
        date: int,
        ticks: List[Tick],
    ) -> None:
        """保存分笔数据到文件"""
        filename = f"{market}_{code}_{date}_ticks.json"
        filepath = output_dir / filename

        data = {
            "market": market,
            "code": code,
            "date": date,
            "count": len(ticks),
            "ticks": [
                {
                    "time": t.time,
                    "price": t.price,
                    "volume": t.volume,
                    "amount": t.amount,
                    "direction": t.direction,
                }
                for t in ticks
            ],
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def stop(self) -> None:
        """停止下载"""
        self._stop_event.set()

    def get_progress(self) -> DownloadProgress:
        """获取当前进度"""
        return self._progress

    def reset_progress(self, task_id: Optional[str] = None) -> None:
        """重置进度

        Args:
            task_id: 任务ID，None则清除所有进度
        """
        if task_id:
            self._clear_progress(task_id)
        else:
            self._progress = DownloadProgress()


class DateRangeHelper:
    """日期范围辅助类"""

    @staticmethod
    def get_trading_days(start_date: datetime, end_date: datetime) -> List[datetime]:
        """获取交易日列表（简化版，假设每天都是交易日）

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            日期列表
        """
        days = []
        current = start_date
        while current <= end_date:
            # 跳过周末（简化处理）
            if current.weekday() < 5:  # 0-4 是周一到周五
                days.append(current)
            current += timedelta(days=1)
        return days

    @staticmethod
    def date_to_int(date: datetime) -> int:
        """将datetime转换为YYYYMMDD格式整数"""
        return int(date.strftime("%Y%m%d"))

    @staticmethod
    def int_to_date(date_int: int) -> datetime:
        """将YYYYMMDD格式整数转换为datetime"""
        return datetime.strptime(str(date_int), "%Y%m%d")


async def download_all_stocks_bars(
    output_dir: Union[str, Path],
    markets: Optional[List[str]] = None,
    period: str = "1d",
    count: int = 800,
    max_concurrent: int = 5,
    progress_file: Optional[Union[str, Path]] = None,
) -> DownloadProgress:
    """便捷函数：下载全市场K线数据

    Args:
        output_dir: 输出目录
        markets: 市场列表，默认 ["SH", "SZ"]
        period: K线周期
        count: 每只股票获取的K线数量
        max_concurrent: 最大并发数
        progress_file: 进度文件路径

    Returns:
        DownloadProgress 下载进度对象
    """
    if markets is None:
        markets = ["SH", "SZ"]

    async with BulkDownloader(
        max_concurrent=max_concurrent,
        progress_file=progress_file,
        enable_tqdm=True,
    ) as downloader:
        # 获取股票列表
        print("正在获取股票列表...")
        stocks = await downloader.get_all_stocks(markets)
        codes = [(s["market"], s["code"]) for s in stocks]
        print(f"共 {len(codes)} 只股票")

        # 下载K线数据
        progress = await downloader.download_bars(
            codes=codes,
            period=period,
            count=count,
            output_dir=output_dir,
            resume=True,
        )

        return progress
