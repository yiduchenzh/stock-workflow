"""
技术指标计算模块

提供常用的技术分析指标计算功能，包括成交量指标、移动平均线等。
"""

from typing import List, Optional, Union, Dict
from dataclasses import dataclass

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

from data.tdxapi.models import Bar


# 类型别名
PriceData = Union[List[float], List[Bar]]


def _extract_prices(data: PriceData, price_type: str = "close") -> List[float]:
    """
    从 Bar 列表或价格列表中提取价格数据。

    Args:
        data: Bar 列表或价格列表
        price_type: 价格类型，可选 "open", "high", "low", "close"

    Returns:
        价格列表
    """
    if not data:
        return []

    if isinstance(data[0], Bar):
        if price_type == "open":
            return [b.open for b in data]  # type: ignore
        elif price_type == "high":
            return [b.high for b in data]  # type: ignore
        elif price_type == "low":
            return [b.low for b in data]  # type: ignore
        else:  # close
            return [b.close for b in data]  # type: ignore
    else:
        return data  # type: ignore


def vol(bars: List[Bar]) -> List[int]:
    """
    计算成交量 (Volume)

    成交量指标直接返回每根K线的成交量数据。

    Args:
        bars: K线数据列表

    Returns:
        成交量列表，与输入bars长度相同

    Example:
        >>> bars = [Bar(..., volume=1000, ...), Bar(..., volume=2000, ...)]
        >>> vol(bars)
        [1000, 2000]
    """
    return [bar.volume for bar in bars]


def obv(bars: List[Bar]) -> List[int]:
    """
    计算能量潮指标 (On Balance Volume, OBV)

    OBV指标通过统计成交量变动的趋势来推测股价趋势。
    计算公式：
    - 如果当日收盘价 > 前日收盘价，则 OBV = 前日OBV + 当日成交量
    - 如果当日收盘价 < 前日收盘价，则 OBV = 前日OBV - 当日成交量
    - 如果当日收盘价 = 前日收盘价，则 OBV = 前日OBV

    Args:
        bars: K线数据列表，按时间顺序排列（从早到晚）

    Returns:
        OBV值列表，与输入bars长度相同。第一个值为第一个bar的成交量。

    Example:
        >>> bars = [
        ...     Bar(..., close=10.0, volume=1000, ...),
        ...     Bar(..., close=11.0, volume=2000, ...),  # 上涨
        ...     Bar(..., close=10.5, volume=1500, ...),  # 下跌
        ... ]
        >>> obv(bars)
        [1000, 3000, 1500]
    """
    if not bars:
        return []

    result: List[int] = [bars[0].volume]

    for i in range(1, len(bars)):
        prev_close = bars[i - 1].close
        curr_close = bars[i].close
        curr_volume = bars[i].volume

        if curr_close > prev_close:
            # 上涨，累加成交量
            result.append(result[-1] + curr_volume)
        elif curr_close < prev_close:
            # 下跌，累减成交量
            result.append(result[-1] - curr_volume)
        else:
            # 平盘，OBV不变
            result.append(result[-1])

    return result


def vol_ma(bars: List[Bar], period: int) -> List[Optional[float]]:
    """
    计算成交量移动平均线 (Volume Moving Average)

    Args:
        bars: K线数据列表
        period: 计算周期，必须大于0

    Returns:
        成交量移动平均值列表，与输入bars长度相同。
        前period-1个值为None（因为数据不足），从第period个值开始为有效平均值。

    Raises:
        ValueError: 当period <= 0时

    Example:
        >>> bars = [Bar(..., volume=1000, ...), Bar(..., volume=2000, ...), ...]
        >>> vol_ma(bars, 5)  # 5日成交量均线
        [None, None, None, None, 1500.0, ...]
    """
    if period <= 0:
        raise ValueError(f"period must be positive, got {period}")

    if not bars:
        return []

    volumes = [bar.volume for bar in bars]
    result: List[Optional[float]] = []

    for i in range(len(volumes)):
        if i < period - 1:
            # 数据不足，返回None
            result.append(None)
        else:
            # 计算移动平均
            window = volumes[i - period + 1:i + 1]
            result.append(sum(window) / period)

    return result


def ma(data: PriceData, period: int, price_type: str = "close") -> List[Optional[float]]:
    """
    计算简单移动平均线 (Simple Moving Average, SMA)。

    对于数据不足 period 个的位置，返回 None。

    Args:
        data: Bar 列表或价格列表
        period: 移动平均周期
        price_type: 价格类型，可选 "open", "high", "low", "close"（仅对 Bar 列表有效）

    Returns:
        移动平均线值列表，长度与输入相同，前 period-1 个为 None

    Example:
        >>> prices = [10.0, 11.0, 12.0, 13.0, 14.0]
        >>> ma(prices, 3)
        [None, None, 11.0, 12.0, 13.0]
    """
    if period <= 0:
        raise ValueError(f"period must be positive, got {period}")

    prices = _extract_prices(data, price_type)
    n = len(prices)

    if n == 0:
        return []

    # 纯 Python 实现（与 numpy 实现结果一致且更易理解）
    result: List[Optional[float]] = []
    for i in range(n):
        if i < period - 1:
            result.append(None)
        else:
            window = prices[i - period + 1:i + 1]
            result.append(sum(window) / period)
    return result


