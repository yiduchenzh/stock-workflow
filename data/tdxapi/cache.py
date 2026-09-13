"""
SQLite本地缓存模块

提供K线数据和分笔数据的本地SQLite存储和查询功能。
支持zlib和lz4数据压缩，压缩/解压对用户透明。
支持LRU缓存策略、TTL过期机制和增量更新。
"""

import json
import sqlite3
import threading
import zlib
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from data.tdxapi.models import Bar, Tick


class CompressionType(Enum):
    """压缩类型枚举"""

    NONE = "none"
    ZLIB = "zlib"
    LZ4 = "lz4"


@dataclass
class CacheEntry:
    """缓存条目元数据"""

    key: str
    timestamp: datetime
    access_count: int = 0
    last_accessed: datetime = None

    def __post_init__(self):
        if self.last_accessed is None:
            self.last_accessed = self.timestamp


class TdxCache:
    """通达信数据本地SQLite缓存类

    支持K线数据(bars)和分笔数据(ticks)的存储和查询，
    可按股票代码、日期范围进行查询。
    支持数据压缩存储（zlib/lz4），压缩/解压对用户透明。

    新增功能:
    - LRU (Least Recently Used) 缓存策略
    - TTL (Time To Live) 数据过期机制
    - 增量更新支持
    - 缓存统计信息

    Attributes:
        db_path: SQLite数据库文件路径
        compression: 压缩类型
        compression_level: 压缩级别（zlib: 0-9, lz4: 1-12）
        max_memory_cache_size: 内存LRU缓存最大条目数
        default_ttl: 默认数据过期时间(秒)，None表示永不过期
    """

    # 数据库版本，用于迁移
    DB_VERSION = 3

    def __init__(
        self,
        db_path: Union[str, Path] = "tdx_cache.db",
        compression: Union[str, CompressionType] = CompressionType.ZLIB,
        compression_level: Optional[int] = None,
        max_memory_cache_size: int = 1000,
        default_ttl: Optional[int] = None,
    ):
        """初始化缓存实例

        Args:
            db_path: SQLite数据库文件路径，默认为当前目录下的tdx_cache.db
            compression: 压缩类型，可选 'none', 'zlib', 'lz4'，默认为 'zlib'
            compression_level: 压缩级别，None则使用默认值（zlib: 6, lz4: 5）
            max_memory_cache_size: 内存LRU缓存最大条目数，默认1000
            default_ttl: 默认数据过期时间(秒)，None表示永不过期
        """
        self.db_path = Path(db_path)

        # 处理压缩类型
        if isinstance(compression, str):
            compression = CompressionType(compression.lower())
        self.compression = compression

        # 设置压缩级别
        if compression_level is None:
            if compression == CompressionType.ZLIB:
                self.compression_level = 6
            elif compression == CompressionType.LZ4:
                self.compression_level = 5
            else:
                self.compression_level = 0
        else:
            self.compression_level = compression_level

        # 检查lz4可用性
        self._lz4_available = self._check_lz4_available()
        if self.compression == CompressionType.LZ4 and not self._lz4_available:
            raise ImportError(
                "lz4 is not installed. Install it with: pip install tdxapi[compression]"
            )

        # LRU缓存配置
        self.max_memory_cache_size = max_memory_cache_size
        self.default_ttl = default_ttl

        # 内存LRU缓存: OrderedDict用于实现LRU
        self._memory_cache: OrderedDict[str, List[Bar]] = OrderedDict()
        self._cache_lock = threading.RLock()
        self._access_stats: Dict[str, CacheEntry] = {}

        self._init_db()

    def _check_lz4_available(self) -> bool:
        """检查lz4是否可用"""
        try:
            import lz4.frame  # noqa: F401

            return True
        except ImportError:
            return False

    @contextmanager
    def _get_connection(self):
        """获取数据库连接的上下文管理器

        Yields:
            sqlite3.Connection: 数据库连接对象
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        """初始化数据库表结构"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 元数据表（存储版本和配置）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """)

            # K线数据表（使用BLOB存储压缩数据）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bars (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL,
                    market TEXT NOT NULL,
                    datetime TEXT NOT NULL,
                    data BLOB NOT NULL,
                    compression TEXT NOT NULL DEFAULT 'none',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(code, market, datetime)
                )
                """)

            # 分笔数据表（使用BLOB存储压缩数据）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ticks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL,
                    market TEXT NOT NULL,
                    time TEXT NOT NULL,
                    data BLOB NOT NULL,
                    compression TEXT NOT NULL DEFAULT 'none',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(code, market, time)
                )
                """)

            # 缓存元数据表 - 用于存储每只股票的数据更新时间和统计
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cache_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL,
                    market TEXT NOT NULL,
                    data_type TEXT NOT NULL,  -- 'bars' or 'ticks'
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    earliest_date TIMESTAMP,
                    latest_date TIMESTAMP,
                    record_count INTEGER DEFAULT 0,
                    UNIQUE(code, market, data_type)
                )
                """)

            # 创建索引优化查询性能
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_bars_code_market ON bars(code, market)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_bars_datetime ON bars(datetime)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_ticks_code_market ON ticks(code, market)"
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ticks_time ON ticks(time)")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_metadata_lookup ON cache_metadata(code, market, data_type)"
            )

            # 检查并更新数据库版本
            cursor.execute("SELECT value FROM metadata WHERE key = 'version'")
            row = cursor.fetchone()
            current_version = int(row["value"]) if row else 1

            if current_version < self.DB_VERSION:
                self._migrate_db(cursor, current_version)

            # 保存当前版本
            cursor.execute(
                """
                INSERT OR REPLACE INTO metadata (key, value)
                VALUES ('version', ?)
                """,
                (str(self.DB_VERSION),),
            )

    def _migrate_db(self, cursor, from_version: int) -> None:
        """数据库迁移

        Args:
            cursor: 数据库游标
            from_version: 当前数据库版本
        """
        if from_version < 2:
            # 迁移到版本2：添加压缩支持
            try:
                cursor.execute(
                    "ALTER TABLE bars ADD COLUMN compression TEXT NOT NULL DEFAULT 'none'"
                )
            except sqlite3.OperationalError:
                pass  # 列已存在

            try:
                cursor.execute(
                    "ALTER TABLE ticks ADD COLUMN compression TEXT NOT NULL DEFAULT 'none'"
                )
            except sqlite3.OperationalError:
                pass  # 列已存在

        if from_version < 3:
            # 迁移到版本3：添加时间戳和元数据表
            try:
                cursor.execute(
                    "ALTER TABLE bars ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                )
            except sqlite3.OperationalError:
                pass

            try:
                cursor.execute(
                    "ALTER TABLE bars ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                )
            except sqlite3.OperationalError:
                pass

            try:
                cursor.execute(
                    "ALTER TABLE ticks ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                )
            except sqlite3.OperationalError:
                pass

            try:
                cursor.execute(
                    "ALTER TABLE ticks ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                )
            except sqlite3.OperationalError:
                pass

            # 创建元数据表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cache_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL,
                    market TEXT NOT NULL,
                    data_type TEXT NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    earliest_date TIMESTAMP,
                    latest_date TIMESTAMP,
                    record_count INTEGER DEFAULT 0,
                    UNIQUE(code, market, data_type)
                )
                """)

            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_metadata_lookup ON cache_metadata(code, market, data_type)"
            )

    def _get_cache_key(self, code: str, market: str, data_type: str = "bars") -> str:
        """生成缓存键"""
        return f"{market}:{code}:{data_type}"

    def _update_memory_cache(self, key: str, data: List[Bar]) -> None:
        """更新内存LRU缓存"""
        with self._cache_lock:
            # 如果key已存在，先删除再添加（移到末尾表示最新使用）
            if key in self._memory_cache:
                del self._memory_cache[key]
            # 如果超过最大容量，移除最旧的条目
            while len(self._memory_cache) >= self.max_memory_cache_size:
                self._memory_cache.popitem(last=False)
            # 添加新条目
            self._memory_cache[key] = data
            # 更新访问统计
            now = datetime.now()
            if key not in self._access_stats:
                self._access_stats[key] = CacheEntry(key=key, timestamp=now)
            self._access_stats[key].access_count += 1
            self._access_stats[key].last_accessed = now

    def _get_from_memory_cache(self, key: str) -> Optional[List[Bar]]:
        """从内存LRU缓存获取数据，并更新访问顺序"""
        with self._cache_lock:
            if key in self._memory_cache:
                # 移动到末尾表示最近使用
                data = self._memory_cache.pop(key)
                self._memory_cache[key] = data
                # 更新访问统计
                if key in self._access_stats:
                    self._access_stats[key].access_count += 1
                    self._access_stats[key].last_accessed = datetime.now()
                return data
            return None

    def _is_data_expired(
        self, code: str, market: str, data_type: str = "bars"
    ) -> bool:
        """检查数据是否过期"""
        if self.default_ttl is None:
            return False

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT last_updated FROM cache_metadata
                WHERE code = ? AND market = ? AND data_type = ?
                """,
                (code, market, data_type),
            )
            row = cursor.fetchone()
            if row is None:
                return True  # 无元数据视为过期

            last_updated = datetime.fromisoformat(row["last_updated"])
            expiry_time = last_updated + timedelta(seconds=self.default_ttl)
            return datetime.now() > expiry_time

    def _update_metadata(
        self,
        code: str,
        market: str,
        data_type: str,
        earliest_date: Optional[datetime] = None,
        latest_date: Optional[datetime] = None,
        record_count_delta: int = 0,
    ) -> None:
        """更新缓存元数据"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 获取现有记录数
            cursor.execute(
                """
                SELECT record_count FROM cache_metadata
                WHERE code = ? AND market = ? AND data_type = ?
                """,
                (code, market, data_type),
            )
            row = cursor.fetchone()

            if row is None:
                # 插入新记录
                cursor.execute(
                    """
                    INSERT INTO cache_metadata
                    (code, market, data_type, last_updated, earliest_date, latest_date, record_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        code,
                        market,
                        data_type,
                        datetime.now().isoformat(),
                        earliest_date.isoformat() if earliest_date else None,
                        latest_date.isoformat() if latest_date else None,
                        max(0, record_count_delta),
                    ),
                )
            else:
                # 更新现有记录
                current_count = row["record_count"]
                new_count = max(0, current_count + record_count_delta)

                # 重新计算日期范围
                if data_type == "bars":
                    cursor.execute(
                        """
                        SELECT MIN(datetime) as earliest, MAX(datetime) as latest, COUNT(*) as cnt
                        FROM bars WHERE code = ? AND market = ?
                        """,
                        (code, market),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT MIN(time) as earliest, MAX(time) as latest, COUNT(*) as cnt
                        FROM ticks WHERE code = ? AND market = ?
                        """,
                        (code, market),
                    )
                date_row = cursor.fetchone()

                cursor.execute(
                    """
                    UPDATE cache_metadata
                    SET last_updated = ?, earliest_date = ?, latest_date = ?, record_count = ?
                    WHERE code = ? AND market = ? AND data_type = ?
                    """,
                    (
                        datetime.now().isoformat(),
                        date_row["earliest"] if date_row else None,
                        date_row["latest"] if date_row else None,
                        new_count,
                        code,
                        market,
                        data_type,
                    ),
                )

    def _compress(self, data: bytes) -> tuple[bytes, CompressionType]:
        """压缩数据

        Args:
            data: 原始数据

        Returns:
            (压缩后的数据, 使用的压缩类型)
        """
        if self.compression == CompressionType.NONE:
            return data, CompressionType.NONE

        if self.compression == CompressionType.ZLIB:
            compressed = zlib.compress(data, level=self.compression_level)
            return compressed, CompressionType.ZLIB

        if self.compression == CompressionType.LZ4:
            import lz4.frame

            compressed = lz4.frame.compress(
                data, compression_level=self.compression_level
            )
            return compressed, CompressionType.LZ4

        return data, CompressionType.NONE

    def _decompress(self, data: bytes, compression: str) -> bytes:
        """解压数据

        Args:
            data: 压缩数据
            compression: 压缩类型字符串

        Returns:
            解压后的原始数据
        """
        comp_type = CompressionType(compression)

        if comp_type == CompressionType.NONE:
            return data

        if comp_type == CompressionType.ZLIB:
            return zlib.decompress(data)

        if comp_type == CompressionType.LZ4:
            import lz4.frame

            return lz4.frame.decompress(data)

        return data

    def _bar_to_dict(self, bar: Bar) -> dict:
        """将Bar对象转换为字典"""
        return {
            "code": bar.code,
            "market": bar.market,
            "datetime": bar.datetime.isoformat(),
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "amount": bar.amount,
        }

    def _dict_to_bar(self, data: dict) -> Bar:
        """将字典转换为Bar对象"""
        return Bar(
            code=data["code"],
            market=data["market"],
            datetime=datetime.fromisoformat(data["datetime"]),
            open=data["open"],
            high=data["high"],
            low=data["low"],
            close=data["close"],
            volume=data["volume"],
            amount=data["amount"],
        )

    def _tick_to_dict(self, tick: Tick) -> dict:
        """将Tick对象转换为字典"""
        return {
            "code": tick.code,
            "market": tick.market,
            "time": tick.time,
            "price": tick.price,
            "volume": tick.volume,
            "amount": tick.amount,
            "direction": tick.direction,
        }

    def _dict_to_tick(self, data: dict) -> Tick:
        """将字典转换为Tick对象"""
        return Tick(
            code=data["code"],
            market=data["market"],
            time=data["time"],
            price=data["price"],
            volume=data["volume"],
            amount=data["amount"],
            direction=data["direction"],
        )

    def save_bars(self, bars: List[Bar]) -> int:
        """保存K线数据到本地缓存

        Args:
            bars: K线数据列表

        Returns:
            实际保存的数据条数（已存在的数据会被跳过）

        Raises:
            ValueError: 输入数据为空列表
        """
        if not bars:
            raise ValueError("bars列表不能为空")

        saved_count = 0

        # 按股票分组处理
        from collections import defaultdict
        bars_by_stock = defaultdict(list)
        for bar in bars:
            bars_by_stock[(bar.code, bar.market)].append(bar)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            for bar in bars:
                try:
                    # 序列化为JSON并压缩
                    json_data = json.dumps(self._bar_to_dict(bar), ensure_ascii=False)
                    compressed_data, compression_used = self._compress(
                        json_data.encode("utf-8")
                    )

                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO bars
                        (code, market, datetime, data, compression, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            bar.code,
                            bar.market,
                            bar.datetime.isoformat(),
                            compressed_data,
                            compression_used.value,
                            datetime.now().isoformat(),
                        ),
                    )
                    if cursor.rowcount > 0:
                        saved_count += 1
                except sqlite3.Error:
                    # 单条数据失败继续处理其他数据
                    continue

        # 为每只股票更新元数据和内存缓存
        for (code, market), stock_bars in bars_by_stock.items():
            stock_saved = len(stock_bars)  # 简化处理，假设都保存成功
            if stock_saved > 0:
                dates = [bar.datetime for bar in stock_bars]
                self._update_metadata(
                    code=code,
                    market=market,
                    data_type="bars",
                    earliest_date=min(dates),
                    latest_date=max(dates),
                    record_count_delta=stock_saved,
                )

                # 更新内存缓存
                cache_key = self._get_cache_key(code, market, "bars")
                self._update_memory_cache(cache_key, stock_bars)

        return saved_count

    def get_bars(
        self,
        code: str,
        market: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        use_cache: bool = True,
    ) -> List[Bar]:
        """从本地缓存查询K线数据

        Args:
            code: 股票代码
            market: 市场代码(SH/SZ/BJ)
            start_date: 开始日期(包含)，为None则不限制
            end_date: 结束日期(包含)，为None则不限制
            use_cache: 是否使用内存LRU缓存，默认True

        Returns:
            K线数据列表，按时间升序排列
        """
        cache_key = self._get_cache_key(code, market, "bars")

        # 尝试从内存缓存获取（当没有日期限制时）
        if use_cache and start_date is None and end_date is None:
            cached_data = self._get_from_memory_cache(cache_key)
            if cached_data is not None and not self._is_data_expired(
                code, market, "bars"
            ):
                return cached_data

        with self._get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM bars WHERE code = ? AND market = ?"
            params: List[Union[str, int]] = [code, market]

            if start_date is not None:
                query += " AND datetime >= ?"
                params.append(start_date.isoformat())

            if end_date is not None:
                query += " AND datetime <= ?"
                params.append(end_date.isoformat())

            query += " ORDER BY datetime ASC"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            bars = []
            for row in rows:
                try:
                    # 解压并反序列化
                    compressed_data = row["data"]
                    compression = row["compression"]
                    json_data = self._decompress(compressed_data, compression)
                    data = json.loads(json_data.decode("utf-8"))
                    bars.append(self._dict_to_bar(data))
                except (json.JSONDecodeError, zlib.error, Exception):
                    # 数据损坏，跳过
                    continue

            # 更新内存缓存（当查询完整数据时）
            if use_cache and start_date is None and end_date is None and bars:
                self._update_memory_cache(cache_key, bars)

            return bars

    def save_ticks(self, ticks: List[Tick]) -> int:
        """保存分笔数据到本地缓存

        Args:
            ticks: 分笔数据列表

        Returns:
            实际保存的数据条数（已存在的数据会被跳过）

        Raises:
            ValueError: 输入数据为空列表
        """
        if not ticks:
            raise ValueError("ticks列表不能为空")

        saved_count = 0
        code = ticks[0].code
        market = ticks[0].market

        with self._get_connection() as conn:
            cursor = conn.cursor()
            for tick in ticks:
                try:
                    # 序列化为JSON并压缩
                    json_data = json.dumps(self._tick_to_dict(tick), ensure_ascii=False)
                    compressed_data, compression_used = self._compress(
                        json_data.encode("utf-8")
                    )

                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO ticks
                        (code, market, time, data, compression, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            tick.code,
                            tick.market,
                            tick.time,
                            compressed_data,
                            compression_used.value,
                            datetime.now().isoformat(),
                        ),
                    )
                    if cursor.rowcount > 0:
                        saved_count += 1
                except sqlite3.Error:
                    # 单条数据失败继续处理其他数据
                    continue

        if saved_count > 0:
            self._update_metadata(
                code=code,
                market=market,
                data_type="ticks",
                record_count_delta=saved_count,
            )

        return saved_count

    def get_ticks(
        self,
        code: str,
        market: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> List[Tick]:
        """从本地缓存查询分笔数据

        Args:
            code: 股票代码
            market: 市场代码(SH/SZ/BJ)
            start_time: 开始时间(包含)，格式"HH:MM:SS"，为None则不限制
            end_time: 结束时间(包含)，格式"HH:MM:SS"，为None则不限制

        Returns:
            分笔数据列表，按时间升序排列
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM ticks WHERE code = ? AND market = ?"
            params: List[str] = [code, market]

            if start_time is not None:
                query += " AND time >= ?"
                params.append(start_time)

            if end_time is not None:
                query += " AND time <= ?"
                params.append(end_time)

            query += " ORDER BY time ASC"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            ticks = []
            for row in rows:
                try:
                    # 解压并反序列化
                    compressed_data = row["data"]
                    compression = row["compression"]
                    json_data = self._decompress(compressed_data, compression)
                    data = json.loads(json_data.decode("utf-8"))
                    ticks.append(self._dict_to_tick(data))
                except (json.JSONDecodeError, zlib.error, Exception):
                    # 数据损坏，跳过
                    continue

            return ticks

    def clear_cache(
        self, code: Optional[str] = None, market: Optional[str] = None
    ) -> int:
        """清除本地缓存数据

        Args:
            code: 股票代码，为None则清除所有股票
            market: 市场代码，为None则清除所有市场

        Returns:
            删除的数据条数
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            total_deleted = 0

            # 清除K线数据
            if code and market:
                cursor.execute(
                    "DELETE FROM bars WHERE code = ? AND market = ?",
                    (code, market),
                )
            elif code:
                cursor.execute("DELETE FROM bars WHERE code = ?", (code,))
            elif market:
                cursor.execute("DELETE FROM bars WHERE market = ?", (market,))
            else:
                cursor.execute("DELETE FROM bars")
            total_deleted += cursor.rowcount

            # 清除分笔数据
            if code and market:
                cursor.execute(
                    "DELETE FROM ticks WHERE code = ? AND market = ?",
                    (code, market),
                )
            elif code:
                cursor.execute("DELETE FROM ticks WHERE code = ?", (code,))
            elif market:
                cursor.execute("DELETE FROM ticks WHERE market = ?", (market,))
            else:
                cursor.execute("DELETE FROM ticks")
            total_deleted += cursor.rowcount

            # 清除元数据
            if code and market:
                cursor.execute(
                    "DELETE FROM cache_metadata WHERE code = ? AND market = ?",
                    (code, market),
                )
            elif code:
                cursor.execute("DELETE FROM cache_metadata WHERE code = ?", (code,))
            elif market:
                cursor.execute("DELETE FROM cache_metadata WHERE market = ?", (market,))
            else:
                cursor.execute("DELETE FROM cache_metadata")

            # 清除内存缓存
            with self._cache_lock:
                if code and market:
                    # 清除特定股票的内存缓存
                    cache_key = self._get_cache_key(code, market, "bars")
                    if cache_key in self._memory_cache:
                        del self._memory_cache[cache_key]
                    if cache_key in self._access_stats:
                        del self._access_stats[cache_key]
                elif code:
                    # 清除特定代码的所有市场缓存
                    keys_to_remove = [
                        k for k in self._memory_cache.keys()
                        if k.startswith(f"SH:{code}:") or k.startswith(f"SZ:{code}:") or k.startswith(f"BJ:{code}:")
                    ]
                    for key in keys_to_remove:
                        del self._memory_cache[key]
                        if key in self._access_stats:
                            del self._access_stats[key]
                elif market:
                    # 清除特定市场的所有缓存
                    keys_to_remove = [
                        k for k in self._memory_cache.keys()
                        if k.startswith(f"{market}:")
                    ]
                    for key in keys_to_remove:
                        del self._memory_cache[key]
                        if key in self._access_stats:
                            del self._access_stats[key]
                else:
                    # 清除所有内存缓存
                    self._memory_cache.clear()
                    self._access_stats.clear()

            return total_deleted

    def get_cache_info(self) -> dict:
        """获取缓存统计信息

        Returns:
            包含缓存统计信息的字典
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM bars")
            bars_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM ticks")
            ticks_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(DISTINCT code || '_' || market) FROM bars")
            bars_stocks = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(DISTINCT code || '_' || market) FROM ticks")
            ticks_stocks = cursor.fetchone()[0]

            # 获取压缩统计
            cursor.execute(
                "SELECT compression, COUNT(*) FROM bars GROUP BY compression"
            )
            bars_compression = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute(
                "SELECT compression, COUNT(*) FROM ticks GROUP BY compression"
            )
            ticks_compression = {row[0]: row[1] for row in cursor.fetchall()}

            return {
                "db_path": str(self.db_path),
                "bars_count": bars_count,
                "ticks_count": ticks_count,
                "bars_stocks": bars_stocks,
                "ticks_stocks": ticks_stocks,
                "bars_compression": bars_compression,
                "ticks_compression": ticks_compression,
                "default_compression": self.compression.value,
            }

    def get_compression_stats(self) -> dict:
        """获取压缩统计信息

        Returns:
            包含压缩前后数据大小对比的字典
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 计算bars的总数据大小（近似）
            cursor.execute("SELECT SUM(LENGTH(data)) FROM bars")
            bars_compressed_size = cursor.fetchone()[0] or 0

            cursor.execute(
                """
                SELECT SUM(LENGTH(data)) FROM bars WHERE compression = 'none'
                """
            )
            bars_uncompressed_size = cursor.fetchone()[0] or 0

            # 计算ticks的总数据大小（近似）
            cursor.execute("SELECT SUM(LENGTH(data)) FROM ticks")
            ticks_compressed_size = cursor.fetchone()[0] or 0

            cursor.execute(
                """
                SELECT SUM(LENGTH(data)) FROM ticks WHERE compression = 'none'
                """
            )
            ticks_uncompressed_size = cursor.fetchone()[0] or 0

            total_compressed = bars_compressed_size + ticks_compressed_size
            total_uncompressed = bars_uncompressed_size + ticks_uncompressed_size

            compression_ratio = (
                (total_compressed / total_uncompressed * 100)
                if total_uncompressed > 0
                else 0
            )

            return {
                "bars_compressed_bytes": bars_compressed_size,
                "bars_uncompressed_bytes": bars_uncompressed_size,
                "ticks_compressed_bytes": ticks_compressed_size,
                "ticks_uncompressed_bytes": ticks_uncompressed_size,
                "total_compressed_bytes": total_compressed,
                "total_uncompressed_bytes": total_uncompressed,
                "compression_ratio_percent": round(compression_ratio, 2),
            }

    def get_cache_stats(self) -> dict:
        """获取详细的缓存统计信息

        Returns:
            包含详细缓存统计信息的字典，包括:
            - 数据库统计
            - 内存LRU缓存统计
            - 访问统计
            - 元数据信息
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 基础统计
            cursor.execute("SELECT COUNT(*) FROM bars")
            bars_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM ticks")
            ticks_count = cursor.fetchone()[0]

            # 获取每只股票的数据统计
            cursor.execute("""
                SELECT code, market, data_type, last_updated, earliest_date, latest_date, record_count
                FROM cache_metadata
                ORDER BY code, market, data_type
            """)
            metadata_rows = cursor.fetchall()

            stock_stats = []
            for row in metadata_rows:
                stock_stats.append(
                    {
                        "code": row["code"],
                        "market": row["market"],
                        "data_type": row["data_type"],
                        "last_updated": row["last_updated"],
                        "earliest_date": row["earliest_date"],
                        "latest_date": row["latest_date"],
                        "record_count": row["record_count"],
                        "is_expired": self._is_data_expired(
                            row["code"], row["market"], row["data_type"]
                        ),
                    }
                )

        # 内存LRU缓存统计
        with self._cache_lock:
            memory_cache_size = len(self._memory_cache)
            memory_cache_keys = list(self._memory_cache.keys())

            # 访问统计
            access_stats = []
            for key, entry in self._access_stats.items():
                access_stats.append(
                    {
                        "key": key,
                        "access_count": entry.access_count,
                        "last_accessed": (
                            entry.last_accessed.isoformat()
                            if entry.last_accessed
                            else None
                        ),
                        "created_at": entry.timestamp.isoformat(),
                    }
                )

        return {
            "db_path": str(self.db_path),
            "db_stats": {
                "bars_count": bars_count,
                "ticks_count": ticks_count,
                "total_count": bars_count + ticks_count,
            },
            "memory_cache": {
                "size": memory_cache_size,
                "max_size": self.max_memory_cache_size,
                "utilization": (
                    memory_cache_size / self.max_memory_cache_size
                    if self.max_memory_cache_size > 0
                    else 0
                ),
                "keys": memory_cache_keys,
            },
            "ttl_config": {
                "default_ttl_seconds": self.default_ttl,
                "default_ttl_human": (
                    f"{self.default_ttl} seconds"
                    if self.default_ttl
                    else "No expiration"
                ),
            },
            "stock_stats": stock_stats,
            "access_stats": access_stats,
        }

    def get_data_date_range(
        self, code: str, market: str, data_type: str = "bars"
    ) -> Tuple[Optional[datetime], Optional[datetime]]:
        """获取本地缓存中指定股票的数据日期范围

        Args:
            code: 股票代码
            market: 市场代码
            data_type: 数据类型，'bars' 或 'ticks'

        Returns:
            (最早日期, 最新日期) 的元组，如果没有数据则返回 (None, None)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT earliest_date, latest_date FROM cache_metadata
                WHERE code = ? AND market = ? AND data_type = ?
                """,
                (code, market, data_type),
            )
            row = cursor.fetchone()

            if row is None:
                return None, None

            earliest = (
                datetime.fromisoformat(row["earliest_date"])
                if row["earliest_date"]
                else None
            )
            latest = (
                datetime.fromisoformat(row["latest_date"])
                if row["latest_date"]
                else None
            )
            return earliest, latest

    def get_missing_date_ranges(
        self,
        code: str,
        market: str,
        start_date: datetime,
        end_date: datetime,
        data_type: str = "bars",
    ) -> List[Tuple[datetime, datetime]]:
        """计算需要增量下载的日期范围

        对比本地缓存的数据日期范围和请求的范围，返回需要下载的缺失区间。

        Args:
            code: 股票代码
            market: 市场代码
            start_date: 请求的开始日期
            end_date: 请求的结束日期
            data_type: 数据类型，'bars' 或 'ticks'

        Returns:
            需要下载的日期范围列表，每个元素为 (start, end) 元组
        """
        cached_earliest, cached_latest = self.get_data_date_range(
            code, market, data_type
        )

        # 如果没有缓存数据，需要下载全部
        if cached_earliest is None or cached_latest is None:
            return [(start_date, end_date)]

        missing_ranges = []

        # 检查是否需要下载更早的数据
        if start_date < cached_earliest:
            missing_ranges.append((start_date, cached_earliest))

        # 检查是否需要下载更新的数据
        if end_date > cached_latest:
            missing_ranges.append((cached_latest, end_date))

        return missing_ranges

    def invalidate_expired_data(
        self, data_type: Optional[str] = None
    ) -> int:
        """清理过期的缓存数据

        Args:
            data_type: 数据类型过滤，'bars'、'ticks' 或 None(全部)

        Returns:
            删除的数据条数
        """
        if self.default_ttl is None:
            return 0

        expiry_threshold = (
            datetime.now() - timedelta(seconds=self.default_ttl)
        ).isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            total_deleted = 0

            if data_type is None or data_type == "bars":
                cursor.execute(
                    "DELETE FROM bars WHERE updated_at < ?",
                    (expiry_threshold,),
                )
                total_deleted += cursor.rowcount

            if data_type is None or data_type == "ticks":
                cursor.execute(
                    "DELETE FROM ticks WHERE updated_at < ?",
                    (expiry_threshold,),
                )
                total_deleted += cursor.rowcount

            # 清理相关的元数据
            cursor.execute(
                "DELETE FROM cache_metadata WHERE last_updated < ?",
                (expiry_threshold,),
            )

            return total_deleted

    def clear_memory_cache(self) -> int:
        """清空内存LRU缓存

        Returns:
            清空的条目数
        """
        with self._cache_lock:
            count = len(self._memory_cache)
            self._memory_cache.clear()
            self._access_stats.clear()
            return count

    def get_lru_cache_info(self) -> dict:
        """获取LRU缓存信息（向后兼容functools.lru_cache风格）

        Returns:
            包含LRU缓存统计信息的字典
        """
        with self._cache_lock:
            return {
                "hits": sum(
                    1 for e in self._access_stats.values() if e.access_count > 1
                ),
                "misses": sum(
                    1 for e in self._access_stats.values() if e.access_count == 1
                ),
                "maxsize": self.max_memory_cache_size,
                "currsize": len(self._memory_cache),
            }
