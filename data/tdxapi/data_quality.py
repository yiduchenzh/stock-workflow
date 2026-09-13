"""
数据质量与工具模块

提供数据校验、缺失数据检测、除权除息复权计算、数据对齐等功能。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Tuple, Set, Union, Any
from enum import Enum

from data.tdxapi.models import Bar


class AdjustmentType(Enum):
    """复权类型"""
    FORWARD = "forward"    # 前复权
    BACKWARD = "backward"  # 后复权


@dataclass
class ValidationIssue:
    """数据校验问题"""
    issue_type: str
    message: str
    index: int
    value: Any
    severity: str = "warning"  # "error", "warning", "info"


@dataclass
class DataGap:
    """数据缺失区间"""
    start_date: datetime
    end_date: datetime
    expected_count: int
    actual_count: int


@dataclass
class AdjustmentFactor:
    """复权因子"""
    date: datetime
    factor: float
    dividend: float = 0.0  # 每股分红
    split_ratio: float = 1.0  # 拆股比例
    rights_issue: float = 0.0  # 配股


class DataValidator:
    """
    数据校验工具类

    用于检查K线数据中的异常值，包括价格跳空、成交量异常等。

    Example:
        >>> bars = [...]  # K线数据
        >>> validator = DataValidator()
        >>> issues = validator.validate(bars)
        >>> for issue in issues:
        ...     print(f"{issue.issue_type}: {issue.message}")
    """

    def __init__(
        self,
        max_price_gap: float = 0.21,  # 最大价格跳空比例（21%对应科创板/创业板涨停）
        max_volume_spike: float = 10.0,  # 最大成交量突增倍数
        min_volume: int = 0,  # 最小成交量
        max_price_change: float = 0.21,  # 最大价格变动比例
        check_ohlc: bool = True,  # 是否检查OHLC逻辑关系
    ):
        """
        初始化数据校验器

        Args:
            max_price_gap: 最大允许的价格跳空比例，默认21%（科创板/创业板涨停限制）
            max_volume_spike: 最大允许的成交量突增倍数，默认10倍
            min_volume: 最小成交量，默认0
            max_price_change: 最大日内价格变动比例，默认21%
            check_ohlc: 是否检查OHLC逻辑关系（high >= max(open,close), low <= min(open,close)）
        """
        self.max_price_gap = max_price_gap
        self.max_volume_spike = max_volume_spike
        self.min_volume = min_volume
        self.max_price_change = max_price_change
        self.check_ohlc = check_ohlc

    def validate(self, bars: List[Bar]) -> List[ValidationIssue]:
        """
        对K线数据进行全面校验

        Args:
            bars: K线数据列表，按时间顺序排列

        Returns:
            校验问题列表
        """
        issues: List[ValidationIssue] = []

        if not bars:
            return issues

        # 检查每根K线
        for i, bar in enumerate(bars):
            issues.extend(self._validate_single_bar(bar, i))

        # 检查连续K线之间的关系
        issues.extend(self._validate_consecutive_bars(bars))

        return issues

    def _validate_single_bar(self, bar: Bar, index: int) -> List[ValidationIssue]:
        """校验单根K线"""
        issues: List[ValidationIssue] = []

        # 检查OHLC逻辑关系
        if self.check_ohlc:
            if bar.high < bar.low:
                issues.append(ValidationIssue(
                    issue_type="ohlc_logic_error",
                    message=f"最高价({bar.high})低于最低价({bar.low})",
                    index=index,
                    value={"high": bar.high, "low": bar.low},
                    severity="error"
                ))

            if bar.high < max(bar.open, bar.close):
                issues.append(ValidationIssue(
                    issue_type="ohlc_logic_error",
                    message=f"最高价({bar.high})低于max(开盘,收盘)",
                    index=index,
                    value={"high": bar.high, "open": bar.open, "close": bar.close},
                    severity="error"
                ))

            if bar.low > min(bar.open, bar.close):
                issues.append(ValidationIssue(
                    issue_type="ohlc_logic_error",
                    message=f"最低价({bar.low})高于min(开盘,收盘)",
                    index=index,
                    value={"low": bar.low, "open": bar.open, "close": bar.close},
                    severity="error"
                ))

        # 检查价格是否为正
        for price_name, price_value in [
            ("open", bar.open),
            ("high", bar.high),
            ("low", bar.low),
            ("close", bar.close),
        ]:
            if price_value <= 0:
                issues.append(ValidationIssue(
                    issue_type="invalid_price",
                    message=f"{price_name}价格({price_value})必须为正数",
                    index=index,
                    value=price_value,
                    severity="error"
                ))

        # 检查日内价格变动
        if bar.open > 0:
            day_change = abs(bar.close - bar.open) / bar.open
            if day_change > self.max_price_change:
                issues.append(ValidationIssue(
                    issue_type="large_price_change",
                    message=f"日内价格变动({day_change:.2%})超过阈值({self.max_price_change:.2%})",
                    index=index,
                    value=day_change,
                    severity="warning"
                ))

        # 检查成交量
        if bar.volume < self.min_volume:
            issues.append(ValidationIssue(
                issue_type="low_volume",
                message=f"成交量({bar.volume})低于最小值({self.min_volume})",
                index=index,
                value=bar.volume,
                severity="warning"
            ))

        # 检查成交额与成交量的关系
        if bar.volume > 0 and bar.amount > 0:
            avg_price = bar.amount / bar.volume
            if avg_price < bar.low * 0.9 or avg_price > bar.high * 1.1:
                issues.append(ValidationIssue(
                    issue_type="amount_volume_mismatch",
                    message=f"成交额/成交量({avg_price:.2f})与价格区间不匹配",
                    index=index,
                    value={"avg_price": avg_price, "low": bar.low, "high": bar.high},
                    severity="warning"
                ))

        return issues

    def _validate_consecutive_bars(self, bars: List[Bar]) -> List[ValidationIssue]:
        """校验连续K线之间的关系"""
        issues: List[ValidationIssue] = []

        if len(bars) < 2:
            return issues

        # 计算平均成交量（用于检测异常成交量）
        avg_volume = sum(bar.volume for bar in bars) / len(bars)

        for i in range(1, len(bars)):
            prev_bar = bars[i - 1]
            curr_bar = bars[i]

            # 检查价格跳空
            if prev_bar.close > 0:
                gap_up = (curr_bar.open - prev_bar.close) / prev_bar.close
                gap_down = (prev_bar.close - curr_bar.open) / prev_bar.close

                if gap_up > self.max_price_gap:
                    issues.append(ValidationIssue(
                        issue_type="price_gap_up",
                        message=f"向上跳空({gap_up:.2%})超过阈值",
                        index=i,
                        value=gap_up,
                        severity="warning"
                    ))

                if gap_down > self.max_price_gap:
                    issues.append(ValidationIssue(
                        issue_type="price_gap_down",
                        message=f"向下跳空({gap_down:.2%})超过阈值",
                        index=i,
                        value=gap_down,
                        severity="warning"
                    ))

            # 检查成交量突增
            if avg_volume > 0:
                volume_spike = curr_bar.volume / avg_volume
                if volume_spike > self.max_volume_spike:
                    issues.append(ValidationIssue(
                        issue_type="volume_spike",
                        message=f"成交量突增({volume_spike:.1f}倍)超过阈值",
                        index=i,
                        value=volume_spike,
                        severity="warning"
                    ))

            # 检查时间顺序
            if curr_bar.datetime <= prev_bar.datetime:
                issues.append(ValidationIssue(
                    issue_type="timestamp_order_error",
                    message=f"时间戳顺序错误: {prev_bar.datetime} >= {curr_bar.datetime}",
                    index=i,
                    value={"prev": prev_bar.datetime, "curr": curr_bar.datetime},
                    severity="error"
                ))

        return issues

    def check_missing_data(
        self,
        bars: List[Bar],
        expected_interval: str = "1d"
    ) -> List[DataGap]:
        """
        检查缺失的K线数据

        Args:
            bars: K线数据列表，按时间顺序排列
            expected_interval: 期望的数据间隔，支持 "1d"(日线), "1m"(1分钟), "5m", "15m", "30m", "60m"

        Returns:
            数据缺失区间列表
        """
        gaps: List[DataGap] = []

        if not bars or len(bars) < 2:
            return gaps

        # 解析间隔
        interval_minutes = self._parse_interval(expected_interval)

        # 按日期分组检查（处理交易日）
        from collections import defaultdict
        date_bars = defaultdict(list)
        for bar in bars:
            date_key = bar.datetime.date()
            date_bars[date_key].append(bar)

        sorted_dates = sorted(date_bars.keys())

        for i in range(1, len(sorted_dates)):
            prev_date = sorted_dates[i - 1]
            curr_date = sorted_dates[i]

            # 计算期望的日期差
            date_diff = (curr_date - prev_date).days

            # 如果是日线数据，检查是否跳过了交易日
            if expected_interval == "1d":
                # 简单的交易日检查：跳过周末
                expected_dates = []
                d = prev_date + timedelta(days=1)
                while d < curr_date:
                    if d.weekday() < 5:  # 周一到周五
                        expected_dates.append(d)
                    d += timedelta(days=1)

                if expected_dates:
                    gaps.append(DataGap(
                        start_date=datetime.combine(expected_dates[0], datetime.min.time()),
                        end_date=datetime.combine(expected_dates[-1], datetime.min.time()),
                        expected_count=len(expected_dates),
                        actual_count=0
                    ))
            else:
                # 分钟线数据检查
                prev_bars = date_bars[prev_date]
                curr_bars = date_bars[curr_date]

                # 检查同一天内的间隔
                for j in range(1, len(curr_bars)):
                    time_diff = (curr_bars[j].datetime - curr_bars[j-1].datetime).total_seconds() / 60
                    if time_diff > interval_minutes * 1.5:  # 允许50%的误差
                        expected_count = int(time_diff / interval_minutes)
                        gaps.append(DataGap(
                            start_date=curr_bars[j-1].datetime,
                            end_date=curr_bars[j].datetime,
                            expected_count=expected_count,
                            actual_count=0
                        ))

        return gaps

    def _parse_interval(self, interval: str) -> int:
        """解析时间间隔字符串为分钟数"""
        interval_map = {
            "1m": 1,
            "5m": 5,
            "15m": 15,
            "30m": 30,
            "60m": 60,
            "1d": 240,  # 假设一天4小时交易时间
        }
        return interval_map.get(interval, 1)


class PriceAdjuster:
    """
    价格复权计算类

    实现前复权和后复权计算，处理除权除息数据。

    Example:
        >>> bars = [...]  # K线数据
        >>> factors = [...]  # 复权因子列表
        >>> adjuster = PriceAdjuster()
        >>> forward_adjusted = adjuster.adjust_forward(bars, factors)
        >>> backward_adjusted = adjuster.adjust_backward(bars, factors)
    """

    def __init__(self):
        """初始化复权计算器"""
        pass

    def adjust_forward(
        self,
        bars: List[Bar],
        factors: List[AdjustmentFactor]
    ) -> List[Bar]:
        """
        前复权计算

        前复权：以最新价格为基准，将历史价格调整为与最新价格可比的价格。
        适用于分析历史走势。

        Args:
            bars: K线数据列表，按时间顺序排列
            factors: 复权因子列表，按日期排序

        Returns:
            前复权后的K线数据
        """
        if not bars or not factors:
            return bars

        # 按日期排序复权因子
        sorted_factors = sorted(factors, key=lambda f: f.date)

        # 计算累积复权因子 - 前复权：从最新往前累积
        # 对于前复权，我们需要知道每个日期之后（含）的所有因子乘积
        cumulative_factor = 1.0
        factor_by_date: Dict[datetime.date, float] = {}

        # 从最旧的因子到最新的因子，累积因子
        for factor in sorted_factors:
            factor_by_date[factor.date.date()] = cumulative_factor
            cumulative_factor *= factor.factor

        # 应用复权 - 前复权：每个日期乘以该日期之后的所有因子
        return self._apply_adjustment_forward(bars, factor_by_date)

    def adjust_backward(
        self,
        bars: List[Bar],
        factors: List[AdjustmentFactor]
    ) -> List[Bar]:
        """
        后复权计算

        后复权：以历史价格为基准，将最新价格调整为与历史价格可比的价格。
        适用于计算真实收益率。

        Args:
            bars: K线数据列表，按时间顺序排列
            factors: 复权因子列表，按日期排序

        Returns:
            后复权后的K线数据
        """
        if not bars or not factors:
            return bars

        # 按日期排序复权因子
        sorted_factors = sorted(factors, key=lambda f: f.date)

        # 计算累积复权因子 - 后复权：从最旧往后累积
        cumulative_factor = 1.0
        factor_by_date: Dict[datetime.date, float] = {}

        for factor in sorted_factors:
            factor_by_date[factor.date.date()] = cumulative_factor
            cumulative_factor *= factor.factor

        # 应用复权 - 后复权
        return self._apply_adjustment_backward(bars, factor_by_date)

    def _apply_adjustment_forward(
        self,
        bars: List[Bar],
        factor_by_date: Dict[datetime.date, float]
    ) -> List[Bar]:
        """应用前复权因子到K线数据
        
        前复权逻辑：价格乘以该日期之后的所有因子
        """
        adjusted_bars: List[Bar] = []
        
        # 获取所有因子日期并排序
        factor_dates = sorted(factor_by_date.keys())
        
        # 计算每个bar对应的累积因子
        for bar in bars:
            bar_date = bar.datetime.date()
            
            # 找到该日期之后的所有因子，计算累积
            current_factor = 1.0
            for f_date in factor_dates:
                if f_date > bar_date:
                    # 对于前复权，需要乘以该日期之后的因子
                    pass
                # 该日期的因子需要应用
                if f_date >= bar_date:
                    # 找到对应的factor值
                    for f in factor_dates:
                        if f == f_date:
                            # 从factor_by_date获取的是到该日期为止的累积
                            pass
            
            # 简化：使用前向累积
            # 找到第一个大于bar_date的factor_date
            applicable_factor = 1.0
            for f_date in reversed(factor_dates):
                if f_date > bar_date:
                    applicable_factor = factor_by_date[f_date]
            
            # 如果bar_date本身有因子，也要应用
            if bar_date in factor_by_date:
                # 找到这个因子之后的累积
                idx = factor_dates.index(bar_date)
                applicable_factor = 1.0
                for i in range(idx, len(factor_dates)):
                    if i == idx:
                        applicable_factor *= 1.0  # 当前日期的因子是1.0（基准）
                    else:
                        # 需要获取实际因子值
                        pass
            
            # 简化实现：前复权 = 价格 / (从该日期到最新日期的因子乘积)
            # 即价格乘以从最新日期往回累积到该日期的因子
            applicable_factor = 1.0
            for f_date in reversed(factor_dates):
                if f_date > bar_date:
                    # 获取该日期的实际因子（factor_by_date存储的是到该日期的累积）
                    pass
                applicable_factor = factor_by_date.get(f_date, 1.0)
                if f_date <= bar_date:
                    break
            
            # 重新实现：计算每个日期的累积调整因子
            applicable_factor = self._calculate_forward_factor(bar_date, factor_dates, factor_by_date)
            
            adjusted_bar = Bar(
                code=bar.code,
                market=bar.market,
                datetime=bar.datetime,
                open=round(bar.open * applicable_factor, 4),
                high=round(bar.high * applicable_factor, 4),
                low=round(bar.low * applicable_factor, 4),
                close=round(bar.close * applicable_factor, 4),
                volume=int(bar.volume / applicable_factor) if applicable_factor > 0 else bar.volume,
                amount=bar.amount,
            )
            adjusted_bars.append(adjusted_bar)

        return adjusted_bars
    
    def _calculate_forward_factor(self, bar_date, factor_dates, factor_by_date):
        """计算前复权因子"""
        # 找到该日期应该应用的累积因子
        # 前复权：从最新日期往回累积到该日期
        result = 1.0
        found = False
        for f_date in reversed(factor_dates):
            if f_date <= bar_date:
                if not found:
                    result = factor_by_date[f_date]
                    found = True
                break
            result = factor_by_date[f_date]
        return result if found else 1.0

    def _apply_adjustment_backward(
        self,
        bars: List[Bar],
        factor_by_date: Dict[datetime.date, float]
    ) -> List[Bar]:
        """应用后复权因子到K线数据
        
        后复权逻辑：价格乘以该日期之前的所有因子
        """
        adjusted_bars: List[Bar] = []
        
        factor_dates = sorted(factor_by_date.keys())
        current_factor = 1.0
        factor_idx = 0
        
        for bar in bars:
            bar_date = bar.datetime.date()
            
            # 更新当前因子 - 应用所有小于等于当前日期的因子
            while factor_idx < len(factor_dates) and factor_dates[factor_idx] <= bar_date:
                # 获取实际因子值（factor_by_date存储的是累积值，需要计算差分）
                if factor_idx == 0:
                    current_factor = factor_by_date[factor_dates[factor_idx]]
                else:
                    prev_cum = factor_by_date[factor_dates[factor_idx - 1]]
                    curr_cum = factor_by_date[factor_dates[factor_idx]]
                    actual_factor = curr_cum / prev_cum if prev_cum > 0 else 1.0
                    current_factor *= actual_factor
                factor_idx += 1
            
            # 简化：直接使用factor_by_date的值
            applicable_factor = 1.0
            for f_date in reversed(factor_dates):
                if f_date <= bar_date:
                    applicable_factor = factor_by_date[f_date]
                    break
            
            adjusted_bar = Bar(
                code=bar.code,
                market=bar.market,
                datetime=bar.datetime,
                open=round(bar.open * applicable_factor, 4),
                high=round(bar.high * applicable_factor, 4),
                low=round(bar.low * applicable_factor, 4),
                close=round(bar.close * applicable_factor, 4),
                volume=int(bar.volume / applicable_factor) if applicable_factor > 0 else bar.volume,
                amount=bar.amount,
            )
            adjusted_bars.append(adjusted_bar)

        return adjusted_bars

    def calculate_factors_from_splits(
        self,
        splits: List[Tuple[datetime, float, float]]
    ) -> List[AdjustmentFactor]:
        """
        从除权除息数据计算复权因子

        Args:
            splits: 除权除息数据列表，每项为 (日期, 分红, 送股比例)
                   例如：[(datetime(2024,6,1), 0.5, 0.1)] 表示每10股分红5元，送1股

        Returns:
            复权因子列表
        """
        factors: List[AdjustmentFactor] = []

        for date, dividend, bonus_ratio in splits:
            # 复权因子 = 1 / (1 + 送股比例)
            # 分红会影响价格但不影响复权因子（因为价格已经扣除）
            factor = 1.0 / (1.0 + bonus_ratio) if bonus_ratio > -1 else 1.0

            factors.append(AdjustmentFactor(
                date=date,
                factor=factor,
                dividend=dividend,
                split_ratio=1.0 + bonus_ratio
            ))

        return factors

    def calculate_returns(
        self,
        bars: List[Bar],
        adjusted: bool = True,
        factors: Optional[List[AdjustmentFactor]] = None
    ) -> List[float]:
        """
        计算收益率序列

        Args:
            bars: K线数据列表
            adjusted: 是否使用复权价格计算
            factors: 复权因子列表（如果需要复权）

        Returns:
            收益率列表（百分比）
        """
        if len(bars) < 2:
            return []

        if adjusted and factors:
            bars = self.adjust_backward(bars, factors)

        returns: List[float] = []
        for i in range(1, len(bars)):
            if bars[i-1].close > 0:
                ret = (bars[i].close - bars[i-1].close) / bars[i-1].close * 100
                returns.append(ret)
            else:
                returns.append(0.0)

        return returns


class DataAligner:
    """
    数据对齐工具类

    用于对齐多只股票的时间序列数据，支持多种对齐模式。

    Example:
        >>> bars_a = [...]  # 股票A的K线
        >>> bars_b = [...]  # 股票B的K线
        >>> aligner = DataAligner()
        >>> aligned = aligner.align([bars_a, bars_b], mode="inner")
    """

    def __init__(self):
        """初始化数据对齐器"""
        pass

    def align(
        self,
        bars_list: List[List[Bar]],
        mode: str = "inner",
        fill_method: Optional[str] = None
    ) -> List[List[Bar]]:
        """
        对齐多只股票的时间序列数据

        Args:
            bars_list: 多组K线数据列表，每组是一个股票的K线序列
            mode: 对齐模式
                  - "inner": 内连接，只保留所有股票都有的日期（默认）
                  - "outer": 外连接，保留所有日期
                  - "left": 左连接，以第一组数据的日期为准
            fill_method: 填充方法（用于outer模式）
                  - None: 不填充，保留None
                  - "ffill": 向前填充
                  - "bfill": 向后填充
                  - "zero": 填充0

        Returns:
            对齐后的K线数据列表
        """
        if not bars_list:
            return []

        if len(bars_list) == 1:
            return bars_list

        # 获取所有日期集合
        all_dates_set: Set[datetime] = set()
        date_to_bars: List[Dict[datetime, Bar]] = []

        for bars in bars_list:
            date_map = {bar.datetime: bar for bar in bars}
            date_to_bars.append(date_map)
            all_dates_set.update(date_map.keys())

        # 确定对齐后的日期列表
        if mode == "inner":
            # 内连接：所有股票都有的日期
            common_dates = all_dates_set.copy()
            for date_map in date_to_bars:
                common_dates &= set(date_map.keys())
            aligned_dates = sorted(common_dates)
        elif mode == "outer":
            # 外连接：所有日期
            aligned_dates = sorted(all_dates_set)
        elif mode == "left":
            # 左连接：以第一组为准
            aligned_dates = sorted(date_to_bars[0].keys())
        else:
            raise ValueError(f"Unknown alignment mode: {mode}")

        # 对齐数据
        aligned_bars_list: List[List[Bar]] = []

        for i, date_map in enumerate(date_to_bars):
            aligned_bars: List[Bar] = []

            for date in aligned_dates:
                if date in date_map:
                    aligned_bars.append(date_map[date])
                elif mode == "outer" and fill_method:
                    # 需要填充
                    filled_bar = self._create_filled_bar(date, date_map, fill_method, bars_list[i])
                    if filled_bar:
                        aligned_bars.append(filled_bar)

            aligned_bars_list.append(aligned_bars)

        return aligned_bars_list

    def _create_filled_bar(
        self,
        date: datetime,
        date_map: Dict[datetime, Bar],
        fill_method: str,
        reference_bars: List[Bar]
    ) -> Optional[Bar]:
        """创建填充的Bar"""
        if not reference_bars:
            return None

        # 获取参考股票代码
        code = reference_bars[0].code
        market = reference_bars[0].market

        if fill_method == "ffill":
            # 向前填充：找到最近的过去数据
            past_dates = [d for d in date_map.keys() if d < date]
            if past_dates:
                nearest_date = max(past_dates)
                ref_bar = date_map[nearest_date]
                return Bar(
                    code=code,
                    market=market,
                    datetime=date,
                    open=ref_bar.close,
                    high=ref_bar.close,
                    low=ref_bar.close,
                    close=ref_bar.close,
                    volume=0,
                    amount=0.0,
                )
        elif fill_method == "bfill":
            # 向后填充：找到最近的未来数据
            future_dates = [d for d in date_map.keys() if d > date]
            if future_dates:
                nearest_date = min(future_dates)
                ref_bar = date_map[nearest_date]
                return Bar(
                    code=code,
                    market=market,
                    datetime=date,
                    open=ref_bar.open,
                    high=ref_bar.open,
                    low=ref_bar.open,
                    close=ref_bar.open,
                    volume=0,
                    amount=0.0,
                )
        elif fill_method == "zero":
            # 填充0
            return Bar(
                code=code,
                market=market,
                datetime=date,
                open=0.0,
                high=0.0,
                low=0.0,
                close=0.0,
                volume=0,
                amount=0.0,
            )

        return None

    def align_to_dataframe(
        self,
        bars_list: List[List[Bar]],
        codes: List[str],
        mode: str = "inner",
        price_type: str = "close"
    ) -> "pandas.DataFrame":
        """
        对齐数据并转换为DataFrame

        Args:
            bars_list: 多组K线数据列表
            codes: 股票代码列表
            mode: 对齐模式
            price_type: 价格类型，可选 "open", "high", "low", "close"

        Returns:
            pandas.DataFrame，行为日期，列为股票代码
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas is required for align_to_dataframe()")

        # 对齐数据
        aligned_bars = self.align(bars_list, mode=mode)

        # 提取价格数据
        data: Dict[str, List[float]] = {"date": []}
        for code in codes:
            data[code] = []

        if not aligned_bars or not aligned_bars[0]:
            return pd.DataFrame(data)

        # 获取日期列表
        dates = [bar.datetime for bar in aligned_bars[0]]
        data["date"] = dates

        # 提取各股票的价格
        price_getter = {
            "open": lambda b: b.open,
            "high": lambda b: b.high,
            "low": lambda b: b.low,
            "close": lambda b: b.close,
        }.get(price_type, lambda b: b.close)

        for i, code in enumerate(codes):
            if i < len(aligned_bars):
                data[code] = [price_getter(bar) for bar in aligned_bars[i]]
            else:
                data[code] = [None] * len(dates)

        df = pd.DataFrame(data)
        df.set_index("date", inplace=True)
        return df

    def resample(
        self,
        bars: List[Bar],
        target_interval: str,
        source_interval: str = "1m"
    ) -> List[Bar]:
        """
        重采样K线数据到不同周期

        Args:
            bars: K线数据列表
            target_interval: 目标周期，如 "5m", "15m", "30m", "60m", "1d"
            source_interval: 源数据周期，如 "1m", "5m"

        Returns:
            重采样后的K线数据
        """
        if not bars:
            return []

        # 解析周期
        target_minutes = self._parse_interval_minutes(target_interval)
        source_minutes = self._parse_interval_minutes(source_interval)

        if target_minutes < source_minutes:
            raise ValueError("Target interval must be larger than source interval")

        if target_minutes == source_minutes:
            return bars

        # 按周期分组
        from collections import defaultdict
        groups: Dict[datetime, List[Bar]] = defaultdict(list)

        for bar in bars:
            # 计算所属周期
            if target_interval.endswith("d"):
                # 日线：按日期分组
                group_key = bar.datetime.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                # 分钟线：按时间窗口分组
                minutes_since_midnight = bar.datetime.hour * 60 + bar.datetime.minute
                window = minutes_since_midnight // target_minutes * target_minutes
                new_hour = window // 60
                new_minute = window % 60
                group_key = bar.datetime.replace(hour=new_hour, minute=new_minute, second=0, microsecond=0)

            groups[group_key].append(bar)

        # 合并每组数据
        resampled: List[Bar] = []
        for group_key in sorted(groups.keys()):
            group_bars = groups[group_key]
            if not group_bars:
                continue

            merged_bar = Bar(
                code=group_bars[0].code,
                market=group_bars[0].market,
                datetime=group_key,
                open=group_bars[0].open,
                high=max(b.high for b in group_bars),
                low=min(b.low for b in group_bars),
                close=group_bars[-1].close,
                volume=sum(b.volume for b in group_bars),
                amount=sum(b.amount for b in group_bars),
            )
            resampled.append(merged_bar)

        return resampled

    def _parse_interval_minutes(self, interval: str) -> int:
        """解析时间间隔为分钟数"""
        if interval.endswith("d"):
            return int(interval[:-1]) * 240  # 假设一天4小时交易
        elif interval.endswith("m"):
            return int(interval[:-1])
        else:
            raise ValueError(f"Unknown interval format: {interval}")