def ema(data: PriceData, period: int, price_type: str = "close") -> List[Optional[float]]:
    """
    计算指数移动平均线 (Exponential Moving Average, EMA)。

    EMA 公式: EMA_today = alpha * price_today + (1 - alpha) * EMA_yesterday
    其中 alpha = 2 / (period + 1)

    对于第一个数据点，使用第一个价格作为初始值。

    Args:
        data: Bar 列表或价格列表
        period: 移动平均周期
        price_type: 价格类型，可选 "open", "high", "low", "close"（仅对 Bar 列表有效）

    Returns:
        指数移动平均线值列表，长度与输入相同

    Example:
        >>> prices = [10.0, 11.0, 12.0, 13.0, 14.0]
        >>> ema(prices, 3)
        [10.0, 10.5, 11.25, 12.125, 13.0625]
    """
    if period <= 0:
        raise ValueError(f"period must be positive, got {period}")

    prices = _extract_prices(data, price_type)
    n = len(prices)

    if n == 0:
        return []

    alpha = 2.0 / (period + 1)
    result: List[Optional[float]] = []

    if HAS_NUMPY:
        # 使用 numpy 高效计算
        prices_arr = np.array(prices, dtype=np.float64)
        ema_values = np.zeros(n, dtype=np.float64)
        # 第一个值使用第一个价格
        ema_values[0] = prices_arr[0]
        for i in range(1, n):
            ema_values[i] = alpha * prices_arr[i] + (1 - alpha) * ema_values[i - 1]
        return ema_values.tolist()
    else:
        # 纯 Python 实现
        # 第一个值使用第一个价格
        result.append(prices[0])
        prev_ema = prices[0]
        for i in range(1, n):
            curr_ema = alpha * prices[i] + (1 - alpha) * prev_ema
            result.append(curr_ema)
            prev_ema = curr_ema
        return result


def wma(data: PriceData, period: int, price_type: str = "close") -> List[Optional[float]]:
    """
    计算加权移动平均线 (Weighted Moving Average, WMA)。

    权重线性递减，最近的数据权重最高。
    权重公式: weight_i = i / sum(1..period)

    Args:
        data: Bar 列表或价格列表
        period: 移动平均周期
        price_type: 价格类型，可选 "open", "high", "low", "close"（仅对 Bar 列表有效）

    Returns:
        加权移动平均线值列表，长度与输入相同，前 period-1 个为 None

    Example:
        >>> prices = [10.0, 11.0, 12.0, 13.0, 14.0]
        >>> wma(prices, 3)
        [None, None, 11.166..., 12.166..., 13.166...]
    """
    if period <= 0:
        raise ValueError(f"period must be positive, got {period}")

    prices = _extract_prices(data, price_type)
    n = len(prices)

    if n == 0:
        return []

    # 计算权重: 1, 2, ..., period（最近的数据权重最高）
    # 窗口中第一个元素（最旧）权重为1，最后一个元素（最新）权重为period
    weights = list(range(1, period + 1))
    weight_sum = sum(weights)

    result: List[Optional[float]] = []
    for i in range(n):
        if i < period - 1:
            result.append(None)
        else:
            window = prices[i - period + 1:i + 1]
            # zip 会自动按顺序配对：window[0]（最旧）对应 weights[0]=1
            # window[-1]（最新）对应 weights[-1]=period
            weighted_sum = sum(p * w for p, w in zip(window, weights))
            result.append(weighted_sum / weight_sum)
    return result


