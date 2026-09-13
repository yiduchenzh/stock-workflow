"""
数据导出模块

支持将K线数据、分笔数据导出为Parquet、CSV、Excel等格式，
以及转换为Pandas DataFrame格式。
"""

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Union

from data.tdxapi.models import Bar, Tick

if TYPE_CHECKING:
    import pandas as pd


def _bars_to_records(bars: List[Bar]) -> List[dict]:
    """将Bar对象列表转换为字典列表

    Args:
        bars: K线数据列表

    Returns:
        字典列表，每个字典代表一条K线记录
    """
    return [
        {
            "code": bar.code,
            "market": bar.market,
            "datetime": bar.datetime,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "amount": bar.amount,
        }
        for bar in bars
    ]


def _ticks_to_records(ticks: List[Tick]) -> List[dict]:
    """将Tick对象列表转换为字典列表

    Args:
        ticks: 分笔数据列表

    Returns:
        字典列表，每个字典代表一条分笔记录
    """
    return [
        {
            "code": tick.code,
            "market": tick.market,
            "time": tick.time,
            "price": tick.price,
            "volume": tick.volume,
            "amount": tick.amount,
            "direction": tick.direction,
        }
        for tick in ticks
    ]


def to_dataframe(
    data: Union[List[Bar], List[Tick]],
) -> "pd.DataFrame":
    """将数据转换为Pandas DataFrame

    Args:
        data: K线数据列表(Bar)或分笔数据列表(Tick)

    Returns:
        Pandas DataFrame对象

    Raises:
        ImportError: 如果未安装pandas
        ValueError: 如果数据为空列表或数据类型不支持

    Example:
        >>> bars = cache.get_bars("600519", "SH")
        >>> df = to_dataframe(bars)
        >>> print(df.head())
    """
    try:
        import pandas as pd
    except ImportError as e:
        raise ImportError(
            "导出DataFrame需要安装pandas: pip install pandas"
        ) from e

    if not data:
        raise ValueError("数据不能为空列表")

    # 根据数据类型选择转换函数
    if isinstance(data[0], Bar):
        records = _bars_to_records(data)
    elif isinstance(data[0], Tick):
        records = _ticks_to_records(data)
    else:
        raise ValueError(
            f"不支持的数据类型: {type(data[0])}. 只支持Bar或Tick列表"
        )

    return pd.DataFrame(records)


def to_parquet(
    data: Union[List[Bar], List[Tick]],
    filepath: Union[str, Path],
    compression: str = "zstd",
    **kwargs,
) -> Path:
    """将数据导出为Parquet格式

    Args:
        data: K线数据列表(Bar)或分笔数据列表(Tick)
        filepath: 输出文件路径
        compression: 压缩算法，可选 "zstd"(默认), "snappy", "gzip", "brotli", "none"
        **kwargs: 传递给pandas.DataFrame.to_parquet的额外参数

    Returns:
        导出文件的Path对象

    Raises:
        ImportError: 如果未安装pandas或pyarrow
        ValueError: 如果数据为空列表或数据类型不支持

    Example:
        >>> bars = cache.get_bars("600519", "SH")
        >>> to_parquet(bars, "600519_bars.parquet")
        PosixPath('600519_bars.parquet')

        >>> ticks = cache.get_ticks("000001", "SZ")
        >>> to_parquet(ticks, "000001_ticks.parquet", compression="snappy")
    """
    try:
        import pandas as pd
        import pyarrow  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "导出Parquet需要安装pandas和pyarrow: pip install pandas pyarrow"
        ) from e

    if not data:
        raise ValueError("数据不能为空列表")

    filepath = Path(filepath)

    # 确保父目录存在
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # 转换为DataFrame并导出
    df = to_dataframe(data)
    df.to_parquet(filepath, compression=compression, **kwargs)

    return filepath