# =============================================================================
# 便捷函数
# =============================================================================

def validate_data(
    bars: List[Bar],
    max_price_gap: float = 0.21,
    max_volume_spike: float = 10.0
) -> List[ValidationIssue]:
    """
    便捷函数：校验K线数据

    Args:
        bars: K线数据列表
        max_price_gap: 最大价格跳空比例
        max_volume_spike: 最大成交量突增倍数

    Returns:
        校验问题列表
    """
    validator = DataValidator(
        max_price_gap=max_price_gap,
        max_volume_spike=max_volume_spike
    )
    return validator.validate(bars)


def adjust_forward(
    bars: List[Bar],
    factors: List[AdjustmentFactor]
) -> List[Bar]:
    """
    便捷函数：前复权计算

    Args:
        bars: K线数据列表
        factors: 复权因子列表

    Returns:
        前复权后的K线数据
    """
    adjuster = PriceAdjuster()
    return adjuster.adjust_forward(bars, factors)


def adjust_backward(
    bars: List[Bar],
    factors: List[AdjustmentFactor]
) -> List[Bar]:
    """
    便捷函数：后复权计算

    Args:
        bars: K线数据列表
        factors: 复权因子列表

    Returns:
        后复权后的K线数据
    """
    adjuster = PriceAdjuster()
    return adjuster.adjust_backward(bars, factors)


def align_bars(
    bars_list: List[List[Bar]],
    mode: str = "inner"
) -> List[List[Bar]]:
    """
    便捷函数：对齐多组K线数据

    Args:
        bars_list: 多组K线数据列表
        mode: 对齐模式

    Returns:
        对齐后的K线数据列表
    """
    aligner = DataAligner()
    return aligner.align(bars_list, mode=mode)