@dataclass
class MA:
    """
    移动平均线指标类。

    支持常用的移动平均线周期: MA5, MA10, MA20, MA60, MA120, MA250
    支持 SMA(简单移动平均) 和 EMA(指数移动平均) 两种计算方式。

    Attributes:
        period: 移动平均周期
        values: 计算出的移动平均数值列表
        ma_type: 移动平均类型，"sma" 或 "ema"

    Example:
        >>> prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0]
        >>> ma5 = MA.calculate(prices, 5)
        >>> print(ma5.values)
        [None, None, None, None, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0]
    """

    period: int
    values: List[Optional[float]]
    ma_type: str = "sma"

    @classmethod
    def calculate(
        cls,
        data: PriceData,
        period: int,
        ma_type: str = "sma",
        price_type: str = "close"
    ) -> "MA":
        """
        计算移动平均线。

        Args:
            data: Bar 列表或价格列表
            period: 移动平均周期
            ma_type: 移动平均类型，"sma"(简单移动平均) 或 "ema"(指数移动平均)
            price_type: 价格类型，可选 "open", "high", "low", "close"（仅对 Bar 列表有效）

        Returns:
            MA 实例

        Raises:
            ValueError: 当 ma_type 不是 "sma" 或 "ema" 时
        """
        if ma_type not in ("sma", "ema"):
            raise ValueError(f"ma_type must be 'sma' or 'ema', got '{ma_type}'")

        if ma_type == "sma":
            values = ma(data, period, price_type)
        else:
            values = ema(data, period, price_type)

        return cls(period=period, values=values, ma_type=ma_type)

    @classmethod
    def ma5(cls, data: PriceData, ma_type: str = "sma", price_type: str = "close") -> "MA":
        """计算 MA5"""
        return cls.calculate(data, 5, ma_type, price_type)

    @classmethod
    def ma10(cls, data: PriceData, ma_type: str = "sma", price_type: str = "close") -> "MA":
        """计算 MA10"""
        return cls.calculate(data, 10, ma_type, price_type)

    @classmethod
    def ma20(cls, data: PriceData, ma_type: str = "sma", price_type: str = "close") -> "MA":
        """计算 MA20"""
        return cls.calculate(data, 20, ma_type, price_type)

    @classmethod
    def ma30(cls, data: PriceData, ma_type: str = "sma", price_type: str = "close") -> "MA":
        """计算 MA30"""
        return cls.calculate(data, 30, ma_type, price_type)

    @classmethod
    def ma60(cls, data: PriceData, ma_type: str = "sma", price_type: str = "close") -> "MA":
        """计算 MA60"""
        return cls.calculate(data, 60, ma_type, price_type)

    @classmethod
    def ma120(cls, data: PriceData, ma_type: str = "sma", price_type: str = "close") -> "MA":
        """计算 MA120"""
        return cls.calculate(data, 120, ma_type, price_type)

    @classmethod
    def ma250(cls, data: PriceData, ma_type: str = "sma", price_type: str = "close") -> "MA":
        """计算 MA250 (年线)"""
        return cls.calculate(data, 250, ma_type, price_type)

    def __len__(self) -> int:
        return len(self.values)

    def __getitem__(self, index: int) -> Optional[float]:
        return self.values[index]

    def __repr__(self) -> str:
        non_none_count = sum(1 for v in self.values if v is not None)
        return f"MA({self.period}, {self.ma_type}, {non_none_count}/{len(self.values)} values)"

    def last(self) -> Optional[float]:
        """
        获取最新的移动平均数值。

        Returns:
            最新的 MA 值，如果没有有效值则返回 None
        """
        for v in reversed(self.values):
            if v is not None:
                return v
        return None

    def valid_values(self) -> List[float]:
        """
        获取所有有效的（非 None）移动平均数值。

        Returns:
            有效 MA 值列表
        """
        return [v for v in self.values if v is not None]


def calculate_all_ma(
    data: PriceData,
    periods: Optional[List[int]] = None,
    ma_type: str = "sma",
    price_type: str = "close"
) -> dict:
    """
    批量计算多个周期的移动平均线。

    Args:
        data: Bar 列表或价格列表
        periods: 周期列表，默认为 [5, 10, 20, 60, 120, 250]
        ma_type: 移动平均类型，"sma" 或 "ema"
        price_type: 价格类型，可选 "open", "high", "low", "close"（仅对 Bar 列表有效）

    Returns:
        字典，键为周期，值为 MA 实例

    Example:
        >>> prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
        >>> result = calculate_all_ma(prices)
        >>> print(result[5].values)
        [None, None, None, None, 12.0, 13.0]
    """
    if periods is None:
        periods = [5, 10, 20, 60, 120, 250]

    return {
        period: MA.calculate(data, period, ma_type, price_type)
        for period in periods
    }


def std(data: PriceData, period: int, price_type: str = "close") -> List[Optional[float]]:
    """
    计算标准差 (Standard Deviation)。

    使用总体标准差公式（除以 n 而不是 n-1）。

    Args:
        data: Bar 列表或价格列表
        period: 计算周期
        price_type: 价格类型，可选 "open", "high", "low", "close"（仅对 Bar 列表有效）

    Returns:
        标准差列表，长度与输入相同，前 period-1 个为 None

    Example:
        >>> prices = [10.0, 11.0, 12.0, 13.0, 14.0]
        >>> std(prices, 3)
        [None, None, 0.816..., 0.816..., 0.816...]
    """
    if period <= 0:
        raise ValueError(f"period must be positive, got {period}")

    prices = _extract_prices(data, price_type)
    n = len(prices)

    if n == 0:
        return []

    result: List[Optional[float]] = []
    for i in range(n):
        if i < period - 1:
            result.append(None)
        else:
            window = prices[i - period + 1:i + 1]
            mean = sum(window) / period
            variance = sum((p - mean) ** 2 for p in window) / period
            result.append(variance ** 0.5)


    return result


