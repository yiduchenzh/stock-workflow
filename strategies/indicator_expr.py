"""指标表达式树 v1.0 — 对齐hikyuu Indicator惰性求值思想
P2-3: 21个信号共享MA/EMA/ATR/动量等公共子表达式, 每根K线只算一次

设计:
- IndicatorExpr: 惰性表达式节点(叶子=原始数据/指标, 内部=运算符组合)
- 共享缓存: 同一表达式树在同一K线上计算结果缓存, 重复取零成本
- 表达式的公共子表达式自动合并(对齐hikyuu combineCalculateIndicators的alike合并思想)
"""
import logging
logger = logging.getLogger("aurora.indexpr")
import numpy as np


# ── 基础指标计算 (每个都带numpy优化) ──
def calc_ma(arr, window):
    if len(arr) < window:
        return np.full_like(arr, np.nan, dtype=np.float64)
    cum = np.cumsum(np.insert(arr, 0, 0))
    ma = (cum[window:] - cum[:-window]) / window
    return np.concatenate([np.full(window - 1, np.nan), ma])


def calc_ema(arr, window):
    if len(arr) == 0:
        return arr.astype(np.float64)
    alpha = 2.0 / (window + 1)
    out = np.empty(len(arr), dtype=np.float64)
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = alpha * arr[i] + (1 - alpha) * out[i - 1]
    return out


def calc_atr(high, low, close, window=14):
    n = len(close)
    if n < 2:
        return np.full(n, np.nan)
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    return calc_ma(tr, window)


def calc_rsi(close, window=14):
    n = len(close)
    if n < window + 1:
        return np.full(n, np.nan)
    delta = np.diff(close)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = calc_ma(gain, window)
    avg_loss = calc_ma(loss, window)
    rsi = np.full(n, np.nan)
    for i in range(window, n):
        if avg_loss[i - 1] == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain[i - 1] / avg_loss[i - 1]
            rsi[i] = 100 - 100 / (1 + rs)
    return rsi


def calc_macd(close, fast=12, slow=26, signal=9):
    ema_fast = calc_ema(close, fast)
    ema_slow = calc_ema(close, slow)
    dif = ema_fast - ema_slow
    dea = calc_ema(dif, signal)
    hist = (dif - dea) * 2
    return dif, dea, hist


def calc_boll(close, window=20, k=2.0):
    mid = calc_ma(close, window)
    n = len(close)
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    for i in range(window - 1, n):
        std = np.std(close[i - window + 1:i + 1])
        upper[i] = mid[i] + k * std
        lower[i] = mid[i] - k * std
    return upper, mid, lower


def calc_std(arr, window):
    n = len(arr)
    if n < window:
        return np.full(n, np.nan)
    out = np.empty(n)
    out[:window - 1] = np.nan
    for i in range(window - 1, n):
        out[i] = np.std(arr[i - window + 1:i + 1])
    return out


def calc_kdj(high, low, close, n=9):
    length = len(close)
    k = np.full(length, 50.0)
    d = np.full(length, 50.0)
    for i in range(length):
        lo = np.min(low[max(0, i - n + 1):i + 1])
        hi = np.max(high[max(0, i - n + 1):i + 1])
        rsv = 0.0 if hi == lo else (close[i] - lo) / (hi - lo) * 100
        k[i] = 2 / 3 * (k[i - 1] if i > 0 else 50) + 1 / 3 * rsv
        d[i] = 2 / 3 * (d[i - 1] if i > 0 else 50) + 1 / 3 * k[i]
    j = 3 * k - 2 * d
    return k, d, j


# ── 表达式节点 (惰性求值) ──
class _ExprNode:
    """表达式树节点 — 叶子=数据列/指标, 内部=运算
    对齐hikyuu IndicatorImp: 节点惰性求值, 结果缓存
    """
    __slots__ = ("op", "args", "cache", "key")

    def __init__(self, op, *args):
        self.op = op          # 'raw'/'ma'/'ema'/'atr'/'rsi'/'macd_dif'/'add'/'sub'/'mul'/'div'/'gt'/'lt'
        self.args = args
        self.cache = None
        self.key = None

    def _build_key(self, n):
        if self.key is None:
            self.key = (self.op, tuple(a if isinstance(a, (int, float, str)) else id(a) for a in self.args))
        return self.key

    def evaluate(self, data, cache=None):
        """惰性求值: 结果缓存到节点(同一K线重复取零成本)"""
        if self.cache is not None:
            return self.cache
        result = self._eval(data)
        self.cache = result
        if cache is not None:
            cache[self._build_key(len(data))] = result
        return result

    def _eval(self, data):
        op = self.op
        if op == "raw":
            return np.asarray(data[self.args[0]], dtype=np.float64)
        if op == "ma":
            return calc_ma(self.args[0].evaluate(data), self.args[1])
        if op == "ema":
            return calc_ema(self.args[0].evaluate(data), self.args[1])
        if op == "atr":
            return calc_atr(self.args[0].evaluate(data), self.args[1].evaluate(data),
                            self.args[2].evaluate(data), self.args[3])
        if op == "rsi":
            return calc_rsi(self.args[0].evaluate(data), self.args[1])
        if op == "std":
            return calc_std(self.args[0].evaluate(data), self.args[1])
        if op in ("add", "sub", "mul", "div", "gt", "lt"):
            a = self.args[0].evaluate(data)
            b = self.args[1] if isinstance(self.args[1], (int, float)) else self.args[1].evaluate(data)
            if op == "add": return a + b
            if op == "sub": return a - b
            if op == "mul": return a * b
            if op == "div":
                with np.errstate(divide="ignore", invalid="ignore"):
                    return np.where(np.abs(b) < 1e-12, 0.0, a / b)
            if op == "gt": return (a > b).astype(np.float64)
            if op == "lt": return (a < b).astype(np.float64)
        raise ValueError(f"Unknown op: {op}")


