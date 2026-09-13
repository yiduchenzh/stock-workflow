"""通用时点对齐(as_of)工具 — 无未来函数语义.

把分散在各回测文件里手写的 "xx <= dt 取 tail" 逻辑抽成通用高效函数。

核心语义: 在 date 这个时点,交易者"能看到"的最近一期数据。
- "能看到" 意味着只使用 date 当天(含)及之前已确定的数据,绝不借用未来数据。
- latest : <= date 的最近一期 (自包含当天,用于"当天收盘可知"的指标对齐)。
- prev   : <  date 的最近一期 (严格排除当天,用于"当天不可知/需次日确认"的场景)。
- exact  : 必须是 == date 那一期,否则返回 None (用于严格对时点的快照)。

效率:
- 先按日期排好序(df 未排序、已排序均可,内部统一排序),再对 date 用二分查找
(hashable 的 numpy datetime64 维度)定位,避免 O(n) 全扫 + 复杂 if 链条。
- 对 df(多行)与单行(仅时序列)两种返回形态做了统一处理。

语义约定:
- date 列: 支持字符串("2024-01-05")或 datetime 类型,统一转成 pandas.Timestamp。
- 返回 latest/prev 时: 返回该时点的"一行"数据,列名与入参 df 相同。
  在此之上封装了 as_of_row(df,date,mode) 返回 dict 版,便于下游 dict 取用。
- 为空 df / 找不到任何满足条件的行时返回 None(单行)或空切片(DataFrame)。
"""
from __future__ import annotations

from typing import Optional

import logging

import pandas as pd
import numpy as np

logger = logging.getLogger("aurora.as_of")

DATE_COL_NAMES = ("date", "date_time", "trade_date", "dt", "time")


def _resolve_date_col(df: pd.DataFrame) -> str:
    """确定 df 的日期列名(优先常见日期列,否则取第一个 datetime64 列)."""
    for c in DATE_COL_NAMES:
        if c in df.columns:
            return c
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            return c
    raise ValueError(
        f"as_of: 找不到日期列,df 需含 {DATE_COL_NAMES} 中之一或任意 datetime64 列;"
        f"实际列: {list(df.columns)}"
    )


def _as_timestamp(d) -> pd.Timestamp:
    """把输入归一化为 pandas.Timestamp (字符串/原生 datetime/np.datetime64/Timestamp)."""
    if isinstance(d, pd.Timestamp):
        return d
    return pd.Timestamp(d)


def as_of(
    df: pd.DataFrame,
    date,
    mode: str = "latest",
) -> Optional[pd.DataFrame]:
    """通用时点对齐: 在 date 时点"能看到"的最近一期数据(无未来函数)。

    参数:
        df:   含日期列的 DataFrame。日期列优先取 date/date_time/trade_date/dt/time,
              否则取第一个 datetime64 列。df 可乱序,内部按日期重排。
        date: 对齐时点,支持字符串("2024-01-05")/datetime/Timestamp/np.datetime64。
        mode: "latest"(<=date 最近一期) / "prev"(<date 最近一期,不含当天) /
              "exact"(==date 那一期,否则 None)。

    返回:
        mode 取 latest/prev: 返回单行的 DataFrame(1 行,含全部原列);无满足行返回 None。
        mode 取 exact: == date 时返回单行;不等(或不存在)返回 None。
    """
    if df is None or len(df) == 0:
        return None

    col = _resolve_date_col(df)
    ts = _as_timestamp(date)

    # 统一排序(升序),保证二分定位正确 —— 传入乱序也能正确处理
    sorted_df = df.sort_values(col, kind="stable").reset_index(drop=True)
    dts = pd.to_datetime(sorted_df[col]).to_numpy(dtype="datetime64[ns]")
    target: np.datetime64 = np.datetime64(ts.to_datetime64())
    n = len(sorted_df)

    # 以 target 为右边界,二分找第一个 > target 的位置 -> idx 即 <= target 的最大下标+1
    idx = int(np.searchsorted(dts, target, side="right"))

    if mode == "latest":
        if idx <= 0:
            return None
        # idx-1 是 <= date 的最大下标(最近一期)
        return sorted_df.iloc[[idx - 1]]

    if mode == "prev":
        # 严格 < date: 排除 == date 的行。若 idx-1 恰好 == date,要再往左退
        pos = idx - 1
        while pos >= 0 and dts[pos] == target:
            pos -= 1
        if pos < 0:
            return None
        return sorted_df.iloc[[pos]]

    if mode == "exact":
        # == date: 期望 idx-1 恰是 target;若该位置日期 != target 则无精确一期
        pos = idx - 1
        if pos < 0 or dts[pos] != target:
            return None
        return sorted_df.iloc[[pos]]

    raise ValueError(f"as_of: mode 必须为 latest/prev/exact,收到 {mode!r}")


# ---------------------------------------------------------------------------
# dict 版: 便于下游把一行结果按 dict 取列值
# ---------------------------------------------------------------------------

def as_of_row(df: pd.DataFrame, date, mode: str = "latest") -> Optional[dict]:
    """as_of 的 dict 版: 返回该时点最近一期的一行作为 dict,无则返回 None."""
    row = as_of(df, date, mode)
    if row is None or len(row) == 0:
        return None
    return row.iloc[0].to_dict()