def rsi(data: PriceData, period: int = 14, price_type: str = "close") -> List[Optional[float]]:
    """
    计算相对强弱指标 (Relative Strength Index, RSI)。

    RSI 是衡量价格变动速度和变化的动量指标，取值范围在 0-100 之间。
    通常使用 14 日作为默认周期，也可以使用 6、12、24 等周期。

    计算公式：
    - 上涨幅度 = max(今日收盘 - 昨日收盘, 0)
    - 下跌幅度 = max(昨日收盘 - 今日收盘, 0)
    - RS = 平均上涨幅度 / 平均下跌幅度
    - RSI = 100 - (100 / (1 + RS))

    使用平滑移动平均计算平均上涨/下跌幅度（Wilder's smoothing）。

    Args:
        data: Bar 列表或价格列表
        period: RSI 计算周期，默认为 14
        price_type: 价格类型，可选 "open", "high", "low", "close"（仅对 Bar 列表有效）

    Returns:
        RSI 值列表，长度与输入相同，前 period 个为 None（数据不足）

    Raises:
        ValueError: 当 period <= 0 时

    Example:
        >>> prices = [10.0, 11.0, 12.0, 11.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0,
        ...           14.0, 13.0, 14.0, 15.0, 16.0, 15.0, 14.0, 15.0, 16.0, 17.0]
        >>> rsi(prices, 14)
        [None, None, None, None, None, None, None, None, None, None,
         None, None, None, None, 60.0, ...]
    """
    if period <= 0:
        raise ValueError(f"period must be positive, got {period}")

    prices = _extract_prices(data, price_type)
    n = len(prices)

    if n == 0:
        return []

    if n < period + 1:
        # 至少需要 period + 1 个价格才能计算 RSI
        return [None] * n

    # 计算价格变动
    deltas = [prices[i] - prices[i - 1] for i in range(1, n)]

    # 分离上涨和下跌
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]

    result: List[Optional[float]] = [None] * n

    # 第一个有效 RSI 值在索引 period 处（需要 period 个变化值）
    # 计算初始平均上涨和下跌（使用简单平均）
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # 计算第一个 RSI 值
    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - (100.0 / (1.0 + rs))

    # 使用 Wilder's smoothing 计算后续 RSI
    alpha = 1.0 / period  # Wilder's smoothing factor

    for i in range(period + 1, n):
        # 使用平滑移动平均更新 avg_gain 和 avg_loss
        avg_gain = alpha * gains[i - 1] + (1 - alpha) * avg_gain
        avg_loss = alpha * losses[i - 1] + (1 - alpha) * avg_loss

        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100.0 - (100.0 / (1.0 + rs))

    return result


def rsi_multi(data: PriceData, periods: List[int] = None, price_type: str = "close") -> Dict[int, List[Optional[float]]]:
    """
    同时计算多个周期的 RSI 指标。

    常用于同时计算 RSI6、RSI12、RSI24 等多个周期，方便对比分析。

    Args:
        data: Bar 列表或价格列表
        periods: RSI 周期列表，默认为 [6, 12, 24]
        price_type: 价格类型，可选 "open", "high", "low", "close"（仅对 Bar 列表有效）

    Returns:
        字典，键为周期，值为对应周期的 RSI 值列表

    Example:
        >>> prices = [10.0, 11.0, 12.0, 11.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0,
        ...           14.0, 13.0, 14.0, 15.0, 16.0, 15.0, 14.0, 15.0, 16.0, 17.0,
        ...           18.0, 19.0, 20.0, 21.0, 22.0]
        >>> result = rsi_multi(prices, [6, 12, 24])
        >>> print(result[6])   # RSI6
        >>> print(result[12])  # RSI12
        >>> print(result[24])  # RSI24
    """
    if periods is None:
        periods = [6, 12, 24]

    return {
        period: rsi(data, period, price_type)
        for period in periods
    }


@dataclass
class RSI:
    """
    相对强弱指标 (RSI) 类。

    RSI 是衡量价格变动速度和变化的动量指标，取值范围在 0-100 之间。
    常用周期有 RSI6、RSI12、RSI14、RSI24 等。

    Attributes:
        period: RSI 计算周期
        values: 计算出的 RSI 数值列表

    Example:
        >>> prices = list(range(1, 50))  # 持续上涨
        >>> rsi14 = RSI.calculate(prices, 14)
        >>> print(rsi14.last())  # 接近 100
    """

    period: int
    values: List[Optional[float]]

    @classmethod
    def calculate(cls, data: PriceData, period: int = 14, price_type: str = "close") -> "RSI":
        """
        计算 RSI 指标。

        Args:
            data: Bar 列表或价格列表
            period: RSI 计算周期，默认为 14
            price_type: 价格类型，可选 "open", "high", "low", "close"（仅对 Bar 列表有效）

        Returns:
            RSI 实例
        """
        values = rsi(data, period, price_type)
        return cls(period=period, values=values)

    @classmethod
    def rsi6(cls, data: PriceData, price_type: str = "close") -> "RSI":
        """计算 RSI6"""
        return cls.calculate(data, 6, price_type)

    @classmethod
    def rsi12(cls, data: PriceData, price_type: str = "close") -> "RSI":
        """计算 RSI12"""
        return cls.calculate(data, 12, price_type)

    @classmethod
    def rsi14(cls, data: PriceData, price_type: str = "close") -> "RSI":
        """计算 RSI14（默认周期）"""
        return cls.calculate(data, 14, price_type)

    @classmethod
    def rsi24(cls, data: PriceData, price_type: str = "close") -> "RSI":
        """计算 RSI24"""
        return cls.calculate(data, 24, price_type)

    def __len__(self) -> int:
        return len(self.values)

    def __getitem__(self, index: int) -> Optional[float]:
        return self.values[index]

    def __repr__(self) -> str:
        non_none_count = sum(1 for v in self.values if v is not None)
        return f"RSI({self.period}, {non_none_count}/{len(self.values)} values)"

    def last(self) -> Optional[float]:
        """
        获取最新的 RSI 数值。

        Returns:
            最新的 RSI 值，如果没有有效值则返回 None
        """
        for v in reversed(self.values):
            if v is not None:
                return v
        return None

    def valid_values(self) -> List[float]:
        """
        获取所有有效的（非 None）RSI 数值。

        Returns:
            有效 RSI 值列表
        """
        return [v for v in self.values if v is not None]

    def is_overbought(self, threshold: float = 70.0) -> Optional[bool]:
        """
        判断是否超买。

        Args:
            threshold: 超买阈值，默认为 70

        Returns:
            如果最新 RSI 值大于阈值返回 True，否则返回 False，无有效值返回 None
        """
        last_val = self.last()
        if last_val is None:
            return None
        return last_val > threshold

    def is_oversold(self, threshold: float = 30.0) -> Optional[bool]:
        """
        判断是否超卖。

        Args:
            threshold: 超卖阈值，默认为 30

        Returns:
            如果最新 RSI 值小于阈值返回 True，否则返回 False，无有效值返回 None
        """
        last_val = self.last()
        if last_val is None:
            return None
        return last_val < threshold