# ── 表达式工厂 (声明式, 对齐hikyuu crt/ 工厂函数风格) ──
def raw(col):
    return _ExprNode("raw", col)


def MA(expr, n):
    return _ExprNode("ma", expr if isinstance(expr, _ExprNode) else raw(expr), n)


def EMA(expr, n):
    return _ExprNode("ema", expr if isinstance(expr, _ExprNode) else raw(expr), n)


def ATR(h, l, c, n=14):
    return _ExprNode("atr", h if isinstance(h, _ExprNode) else raw(h),
                     l if isinstance(l, _ExprNode) else raw(l),
                     c if isinstance(c, _ExprNode) else raw(c), n)


def RSI(c, n=14):
    return _ExprNode("rsi", c if isinstance(c, _ExprNode) else raw(c), n)


def STD(expr, n):
    return _ExprNode("std", expr if isinstance(expr, _ExprNode) else raw(expr), n)


def add(a, b): return _ExprNode("add", a if isinstance(a, _ExprNode) else raw(a), b)
def sub(a, b): return _ExprNode("sub", a if isinstance(a, _ExprNode) else raw(a), b)
def mul(a, b): return _ExprNode("mul", a if isinstance(a, _ExprNode) else raw(a), b)
def div(a, b): return _ExprNode("div", a if isinstance(a, _ExprNode) else raw(a), b)
def gt(a, b):  return _ExprNode("gt",  a if isinstance(a, _ExprNode) else raw(a), b)
def lt(a, b):  return _ExprNode("lt",  a if isinstance(a, _ExprNode) else raw(a), b)


# ── 批量共享计算: 多个表达式在同一K线共享公共子表达式 ──
def evaluate_many(exprs: list, data, use_shared_cache: bool = True) -> list:
    """批量求值多个表达式 — 共享缓存使公共子表达式只算一次
    对齐hikyuu combineCalculateIndicators: 多个公式共享公共子节点
    """
    shared = {} if use_shared_cache else None
    results = []
    for e in exprs:
        results.append(e.evaluate(data, shared))
    return results


# ── 便捷API: 从K线df提取指标矩阵 (供21信号复用) ──
_IND_CACHE = {}

def get_indicator_matrix(kline_df, force=False) -> dict:
    """一次计算K线的全部基础指标 — 21信号共享, 避免每个信号重复算MA/ATR等
    返回: {ma5, ma10, ma20, ma60, ema12, ema26, dif, dea, macd_hist,
           atr14, rsi14, boll_upper, boll_mid, boll_lower, std20, kdj_k, kdj_d, kdj_j}
    """
    if kline_df is None or len(kline_df) == 0:
        return {}
    # 用数据指纹缓存 (K线尾时间+长度)
    try:
        last_date = str(kline_df["date"].iloc[-1])[:19]
    except Exception:
        last_date = str(id(kline_df))
    key = (id(kline_df), last_date, len(kline_df))
    cached = _IND_CACHE.get(key)
    if cached is not None and not force:
        return cached
    try:
        c = kline_df["close"].values.astype(np.float64)
        h = kline_df["high"].values.astype(np.float64)
        l = kline_df["low"].values.astype(np.float64)
        o = kline_df["open"].values.astype(np.float64)
        v = kline_df["volume"].values.astype(np.float64) if "volume" in kline_df.columns else np.ones(len(c))
        dif, dea, hist = calc_macd(c)
        k, d, j = calc_kdj(h, l, c)
        bu, bm, bl = calc_boll(c)
        m = {
            "ma5": calc_ma(c, 5), "ma10": calc_ma(c, 10), "ma20": calc_ma(c, 20),
            "ma60": calc_ma(c, 60), "ema12": calc_ema(c, 12), "ema26": calc_ema(c, 26),
            "dif": dif, "dea": dea, "macd_hist": hist,
            "atr14": calc_atr(h, l, c, 14), "rsi14": calc_rsi(c, 14),
            "boll_upper": bu, "boll_mid": bm, "boll_lower": bl,
            "std20": calc_std(c, 20), "kdj_k": k, "kdj_d": d, "kdj_j": j,
            "_close": c, "_high": h, "_low": l, "_open": o, "_volume": v,
        }
        # 限制缓存大小(防内存泄漏)
        if len(_IND_CACHE) > 200:
            _IND_CACHE.clear()
        _IND_CACHE[key] = m
        return m
    except Exception as e:
        logger.debug(f"[IndMatrix] fail: {e}")
        return {}