def to_csv(
    data: Union[List[Bar], List[Tick]],
    filepath: Union[str, Path],
    index: bool = False,
    encoding: str = "utf-8-sig",
    **kwargs,
) -> Path:
    """将数据导出为CSV格式

    Args:
        data: K线数据列表(Bar)或分笔数据列表(Tick)
        filepath: 输出文件路径
        index: 是否包含行索引，默认为False
        encoding: 文件编码，默认为"utf-8-sig"(带BOM，Excel兼容)
        **kwargs: 传递给pandas.DataFrame.to_csv的额外参数

    Returns:
        导出文件的Path对象

    Raises:
        ImportError: 如果未安装pandas
        ValueError: 如果数据为空列表或数据类型不支持

    Example:
        >>> bars = cache.get_bars("600519", "SH")
        >>> to_csv(bars, "600519_bars.csv")
        PosixPath('600519_bars.csv')
    """
    try:
        import pandas as pd
    except ImportError as e:
        raise ImportError(
            "导出CSV需要安装pandas: pip install pandas"
        ) from e

    if not data:
        raise ValueError("数据不能为空列表")

    filepath = Path(filepath)

    # 确保父目录存在
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # 转换为DataFrame并导出
    df = to_dataframe(data)
    df.to_csv(filepath, index=index, encoding=encoding, **kwargs)

    return filepath


def to_excel(
    data: Union[List[Bar], List[Tick]],
    filepath: Union[str, Path],
    sheet_name: str = "Sheet1",
    index: bool = False,
    **kwargs,
) -> Path:
    """将数据导出为Excel格式

    Args:
        data: K线数据列表(Bar)或分笔数据列表(Tick)
        filepath: 输出文件路径
        sheet_name: 工作表名称，默认为"Sheet1"
        index: 是否包含行索引，默认为False
        **kwargs: 传递给pandas.DataFrame.to_excel的额外参数

    Returns:
        导出文件的Path对象

    Raises:
        ImportError: 如果未安装pandas或openpyxl
        ValueError: 如果数据为空列表或数据类型不支持

    Example:
        >>> bars = cache.get_bars("600519", "SH")
        >>> to_excel(bars, "600519_bars.xlsx")
        PosixPath('600519_bars.xlsx')
    """
    try:
        import pandas as pd
    except ImportError as e:
        raise ImportError(
            "导出Excel需要安装pandas: pip install pandas"
        ) from e

    try:
        import openpyxl  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "导出Excel需要安装openpyxl: pip install openpyxl"
        ) from e

    if not data:
        raise ValueError("数据不能为空列表")

    filepath = Path(filepath)

    # 确保父目录存在
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # 转换为DataFrame并导出
    df = to_dataframe(data)
    df.to_excel(filepath, sheet_name=sheet_name, index=index, **kwargs)

    return filepath


def read_parquet(
    filepath: Union[str, Path],
    data_type: str = "bar",
) -> Union[List[Bar], List[Tick]]:
    """从Parquet文件读取数据

    Args:
        filepath: Parquet文件路径
        data_type: 数据类型，"bar"表示K线数据，"tick"表示分笔数据

    Returns:
        Bar列表或Tick列表

    Raises:
        ImportError: 如果未安装pandas或pyarrow
        ValueError: 如果data_type不支持

    Example:
        >>> bars = read_parquet("600519_bars.parquet", data_type="bar")
        >>> ticks = read_parquet("000001_ticks.parquet", data_type="tick")
    """
    try:
        import pandas as pd
        import pyarrow  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "读取Parquet需要安装pandas和pyarrow: pip install pandas pyarrow"
        ) from e

    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    df = pd.read_parquet(filepath)

    if data_type == "bar":
        return [
            Bar(
                code=row["code"],
                market=row["market"],
                datetime=row["datetime"]
                if isinstance(row["datetime"], datetime)
                else pd.to_datetime(row["datetime"]),
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                amount=row["amount"],
            )
            for _, row in df.iterrows()
        ]
    elif data_type == "tick":
        return [
            Tick(
                code=row["code"],
                market=row["market"],
                time=row["time"],
                price=row["price"],
                volume=row["volume"],
                amount=row["amount"],
                direction=row["direction"],
            )
            for _, row in df.iterrows()
        ]
    else:
        raise ValueError(f"不支持的数据类型: {data_type}. 可选: 'bar', 'tick'")