def macd(data: PriceData, fast: int = 12, slow: int = 26, signal: int = 9,
         price_type: str = "close") -> dict:
    """
    计算 MACD 指标 (Moving Average Convergence Divergence)。

    MACD 是一种趋势跟踪动量指标，显示两条移动平均线之间的关系。

    计算公式：
    - DIF = EMA(Close, fast) - EMA(Close, slow)
    - DEA = EMA(DIF, signal)
    - MACD = (DIF - DEA) * 2

    Args:
        data: Bar 列表或价格列表
        fast: 快速 EMA 周期，默认 12
        slow: 慢速 EMA 周期，默认 26
        signal: 信号线 EMA 周期，默认 9
        price_type: 价格类型，可选 "open", "high", "low", "close"（仅对 Bar 列表有效）

    Returns:
        字典，包含以下键：
        - "dif": DIF 线（快线）列表
        - "dea": DEA 线（慢线/信号线）列表
        - "macd": MACD 柱状图列表
        - "histogram": MACD 柱状图列表（与 macd 相同，别名）

    Raises:
        ValueError: 当 fast >= slow 时，或当任何周期 <= 0 时

    Example:
        >>> prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0,
        ...           20.0, 21.0, 22.0, 23.0, 24.0, 25.0, 26.0, 27.0, 28.0, 29.0,
        ...           30.0, 31.0, 32.0, 33.0, 34.0, 35.0, 36.0]
        >>> result = macd(prices, fast=12, slow=26, signal=9)
        >>> len(result["dif"]) == len(prices)
        True
    """
    if fast <= 0 or slow <= 0 or signal <= 0:
        raise ValueError(f"periods must be positive, got fast={fast}, slow={slow}, signal={signal}")

    if fast >= slow:
        raise ValueError(f"fast period must be less than slow period, got fast={fast}, slow={slow}")

    prices = _extract_prices(data, price_type)
    n = len(prices)

    if n == 0:
        return {"dif": [], "dea": [], "macd": [], "histogram": []}

    # 计算快速和慢速 EMA
    ema_fast = ema(prices, fast)
    ema_slow = ema(prices, slow)

    # 计算 DIF = EMA(fast) - EMA(slow)
    dif: List[Optional[float]] = []
    for f, s in zip(ema_fast, ema_slow):
        if f is not None and s is not None:
            dif.append(f - s)
        else:
            dif.append(None)

    # 计算 DEA = EMA(DIF, signal)
    # 过滤掉 None 值进行 EMA 计算
    valid_dif = [v for v in dif if v is not None]
    if len(valid_dif) == 0:
        dea: List[Optional[float]] = [None] * n
        macd_hist: List[Optional[float]] = [None] * n
    else:
        ema_dea_valid = ema(valid_dif, signal)

        # 将计算结果映射回原始长度（前面补 None）
        none_count = n - len(valid_dif)
        dea = [None] * none_count + ema_dea_valid

        # 计算 MACD 柱状图 = (DIF - DEA) * 2
        macd_hist = []
        for d, de in zip(dif, dea):
            if d is not None and de is not None:
                macd_hist.append((d - de) * 2)
            else:
                macd_hist.append(None)

    return {
        "dif": dif,
        "dea": dea,
        "macd": macd_hist,
        "histogram": macd_hist
    }


