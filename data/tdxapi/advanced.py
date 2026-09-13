"""
Advanced features module for TDX API

Provides DataFrame conversion, stock screening, and alert system functionality.

Features:
- Pandas/Polars DataFrame conversion
- Stock screening based on financial/technical indicators
- Price breakout and indicator cross alerts
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from data.tdxapi.models import Bar, StockQuote
from data.tdxapi.indicators import ma, ema, macd, kdj, rsi, boll


# =============================================================================
# DataFrame Converter
# =============================================================================

class DataFrameConverter:
    """
    DataFrame converter supporting Pandas and Polars.

    Converts tdxapi data models to DataFrame format for easier data analysis.

    Example:
        >>> converter = DataFrameConverter()
        >>> df = converter.to_pandas(bars)
        >>> df_polars = converter.to_polars(bars)
    """

    @staticmethod
    def to_pandas(
        data: Union[List[Bar], List[StockQuote], List[Dict[str, Any]]],
        columns: Optional[List[str]] = None
    ) -> "pandas.DataFrame":
        """
        Convert data to Pandas DataFrame.

        Args:
            data: List of Bar, StockQuote, or dict objects
            columns: Specific columns to include, None for all

        Returns:
            pandas.DataFrame

        Raises:
            ImportError: If pandas is not installed
            ValueError: If data is empty or unsupported format
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError(
                "pandas is required for DataFrame conversion. "
                "Install it with: pip install pandas"
            )

        if not data:
            raise ValueError("data cannot be empty")

        records = DataFrameConverter._to_records(data)
        df = pd.DataFrame(records)

        if columns:
            available_cols = [c for c in columns if c in df.columns]
            df = df[available_cols]

        return df

    @staticmethod
    def to_polars(
        data: Union[List[Bar], List[StockQuote], List[Dict[str, Any]]],
        columns: Optional[List[str]] = None
    ) -> "polars.DataFrame":
        """
        Convert data to Polars DataFrame.

        Args:
            data: List of Bar, StockQuote, or dict objects
            columns: Specific columns to include, None for all

        Returns:
            polars.DataFrame

        Raises:
            ImportError: If polars is not installed
            ValueError: If data is empty or unsupported format
        """
        try:
            import polars as pl
        except ImportError:
            raise ImportError(
                "polars is required for Polars DataFrame conversion. "
                "Install it with: pip install polars"
            )

        if not data:
            raise ValueError("data cannot be empty")

        records = DataFrameConverter._to_records(data)

        if columns:
            records = [
                {k: v for k, v in r.items() if k in columns}
                for r in records
            ]

        return pl.DataFrame(records)

    @staticmethod
    def _to_records(
        data: Union[List[Bar], List[StockQuote], List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """Convert data to list of dictionaries."""
        if not data:
            return []

        first_item = data[0]

        if isinstance(first_item, Bar):
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
                for bar in data
            ]
        elif isinstance(first_item, StockQuote):
            return [
                {
                    "code": quote.code,
                    "market": quote.market,
                    "name": quote.name,
                    "price": quote.price,
                    "last_close": quote.last_close,
                    "open": quote.open,
                    "high": quote.high,
                    "low": quote.low,
                    "volume": quote.volume,
                    "amount": quote.amount,
                    "bid1": quote.bid1,
                    "ask1": quote.ask1,
                    "datetime": quote.datetime,
                }
                for quote in data
            ]
        elif isinstance(first_item, dict):
            return data  # type: ignore
        else:
            raise ValueError(f"Unsupported data type: {type(first_item)}")

    @staticmethod
    def bars_to_ohlc(
        bars: List[Bar],
        date_column: str = "datetime"
    ) -> Dict[str, List[Any]]:
        """
        Convert Bar list to OHLC format dictionary.

        Args:
            bars: List of K-line data
            date_column: Name of the date column

        Returns:
            OHLC dictionary with date, open, high, low, close, volume
        """
        if not bars:
            return {"date": [], "open": [], "high": [], "low": [], "close": [], "volume": []}

        return {
            date_column: [bar.datetime for bar in bars],
            "open": [bar.open for bar in bars],
            "high": [bar.high for bar in bars],
            "low": [bar.low for bar in bars],
            "close": [bar.close for bar in bars],
            "volume": [bar.volume for bar in bars],
            "amount": [bar.amount for bar in bars],
        }


# =============================================================================
# Stock Screener
# =============================================================================

class FilterOperator(Enum):
    """Filter operators."""
    EQ = auto()       # Equal
    NE = auto()       # Not equal
    GT = auto()       # Greater than
    GTE = auto()      # Greater than or equal
    LT = auto()       # Less than
    LTE = auto()      # Less than or equal
    BETWEEN = auto()  # Between two values
    IN = auto()       # In list
    CONTAINS = auto() # Contains substring


@dataclass
class FilterCondition:
    """
    Filter condition.

    Attributes:
        field: Field name
        operator: Filter operator
        value: Comparison value (use (min, max) tuple for BETWEEN)

    Example:
        >>> condition = FilterCondition("close", FilterOperator.GT, 10.0)
        >>> condition2 = FilterCondition("pe", FilterOperator.BETWEEN, (10, 30))
    """
    field: str
    operator: FilterOperator
    value: Any

    def evaluate(self, data: Dict[str, Any]) -> bool:
        """Evaluate if condition is met."""
        if self.field not in data:
            return False

        field_value = data[self.field]

        if field_value is None:
            return False

        if self.operator == FilterOperator.EQ:
            return field_value == self.value
        elif self.operator == FilterOperator.NE:
            return field_value != self.value
        elif self.operator == FilterOperator.GT:
            return field_value > self.value
        elif self.operator == FilterOperator.GTE:
            return field_value >= self.value
        elif self.operator == FilterOperator.LT:
            return field_value < self.value
        elif self.operator == FilterOperator.LTE:
            return field_value <= self.value
        elif self.operator == FilterOperator.BETWEEN:
            min_val, max_val = self.value
            return min_val <= field_value <= max_val
        elif self.operator == FilterOperator.IN:
            return field_value in self.value
        elif self.operator == FilterOperator.CONTAINS:
            return self.value in str(field_value)

        return False


@dataclass
class ScreenerRule:
    """
    Screener rule with multiple conditions.

    Attributes:
        name: Rule name
        conditions: List of conditions
        logic: Condition combination logic, "AND" or "OR"

    Example:
        >>> rule = ScreenerRule(
        ...     name="Low price growth stocks",
        ...     conditions=[
        ...         FilterCondition("close", FilterOperator.LT, 20.0),
        ...         FilterCondition("pe", FilterOperator.BETWEEN, (10, 30)),
        ...     ],
        ...     logic="AND"
        ... )
    """
    name: str
    conditions: List[FilterCondition]
    logic: str = "AND"

    def evaluate(self, data: Dict[str, Any]) -> bool:
        """Evaluate if rule is met."""
        if not self.conditions:
            return True

        results = [c.evaluate(data) for c in self.conditions]

        if self.logic == "AND":
            return all(results)
        elif self.logic == "OR":
            return any(results)

        return False


class StockScreener:
    """
    Stock screener supporting multi-condition filtering.

    Supports predefined rules and custom condition combinations.

    Example:
        >>> screener = StockScreener()
        >>> screener.add_rule(ScreenerRule("Low price", [FilterCondition("close", FilterOperator.LT, 10.0)]))
        >>> results = screener.screen(stock_data, rule_name="Low price")
    """

    PREDEFINED_RULES: Dict[str, ScreenerRule] = {
        "low_price": ScreenerRule(
            name="low_price",
            conditions=[FilterCondition("close", FilterOperator.LT, 10.0)],
        ),
        "small_cap": ScreenerRule(
            name="small_cap",
            conditions=[FilterCondition("market_cap", FilterOperator.LT, 5e9)],
        ),
        "growth": ScreenerRule(
            name="growth",
            conditions=[
                FilterCondition("pe", FilterOperator.BETWEEN, (10, 40)),
                FilterCondition("peg", FilterOperator.LT, 1.0),
            ],
        ),
        "value": ScreenerRule(
            name="value",
            conditions=[
                FilterCondition("pe", FilterOperator.LT, 15.0),
                FilterCondition("pb", FilterOperator.LT, 1.5),
            ],
        ),
        "high_dividend": ScreenerRule(
            name="high_dividend",
            conditions=[FilterCondition("dividend_yield", FilterOperator.GT, 0.03)],
        ),
        "strong": ScreenerRule(
            name="strong",
            conditions=[
                FilterCondition("close", FilterOperator.GT, "ma20"),
                FilterCondition("rsi6", FilterOperator.BETWEEN, (50, 80)),
            ],
        ),
        "oversold": ScreenerRule(
            name="oversold",
            conditions=[
                FilterCondition("close", FilterOperator.LT, "ma60"),
                FilterCondition("rsi6", FilterOperator.LT, 30),
            ],
        ),
        "ma_golden_cross": ScreenerRule(
            name="ma_golden_cross",
            conditions=[FilterCondition("ma_cross", FilterOperator.EQ, "golden")],
        ),
    }

    def __init__(self):
        """Initialize stock screener."""
        self._rules: Dict[str, ScreenerRule] = {}
        self._rules.update(self.PREDEFINED_RULES)

    def add_rule(self, rule: ScreenerRule) -> None:
        """Add custom screening rule."""
        self._rules[rule.name] = rule

    def remove_rule(self, name: str) -> bool:
        """Remove screening rule."""
        if name in self._rules and name not in self.PREDEFINED_RULES:
            del self._rules[name]
            return True
        return False

    def get_rule(self, name: str) -> Optional[ScreenerRule]:
        """Get screening rule by name."""
        return self._rules.get(name)

    def list_rules(self) -> List[str]:
        """List all rule names."""
        return list(self._rules.keys())

    def screen(
        self,
        stocks: List[Dict[str, Any]],
        rule_name: Optional[str] = None,
        conditions: Optional[List[FilterCondition]] = None,
        logic: str = "AND"
    ) -> List[Dict[str, Any]]:
        """
        Screen stocks based on rules or conditions.

        Args:
            stocks: List of stock data dictionaries
            rule_name: Predefined rule name (or use conditions)
            conditions: Custom condition list (or use rule_name)
            logic: Condition combination logic, "AND" or "OR"

        Returns:
            List of stocks matching the criteria
        """
        if rule_name:
            rule = self._rules.get(rule_name)
            if rule is None:
                raise ValueError(f"Rule '{rule_name}' not found")
        elif conditions:
            rule = ScreenerRule(name="custom", conditions=conditions, logic=logic)
        else:
            raise ValueError("Either rule_name or conditions must be provided")

        return [stock for stock in stocks if rule.evaluate(stock)]

    def screen_with_indicators(
        self,
        stocks_bars: Dict[str, List[Bar]],
        rule_name: Optional[str] = None,
        conditions: Optional[List[FilterCondition]] = None,
        logic: str = "AND"
    ) -> List[Dict[str, Any]]:
        """
        Screen stocks based on technical indicators.

        Automatically calculates indicators before screening.

        Args:
            stocks_bars: Dict of stock code to Bar list
            rule_name: Predefined rule name
            conditions: Custom condition list
            logic: Condition combination logic

        Returns:
            List of stocks with calculated indicators
        """
        stocks_with_indicators = []

        for code, bars in stocks_bars.items():
            if len(bars) < 60:
                continue

            indicators = self._calculate_indicators(bars)
            indicators["code"] = code
            indicators["market"] = bars[0].market if bars else ""
            stocks_with_indicators.append(indicators)

        return self.screen(stocks_with_indicators, rule_name, conditions, logic)

    def _calculate_indicators(self, bars: List[Bar]) -> Dict[str, Any]:
        """Calculate technical indicators for a stock."""
        indicators = {}

        latest = bars[-1]
        indicators["close"] = latest.close
        indicators["open"] = latest.open
        indicators["high"] = latest.high
        indicators["low"] = latest.low
        indicators["volume"] = latest.volume
        indicators["amount"] = latest.amount

        ma5_values = ma(bars, 5)
        ma10_values = ma(bars, 10)
        ma20_values = ma(bars, 20)
        ma60_values = ma(bars, 60)

        indicators["ma5"] = ma5_values[-1] if ma5_values else None
        indicators["ma10"] = ma10_values[-1] if ma10_values else None
        indicators["ma20"] = ma20_values[-1] if ma20_values else None
        indicators["ma60"] = ma60_values[-1] if ma60_values else None

        if len(ma5_values) >= 2 and ma10_values[-1] is not None and ma10_values[-2] is not None:
            if ma5_values[-2] is not None:
                if ma5_values[-2] <= ma10_values[-2] and ma5_values[-1] > ma10_values[-1]:
                    indicators["ma_cross"] = "golden"
                elif ma5_values[-2] >= ma10_values[-2] and ma5_values[-1] < ma10_values[-1]:
                    indicators["ma_cross"] = "dead"
                else:
                    indicators["ma_cross"] = "none"

        macd_result = macd(bars)
        indicators["macd_dif"] = macd_result["dif"][-1] if macd_result["dif"] else None
        indicators["macd_dea"] = macd_result["dea"][-1] if macd_result["dea"] else None
        indicators["macd_histogram"] = macd_result["histogram"][-1] if macd_result["histogram"] else None

        if len(macd_result["dif"]) >= 2:
            dif_now = macd_result["dif"][-1]
            dif_prev = macd_result["dif"][-2]
            dea_now = macd_result["dea"][-1]
            dea_prev = macd_result["dea"][-2]

            if dif_prev is not None and dea_prev is not None and dif_now is not None and dea_now is not None:
                if dif_prev <= dea_prev and dif_now > dea_now:
                    indicators["macd_cross"] = "golden"
                elif dif_prev >= dea_prev and dif_now < dea_now:
                    indicators["macd_cross"] = "dead"
                else:
                    indicators["macd_cross"] = "none"

        k_values, d_values, j_values = kdj(bars)
        indicators["kdj_k"] = k_values[-1] if k_values else None
        indicators["kdj_d"] = d_values[-1] if d_values else None
        indicators["kdj_j"] = j_values[-1] if j_values else None

        if len(k_values) >= 2 and k_values[-2] is not None and d_values[-2] is not None:
            if k_values[-2] <= d_values[-2] and k_values[-1] > d_values[-1]:
                indicators["kdj_cross"] = "golden"
            elif k_values[-2] >= d_values[-2] and k_values[-1] < d_values[-1]:
                indicators["kdj_cross"] = "dead"
            else:
                indicators["kdj_cross"] = "none"

        indicators["rsi6"] = rsi(bars, 6)[-1]
        indicators["rsi12"] = rsi(bars, 12)[-1]
        indicators["rsi24"] = rsi(bars, 24)[-1]

        boll_result = boll(bars)
        indicators["boll_up"] = boll_result.up[-1] if boll_result.up else None
        indicators["boll_mid"] = boll_result.mid[-1] if boll_result.mid else None
        indicators["boll_low"] = boll_result.low[-1] if boll_result.low else None

        if indicators["boll_up"] is not None and indicators["close"] > indicators["boll_up"]:
            indicators["boll_break"] = "up"
        elif indicators["boll_low"] is not None and indicators["close"] < indicators["boll_low"]:
            indicators["boll_break"] = "down"
        else:
            indicators["boll_break"] = "none"

        return indicators


# =============================================================================
# Alert System
# =============================================================================

class AlertType(Enum):
    """Alert types."""
    PRICE_ABOVE = auto()
    PRICE_BELOW = auto()
    PRICE_CHANGE = auto()
    MA_GOLDEN_CROSS = auto()
    MA_DEAD_CROSS = auto()
    MACD_GOLDEN_CROSS = auto()
    MACD_DEAD_CROSS = auto()
    KDJ_GOLDEN_CROSS = auto()
    KDJ_DEAD_CROSS = auto()
    RSI_OVERBOUGHT = auto()
    RSI_OVERSOLD = auto()
    BOLL_BREAK_UP = auto()
    BOLL_BREAK_DOWN = auto()
    CUSTOM = auto()


@dataclass
class Alert:
    """
    Alert definition.

    Attributes:
        id: Unique alert identifier
        name: Alert name
        alert_type: Type of alert
        code: Stock code
        market: Market
        params: Alert parameters
        enabled: Whether alert is enabled
        created_at: Creation time
        triggered_at: Last triggered time
        cooldown: Cooldown period in seconds
    """
    id: str
    name: str
    alert_type: AlertType
    code: str
    market: str
    params: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    triggered_at: Optional[datetime] = None
    cooldown: int = 300

    def is_in_cooldown(self) -> bool:
        """Check if alert is in cooldown period."""
        if self.triggered_at is None:
            return False
        return datetime.now() - self.triggered_at < timedelta(seconds=self.cooldown)

    def mark_triggered(self) -> None:
        """Mark alert as triggered."""
        self.triggered_at = datetime.now()


@dataclass
class AlertResult:
    """Alert trigger result."""
    alert: Alert
    triggered: bool
    message: str
    timestamp: datetime
    data: Dict[str, Any] = field(default_factory=dict)


AlertCallback = Callable[[AlertResult], None]


class AlertSystem:
    """
    Alert system for price breakouts and indicator crosses.

    Supports real-time monitoring and batch detection modes.

    Example:
        >>> alert_system = AlertSystem()
        >>> alert = Alert(
        ...     id="1",
        ...     name="Breakout 15",
        ...     alert_type=AlertType.PRICE_ABOVE,
        ...     code="000001",
        ...     market="SZ",
        ...     params={"price": 15.0}
        ... )
        >>> alert_system.add_alert(alert)
        >>> results = alert_system.check_alerts(quotes)
    """

    def __init__(self):
        """Initialize alert system."""
        self._alerts: Dict[str, Alert] = {}
        self._callbacks: List[AlertCallback] = []
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

    def add_alert(self, alert: Alert) -> None:
        """Add an alert."""
        with self._lock:
            self._alerts[alert.id] = alert

    def remove_alert(self, alert_id: str) -> bool:
        """Remove an alert."""
        with self._lock:
            if alert_id in self._alerts:
                del self._alerts[alert_id]
                return True
            return False

    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Get alert by ID."""
        with self._lock:
            return self._alerts.get(alert_id)

    def list_alerts(self, enabled_only: bool = False) -> List[Alert]:
        """List all alerts."""
        with self._lock:
            alerts = list(self._alerts.values())
            if enabled_only:
                alerts = [a for a in alerts if a.enabled]
            return alerts

    def enable_alert(self, alert_id: str) -> bool:
        """Enable an alert."""
        with self._lock:
            if alert_id in self._alerts:
                self._alerts[alert_id].enabled = True
                return True
            return False

    def disable_alert(self, alert_id: str) -> bool:
        """Disable an alert."""
        with self._lock:
            if alert_id in self._alerts:
                self._alerts[alert_id].enabled = False
                return True
            return False

    def register_callback(self, callback: AlertCallback) -> None:
        """Register alert callback function."""
        self._callbacks.append(callback)

    def unregister_callback(self, callback: AlertCallback) -> bool:
        """Unregister alert callback function."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
            return True
        return False

    def check_alerts(
        self,
        quotes: List[StockQuote],
        bars_map: Optional[Dict[str, List[Bar]]] = None
    ) -> List[AlertResult]:
        """
        Check all alerts.

        Args:
            quotes: List of real-time quotes
            bars_map: Dict of stock code to Bar list for technical indicators

        Returns:
            List of alert results
        """
        results = []
        quote_map = {q.code: q for q in quotes}

        with self._lock:
            alerts = [a for a in self._alerts.values() if a.enabled]

        for alert in alerts:
            if alert.is_in_cooldown():
                continue

            quote = quote_map.get(alert.code)
            if quote is None:
                continue

            result = self._check_single_alert(alert, quote, bars_map)
            if result.triggered:
                alert.mark_triggered()
                results.append(result)

                for callback in self._callbacks:
                    try:
                        callback(result)
                    except Exception:
                        pass

        return results

    def _check_single_alert(
        self,
        alert: Alert,
        quote: StockQuote,
        bars_map: Optional[Dict[str, List[Bar]]] = None
    ) -> AlertResult:
        """Check a single alert."""
        alert_type = alert.alert_type
        params = alert.params

        if alert_type == AlertType.PRICE_ABOVE:
            triggered = quote.price >= params.get("price", float("inf"))
            message = f"{alert.code} price broke above {params.get('price')}, current: {quote.price}"

        elif alert_type == AlertType.PRICE_BELOW:
            triggered = quote.price <= params.get("price", 0)
            message = f"{alert.code} price fell below {params.get('price')}, current: {quote.price}"

        elif alert_type == AlertType.PRICE_CHANGE:
            change_pct = (quote.price - quote.last_close) / quote.last_close * 100
            threshold = params.get("threshold", 5)
            triggered = abs(change_pct) >= threshold
            direction = "up" if change_pct > 0 else "down"
            message = f"{alert.code} price {direction} {abs(change_pct):.2f}%, current: {quote.price}"

        elif alert_type in (
            AlertType.MA_GOLDEN_CROSS, AlertType.MA_DEAD_CROSS,
            AlertType.MACD_GOLDEN_CROSS, AlertType.MACD_DEAD_CROSS,
            AlertType.KDJ_GOLDEN_CROSS, AlertType.KDJ_DEAD_CROSS,
            AlertType.RSI_OVERBOUGHT, AlertType.RSI_OVERSOLD,
            AlertType.BOLL_BREAK_UP, AlertType.BOLL_BREAK_DOWN
        ):
            triggered, message = self._check_indicator_alert(alert, quote, bars_map)

        elif alert_type == AlertType.CUSTOM:
            condition = params.get("condition")
            if callable(condition):
                triggered = condition(quote, bars_map.get(alert.code) if bars_map else None)
                message = f"{alert.code} custom condition triggered"
            else:
                triggered = False
                message = f"{alert.code} custom condition not defined"

        else:
            triggered = False
            message = f"{alert.code} unknown alert type"

        return AlertResult(
            alert=alert,
            triggered=triggered,
            message=message,
            timestamp=datetime.now(),
            data={
                "code": quote.code,
                "price": quote.price,
                "market": quote.market,
            }
        )

    def _check_indicator_alert(
        self,
        alert: Alert,
        quote: StockQuote,
        bars_map: Optional[Dict[str, List[Bar]]] = None
    ) -> Tuple[bool, str]:
        """Check technical indicator alert."""
        if bars_map is None or alert.code not in bars_map:
            return False, f"{alert.code} no bar data"

        bars = bars_map[alert.code]
        if len(bars) < 30:
            return False, f"{alert.code} insufficient bar data"

        alert_type = alert.alert_type
        params = alert.params

        if alert_type in (AlertType.MA_GOLDEN_CROSS, AlertType.MA_DEAD_CROSS):
            fast_period = params.get("fast", 5)
            slow_period = params.get("slow", 10)

            fast_ma = ma(bars, fast_period)
            slow_ma = ma(bars, slow_period)

            if len(fast_ma) < 2 or fast_ma[-2] is None or slow_ma[-2] is None:
                return False, f"{alert.code} insufficient MA data"

            if alert_type == AlertType.MA_GOLDEN_CROSS:
                triggered = fast_ma[-2] <= slow_ma[-2] and fast_ma[-1] > slow_ma[-1]
                message = f"{alert.code} MA{fast_period} crossed above MA{slow_period}, golden cross"
            else:
                triggered = fast_ma[-2] >= slow_ma[-2] and fast_ma[-1] < slow_ma[-1]
                message = f"{alert.code} MA{fast_period} crossed below MA{slow_period}, dead cross"

        elif alert_type in (AlertType.MACD_GOLDEN_CROSS, AlertType.MACD_DEAD_CROSS):
            macd_result = macd(bars)
            dif = macd_result["dif"]
            dea = macd_result["dea"]

            if len(dif) < 2 or dif[-2] is None or dea[-2] is None:
                return False, f"{alert.code} insufficient MACD data"

            if alert_type == AlertType.MACD_GOLDEN_CROSS:
                triggered = dif[-2] <= dea[-2] and dif[-1] > dea[-1]
                message = f"{alert.code} MACD golden cross, DIF crossed above DEA"
            else:
                triggered = dif[-2] >= dea[-2] and dif[-1] < dea[-1]
                message = f"{alert.code} MACD dead cross, DIF crossed below DEA"

        elif alert_type in (AlertType.KDJ_GOLDEN_CROSS, AlertType.KDJ_DEAD_CROSS):
            k_values, d_values, _ = kdj(bars)

            if len(k_values) < 2 or k_values[-2] is None or d_values[-2] is None:
                return False, f"{alert.code} insufficient KDJ data"

            if alert_type == AlertType.KDJ_GOLDEN_CROSS:
                triggered = k_values[-2] <= d_values[-2] and k_values[-1] > d_values[-1]
                message = f"{alert.code} KDJ golden cross, K crossed above D"
            else:
                triggered = k_values[-2] >= d_values[-2] and k_values[-1] < d_values[-1]
                message = f"{alert.code} KDJ dead cross, K crossed below D"

        elif alert_type in (AlertType.RSI_OVERBOUGHT, AlertType.RSI_OVERSOLD):
            period = params.get("period", 6)
            rsi_values = rsi(bars, period)

            if rsi_values[-1] is None:
                return False, f"{alert.code} insufficient RSI data"

            if alert_type == AlertType.RSI_OVERBOUGHT:
                threshold = params.get("threshold", 80)
                triggered = rsi_values[-1] >= threshold
                message = f"{alert.code} RSI{period} overbought, current: {rsi_values[-1]:.2f}"
            else:
                threshold = params.get("threshold", 20)
                triggered = rsi_values[-1] <= threshold
                message = f"{alert.code} RSI{period} oversold, current: {rsi_values[-1]:.2f}"

        elif alert_type in (AlertType.BOLL_BREAK_UP, AlertType.BOLL_BREAK_DOWN):
            boll_result = boll(bars)

            if boll_result.up[-1] is None or boll_result.low[-1] is None:
                return False, f"{alert.code} insufficient BOLL data"

            if alert_type == AlertType.BOLL_BREAK_UP:
                triggered = quote.price >= boll_result.up[-1]
                message = f"{alert.code} broke above BOLL upper band"
            else:
                triggered = quote.price <= boll_result.low[-1]
                message = f"{alert.code} fell below BOLL lower band"

        else:
            triggered = False
            message = f"{alert.code} unknown indicator alert"

        return triggered, message

    def start_monitoring(
        self,
        quote_provider: Callable[[], List[StockQuote]],
        bars_provider: Optional[Callable[[List[str]], Dict[str, List[Bar]]]] = None,
        interval: int = 5
    ) -> None:
        """Start real-time monitoring."""
        if self._running:
            return

        self._running = True

        def monitor_loop():
            while self._running:
                try:
                    quotes = quote_provider()
                    bars_map = None
                    if bars_provider:
                        codes = [a.code for a in self.list_alerts(enabled_only=True)]
                        if codes:
                            bars_map = bars_provider(codes)

                    self.check_alerts(quotes, bars_map)
                except Exception:
                    pass

                time.sleep(interval)

        self._monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop_monitoring(self) -> None:
        """Stop real-time monitoring."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
            self._monitor_thread = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stop_monitoring()


# =============================================================================
# Helper Functions
# =============================================================================

def create_price_alert(
    code: str,
    market: str,
    price: float,
    direction: str = "above",
    name: Optional[str] = None
) -> Alert:
    """Create price alert."""
    alert_id = f"price_{code}_{int(time.time())}"
    alert_type = AlertType.PRICE_ABOVE if direction == "above" else AlertType.PRICE_BELOW
    name = name or f"{code} price {'above' if direction == 'above' else 'below'} {price}"

    return Alert(
        id=alert_id,
        name=name,
        alert_type=alert_type,
        code=code,
        market=market,
        params={"price": price}
    )


def create_ma_cross_alert(
    code: str,
    market: str,
    fast: int = 5,
    slow: int = 10,
    cross_type: str = "golden",
    name: Optional[str] = None
) -> Alert:
    """Create MA cross alert."""
    alert_id = f"ma_{code}_{int(time.time())}"
    alert_type = AlertType.MA_GOLDEN_CROSS if cross_type == "golden" else AlertType.MA_DEAD_CROSS
    name = name or f"{code} MA{fast} {'above' if cross_type == 'golden' else 'below'} MA{slow}"

    return Alert(
        id=alert_id,
        name=name,
        alert_type=alert_type,
        code=code,
        market=market,
        params={"fast": fast, "slow": slow}
    )


def create_macd_cross_alert(
    code: str,
    market: str,
    cross_type: str = "golden",
    name: Optional[str] = None
) -> Alert:
    """Create MACD cross alert."""
    alert_id = f"macd_{code}_{int(time.time())}"
    alert_type = AlertType.MACD_GOLDEN_CROSS if cross_type == "golden" else AlertType.MACD_DEAD_CROSS
    name = name or f"{code} MACD {'golden' if cross_type == 'golden' else 'dead'} cross"

    return Alert(
        id=alert_id,
        name=name,
        alert_type=alert_type,
        code=code,
        market=market,
        params={}
    )


def create_kdj_cross_alert(
    code: str,
    market: str,
    cross_type: str = "golden",
    name: Optional[str] = None
) -> Alert:
    """Create KDJ cross alert."""
    alert_id = f"kdj_{code}_{int(time.time())}"
    alert_type = AlertType.KDJ_GOLDEN_CROSS if cross_type == "golden" else AlertType.KDJ_DEAD_CROSS
    name = name or f"{code} KDJ {'golden' if cross_type == 'golden' else 'dead'} cross"

    return Alert(
        id=alert_id,
        name=name,
        alert_type=alert_type,
        code=code,
        market=market,
        params={}
    )


def detect_cross(
    values1: List[Optional[float]],
    values2: List[Optional[float]]
) -> Optional[str]:
    """
    Detect cross between two lines.

    Args:
        values1: First line values
        values2: Second line values

    Returns:
        "golden" if 1 crosses above 2, "dead" if 1 crosses below 2, None if no cross
    """
    if len(values1) < 2 or len(values2) < 2:
        return None

    prev1, curr1 = values1[-2], values1[-1]
    prev2, curr2 = values2[-2], values2[-1]

    if prev1 is None or prev2 is None or curr1 is None or curr2 is None:
        return None

    if prev1 <= prev2 and curr1 > curr2:
        return "golden"
    elif prev1 >= prev2 and curr1 < curr2:
        return "dead"

    return None