@dataclass
class BOLL:
    """
    布林带 (Bollinger Bands) 指标类。

    布林带由三条线组成：
    - 中轨 (MID): 简单移动平均线
    - 上轨 (UP): 中轨 + std_dev * 标准差
    - 下轨 (LOW): 中轨 - std_dev * 标准差

    Attributes:
        period: 计算周期（默认20）
        std_dev: 标准差倍数（默认2）
        up: 上轨值列表
        mid: 中轨值列表
        low: 下轨值列表

    Example:
        >>> bars = [Bar(...), Bar(...), ...]  # 至少20根K线
        >>> boll = BOLL.calculate(bars)
        >>> print(boll.up[-1], boll.mid[-1], boll.low[-1])
    """

    period: int
    std_dev: float
    up: List[Optional[float]]
    mid: List[Optional[float]]
    low: List[Optional[float]]

    @classmethod
    def calculate(
        cls,
        data: PriceData,
        period: int = 20,
        std_dev: float = 2.0,
        price_type: str = "close"
    ) -> "BOLL":
        """
        计算布林带指标。

        Args:
            data: Bar 列表或价格列表
            period: 计算周期，默认20
            std_dev: 标准差倍数，默认2.0
            price_type: 价格类型，可选 "open", "high", "low", "close"（仅对 Bar 列表有效）

        Returns:
            BOLL 实例

        Raises:
            ValueError: 当 period <= 0 或 std_dev <= 0 时

        Example:
            >>> prices = [10.0, 11.0, 12.0, ...]  # 至少20个价格
            >>> boll = BOLL.calculate(prices, period=20, std_dev=2)
        """
        if period <= 0:
            raise ValueError(f"period must be positive, got {period}")
        if std_dev <= 0:
            raise ValueError(f"std_dev must be positive, got {std_dev}")

        prices = _extract_prices(data, price_type)
        n = len(prices)

        if n == 0:
            return cls(period=period, std_dev=std_dev, up=[], mid=[], low=[])

        # 计算中轨（简单移动平均）
        mid_values = ma(prices, period, price_type)

        # 计算标准差
        std_values = std(prices, period, price_type)

        # 计算上下轨
        up_values: List[Optional[float]] = []
        low_values: List[Optional[float]] = []

        for i in range(n):
            if mid_values[i] is None or std_values[i] is None:
                up_values.append(None)
                low_values.append(None)
            else:
                mid_val = mid_values[i]  # type: ignore
                std_val = std_values[i]  # type: ignore
                up_values.append(mid_val + std_dev * std_val)
                low_values.append(mid_val - std_dev * std_val)

        return cls(
            period=period,
            std_dev=std_dev,
            up=up_values,
            mid=mid_values,
            low=low_values
        )

    def __len__(self) -> int:
        return len(self.mid)

    def __getitem__(self, index: int) -> tuple:
        """
        获取指定索引的布林带值。

        Returns:
            (up, mid, low) 元组
        """
        return (self.up[index], self.mid[index], self.low[index])

    def __repr__(self) -> str:
        non_none_count = sum(1 for v in self.mid if v is not None)
        return f"BOLL(period={self.period}, std_dev={self.std_dev}, {non_none_count}/{len(self.mid)} values)"

    def last(self) -> tuple:
        """
        获取最新的布林带数值。

        Returns:
            (up, mid, low) 元组，如果没有有效值则返回 (None, None, None)
        """
        for i in range(len(self.mid) - 1, -1, -1):
            if self.mid[i] is not None:
                return (self.up[i], self.mid[i], self.low[i])
        return (None, None, None)

    def bandwidth(self) -> List[Optional[float]]:
        """
        计算布林带宽度 (Bandwidth)。

        Bandwidth = (UP - LOW) / MID * 100%

        Returns:
            布林带宽度百分比列表
        """
        result: List[Optional[float]] = []
        for up, mid, low in zip(self.up, self.mid, self.low):
            if up is None or mid is None or low is None or mid == 0:
                result.append(None)
            else:
                result.append((up - low) / mid * 100)
        return result


def boll(data: PriceData, period: int = 20, std_dev: float = 2.0, price_type: str = "close") -> BOLL:
    """
    计算布林带指标 (Bollinger Bands)。

    布林带由三条线组成：
    - 中轨 (MID): 简单移动平均线 MA(Close, period)
    - 上轨 (UP): 中轨 + std_dev * STD(Close, period)
    - 下轨 (LOW): 中轨 - std_dev * STD(Close, period)

    Args:
        data: Bar 列表或价格列表
        period: 计算周期，默认20
        std_dev: 标准差倍数，默认2.0
        price_type: 价格类型，可选 "open", "high", "low", "close"（仅对 Bar 列表有效）

    Returns:
        BOLL 实例，包含 up, mid, low 三个序列

    Raises:
        ValueError: 当 period <= 0 或 std_dev <= 0 时

    Example:
        >>> prices = [10.0, 11.0, 12.0, 13.0, 14.0] * 5  # 25个价格
        >>> result = boll(prices, period=20, std_dev=2)
        >>> print(result.up[-1], result.mid[-1], result.low[-1])
    """
    return BOLL.calculate(data, period, std_dev, price_type)


def macd(data: PriceData, fast: int = 12, slow: int = 26, signal: int = 9,
         price_type: str = "close") -> dict:
    """
    计算 MACD 指标 (Moving Average Convergence Divergence)。

    MACD 是一种趋势跟踪动量指标，显示两条移动平均线之间的关系。

    计算公式：
    - DIF = EMA(Close, fast) - EMA(Close, slow)
    - DEA = EMA(DIF, signal)
    - MACD = (DIF - DEA) * 2

    Args:
        data: Bar 列表或价格列表
        fast: 快速 EMA 周期，默认 12
        slow: 慢速 EMA 周期，默认 26
        signal: 信号线 EMA 周期，默认 9
        price_type: 价格类型，可选 "open", "high", "low", "close"（仅对 Bar 列表有效）

    Returns:
        字典，包含以下键：
        - "dif": DIF 线（快线）列表
        - "dea": DEA 线（慢线/信号线）列表
        - "macd": MACD 柱状图列表
        - "histogram": MACD 柱状图列表（与 macd 相同，别名）

    Raises:
        ValueError: 当 fast >= slow 时，或当任何周期 <= 0 时

    Example:
        >>> prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0,
        ...           20.0, 21.0, 22.0, 23.0, 24.0, 25.0, 26.0, 27.0, 28.0, 29.0,
        ...           30.0, 31.0, 32.0, 33.0, 34.0, 35.0, 36.0]
        >>> result = macd(prices, fast=12, slow=26, signal=9)
        >>> len(result["dif"]) == len(prices)
        True
    """
    if fast <= 0 or slow <= 0 or signal <= 0:
        raise ValueError(f"periods must be positive, got fast={fast}, slow={slow}, signal={signal}")

    if fast >= slow:
        raise ValueError(f"fast period must be less than slow period, got fast={fast}, slow={slow}")

    prices = _extract_prices(data, price_type)
    n = len(prices)

    if n == 0:
        return {"dif": [], "dea": [], "macd": [], "histogram": []}

    # 计算快速和慢速 EMA
    ema_fast = ema(prices, fast)
    ema_slow = ema(prices, slow)

    # 计算 DIF = EMA(fast) - EMA(slow)
    dif: List[Optional[float]] = []
    for f, s in zip(ema_fast, ema_slow):
        if f is not None and s is not None:
            dif.append(f - s)
        else:
            dif.append(None)

    # 计算 DEA = EMA(DIF, signal)
    # 过滤掉 None 值进行 EMA 计算
    valid_dif = [v for v in dif if v is not None]
    if len(valid_dif) == 0:
        dea: List[Optional[float]] = [None] * n
        macd_hist: List[Optional[float]] = [None] * n
    else:
        ema_dea_valid = ema(valid_dif, signal)

        # 将计算结果映射回原始长度（前面补 None）
        none_count = n - len(valid_dif)
        dea = [None] * none_count + ema_dea_valid

        # 计算 MACD 柱状图 = (DIF - DEA) * 2
        macd_hist = []
        for d, de in zip(dif, dea):
            if d is not None and de is not None:
                macd_hist.append((d - de) * 2)
            else:
                macd_hist.append(None)

    return {
        "dif": dif,
        "dea": dea,
        "macd": macd_hist,
        "histogram": macd_hist
    }


def kdj(bars: List[Bar], n: int = 9, m1: int = 3, m2: int = 3) -> tuple:
    """
    计算 KDJ 随机指标 (Stochastic Oscillator)

    KDJ 是一种技术分析指标，用于判断超买超卖状态。

    计算公式：
    - RSV = (Close - LLV(Low, n)) / (HHV(High, n) - LLV(Low, n)) * 100
    - K = (2/3) * 前日K + (1/3) * RSV
    - D = (2/3) * 前日D + (1/3) * K
    - J = 3K - 2D

    其中：
    - LLV(Low, n): n日内最低价的最低值
    - HHV(High, n): n日内最高价的最高值
    - RSV: 未成熟随机值 (Raw Stochastic Value)

    初始值：K[0] = D[0] = 50 (当数据不足时)

    Args:
        bars: K线数据列表，按时间顺序排列（从早到晚）
        n: RSV计算周期，默认9
        m1: K值平滑系数，默认3（对应2/3权重）
        m2: D值平滑系数，默认3（对应2/3权重）

    Returns:
        三元组 (K, D, J)，每个都是与输入bars长度相同的列表。
        前n-1个值为None（因为数据不足计算RSV）。

    Raises:
        ValueError: 当n, m1, m2 <= 0时

    Example:
        >>> bars = [
        ...     Bar(..., high=11.0, low=9.0, close=10.0, ...),
        ...     Bar(..., high=12.0, low=10.0, close=11.0, ...),
        ...     # ... 至少9根K线
        ... ]
        >>> k, d, j = kdj(bars)
        >>> print(k[-1], d[-1], j[-1])  # 最新的KDJ值
    """
    if n <= 0 or m1 <= 0 or m2 <= 0:
        raise ValueError(f"n, m1, m2 must be positive, got n={n}, m1={m1}, m2={m2}")

    if not bars:
        return ([], [], [])

    if len(bars) < n:
        # 数据不足，返回全None
        none_list: List[Optional[float]] = [None] * len(bars)
        return (none_list.copy(), none_list.copy(), none_list.copy())

    # 提取价格数据
    closes = [bar.close for bar in bars]
    highs = [bar.high for bar in bars]
    lows = [bar.low for bar in bars]

    # 计算RSV
    rsv: List[Optional[float]] = []
    for i in range(len(bars)):
        if i < n - 1:
            rsv.append(None)
        else:
            # 获取n日内的最高和最低价
            window_highs = highs[i - n + 1:i + 1]
            window_lows = lows[i - n + 1:i + 1]
            highest = max(window_highs)
            lowest = min(window_lows)

            if highest == lowest:
                # 避免除零，RSV设为50（中间值）
                rsv.append(50.0)
            else:
                rsv_value = (closes[i] - lowest) / (highest - lowest) * 100
                rsv.append(rsv_value)

    # 计算K和D
    k_values: List[Optional[float]] = []
    d_values: List[Optional[float]] = []

    # K和D的初始值设为50
    prev_k = 50.0
    prev_d = 50.0

    # 计算平滑系数
    k_alpha = 1.0 / m1
    d_alpha = 1.0 / m2

    for i in range(len(bars)):
        if rsv[i] is None:
            # 数据不足，K和D保持初始值
            k_values.append(None)
            d_values.append(None)
        else:
            # K = (1 - 1/m1) * 前日K + (1/m1) * RSV
            # 即 K = (m1-1)/m1 * 前日K + 1/m1 * RSV
            curr_k = (1 - k_alpha) * prev_k + k_alpha * rsv[i]
            # D = (1 - 1/m2) * 前日D + (1/m2) * K
            curr_d = (1 - d_alpha) * prev_d + d_alpha * curr_k

            k_values.append(curr_k)
            d_values.append(curr_d)

            prev_k = curr_k
            prev_d = curr_d

    # 计算J = 3K - 2D
    j_values: List[Optional[float]] = []
    for i in range(len(bars)):
        if k_values[i] is None or d_values[i] is None:
            j_values.append(None)
        else:
            j_values.append(3 * k_values[i] - 2 * d_values[i])

    return (k_values, d_values, j_values)


@dataclass
class KDJ:
    """
    KDJ 随机指标类。

    Attributes:
        n: RSV计算周期
        m1: K值平滑系数
        m2: D值平滑系数
        k: K值列表
        d: D值列表
        j: J值列表

    Example:
        >>> bars = [...]  # 至少9根K线
        >>> kdj = KDJ.calculate(bars)
        >>> print(kdj.k[-1], kdj.d[-1], kdj.j[-1])
    """

    n: int
    m1: int
    m2: int
    k: List[Optional[float]]
    d: List[Optional[float]]
    j: List[Optional[float]]

    @classmethod
    def calculate(cls, bars: List[Bar], n: int = 9, m1: int = 3, m2: int = 3) -> "KDJ":
        """
        计算 KDJ 指标。

        Args:
            bars: K线数据列表
            n: RSV计算周期，默认9
            m1: K值平滑系数，默认3
            m2: D值平滑系数，默认3

        Returns:
            KDJ 实例
        """
        k, d, j = kdj(bars, n, m1, m2)
        return cls(n=n, m1=m1, m2=m2, k=k, d=d, j=j)

    def __len__(self) -> int:
        return len(self.k)

    def __repr__(self) -> str:
        k_valid = sum(1 for v in self.k if v is not None)
        return f"KDJ(n={self.n}, m1={self.m1}, m2={self.m2}, {k_valid}/{len(self.k)} values)"

    def last(self) -> tuple:
        """
        获取最新的 KDJ 值。

        Returns:
            三元组 (K, D, J)，如果没有有效值则返回 (None, None, None)
        """
        k_last = None
        d_last = None
        j_last = None

        for v in reversed(self.k):
            if v is not None:
                k_last = v
                break

        for v in reversed(self.d):
            if v is not None:
                d_last = v
                break

        for v in reversed(self.j):
            if v is not None:
                j_last = v
                break

        return (k_last, d_last, j_last)

    def is_overbought(self, threshold: float = 80.0) -> Optional[bool]:
        """
        判断是否超买 (K > threshold，通常 threshold=80)。

        Args:
            threshold: 超买阈值，默认80

        Returns:
            如果最新K值存在且大于threshold返回True，否则返回False或None
        """
        k_last = None
        for v in reversed(self.k):
            if v is not None:
                k_last = v
                break

        if k_last is None:
            return None
        return k_last > threshold

    def is_oversold(self, threshold: float = 20.0) -> Optional[bool]:
        """
        判断是否超卖 (K < threshold，通常 threshold=20)。

        Args:
            threshold: 超卖阈值，默认20

        Returns:
            如果最新K值存在且小于threshold返回True，否则返回False或None
        """
        k_last = None
        for v in reversed(self.k):
            if v is not None:
                k_last = v
                break

        if k_last is None:
            return None
        return k_last < threshold
