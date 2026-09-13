"""fundamentals_store + as_of 数据关联层测试.

覆盖:
(a) as_of latest/prev/exact 三种模式语义正确(无未来函数);
(b) as_of 对乱序 df 也能正确(内部排序);
(c) fundamentals_store upsert: 插入后 get 返回相同值,再插入新值覆盖;
(d) stock_sector 多对多: 一股多板块写入 + 查询;
(e) 真实基本面解析: 用真实数据源拉 1 只股票(000001),断言返回真实 float 估值。

(e) 依赖网络/数据源可用性: 若环境受限拉不到真实值,明确记录并跳过该断言,
   绝不回填模拟值冒充真实数据。
"""
import os
import sys
import logging
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pandas as pd

from data.as_of import as_of, as_of_row  # noqa: E402
from data import fundamentals_store as fs  # noqa: E402

logger = logging.getLogger("aurora.test_fundamentals_asof")
logging.basicConfig(level=logging.WARNING)

# 测试用独立临时库,避免污染 data/fundamentals.db
TMP_DB = Path(__file__).parent / "_tmp_fundamentals.db"


@pytest.fixture()
def tmp_store(monkeypatch):
    """每个测试用独立临时库."""
    if TMP_DB.exists():
        TMP_DB.unlink()
    monkeypatch.setattr(fs, "DB_PATH", TMP_DB)
    fs.init()
    yield fs
    if TMP_DB.exists():
        TMP_DB.unlink()


def _sample_df(unsorted=False):
    """构造含日期+取值的有序/乱序 df."""
    rows = [
        {"date": "2024-01-02", "close": 1.0},
        {"date": "2024-01-03", "close": 2.0},
        {"date": "2024-01-05", "close": 3.0},
        {"date": "2024-01-06", "close": 4.0},
    ]
    df = pd.DataFrame(rows)
    if unsorted:
        df = df.iloc[[1, 3, 0, 2]].reset_index(drop=True)  # 打乱
    return df


# ------------------------------------------------------------------ (a) 三模式语义
def test_asof_latest_includes_today():
    df = _sample_df()
    r = as_of_row(df, "2024-01-05", "latest")
    assert r is not None and r["close"] == 3.0  # 当天收盘可知


def test_asof_latest_mid_gap_uses_prev_available():
    df = _sample_df()
    # 2024-01-04 无数据,latest 应回到 2024-01-03
    r = as_of_row(df, "2024-01-04", "latest")
    assert r["date"] == "2024-01-03" or r["date"] == pd.Timestamp("2024-01-03")
    assert r["close"] == 2.0


def test_asof_prev_excludes_today():
    df = _sample_df()
    r = as_of_row(df, "2024-01-05", "prev")
    assert r is not None and r["close"] == 2.0  # 严格 < date,不得取当天 3.0


def test_asof_exact_only_when_present():
    df = _sample_df()
    assert as_of_row(df, "2024-01-03", "exact")["close"] == 2.0
    assert as_of_row(df, "2024-01-04", "exact") is None  # 当天无数据


def test_asof_no_future_leak():
    """无未来函数: date 之前的任何时点都拿不到 date 之后的数据."""
    df = _sample_df()
    # 2024-01-04 时点不可能"看到" 2024-01-05 的 close=3.0
    r = as_of_row(df, "2024-01-04", "latest")
    assert r["close"] < 3.0
    # prev/当天边界同样无泄漏
    assert as_of_row(df, "2024-01-05", "prev")["close"] < 3.0


def test_asof_before_first_returns_none():
    df = _sample_df()
    assert as_of_row(df, "2023-12-01", "latest") is None
    assert as_of(df, "2023-12-01", "prev") is None


def test_asof_dataframe_return_shape():
    df = _sample_df()
    out = as_of(df, "2024-01-05", "latest")
    assert isinstance(out, pd.DataFrame) and len(out) == 1


# ------------------------------------------------------------------ (b) 乱序 df
def test_asof_handles_unsorted_df():
    df = _sample_df(unsorted=True)
    r = as_of_row(df, "2024-01-05", "latest")
    assert r is not None and r["close"] == 3.0
    r_prev = as_of_row(df, "2024-01-06", "prev")
    assert r_prev is not None and r_prev["close"] == 3.0


# ------------------------------------------------------------------ (c) fundamentals upsert
def test_fundamentals_upsert(tmp_store):
    # 拉取依赖网络,这里用单测桩复现"落库/读取/覆盖"逻辑
    rows = [
        {"code": "000001", "pe_ttm": 5.01, "pb": 0.47, "market_cap": 2155.96,
         "roe": None, "float_mcap": 2156.0, "price": 11.11},
    ]
    store = tmp_store
    with store._lock:
        db = store._conn()
        try:
            store._upsert_fundamentals(db, rows)
            db.commit()
        finally:
            db.close()
    got = store.get_fundamentals("000001")
    assert got["pe_ttm"] == 5.01 and got["pb"] == 0.47
    assert got["market_cap"] == 2155.96

    # 覆盖: 用新值重写
    new_rows = [
        {"code": "000001", "pe_ttm": 6.0, "pb": 0.5, "market_cap": 2200.0,
         "roe": None, "float_mcap": 2200.0, "price": 12.0},
    ]
    with store._lock:
        db = store._conn()
        try:
            store._upsert_fundamentals(db, new_rows)
            db.commit()
        finally:
            db.close()
    got2 = store.get_fundamentals("000001")
    assert got2["pe_ttm"] == 6.0 and got2["pb"] == 0.5


def test_fundamentals_missing_returns_empty(tmp_store):
    assert tmp_store.get_fundamentals("999999") == {}


# ------------------------------------------------------------------ (d) stock_sector 多对多
def test_stock_sector_many_to_many(tmp_store):
    store = tmp_store
    store.update_stock_sectors({
        "000001": {"银行": 1.0, "大湾区": 0.8, "保险": 0.6},
    })
    sectors = store.get_stock_sectors("000001")
    names = {s["sector"] for s in sectors}
    assert names == {"银行", "大湾区", "保险"}
    assert len(sectors) == 3

    # 支持二元组列表形态
    store.update_stock_sectors({"000001": [("银行", 1.0), ("保险", 0.6)]})
    assert len(store.get_stock_sectors("000001")) == 2


def test_stock_sector_replace_semantics(tmp_store):
    """对同一 code 全量替换,旧板块不残留."""
    store = tmp_store
    store.update_stock_sectors({"000002": ["房地产"]})
    store.update_stock_sectors({"000002": ["房地产", "深证成份"]})
    names = store.get_stock_sectors_names("000002")
    assert names == ["房地产", "深证成份"] and len(names) == 2
    # 无板块的股票返回空列表
    assert store.get_stock_sectors("nobody") == []


# ------------------------------------------------------------------ (e) 真实基本面解析(000001)
def test_real_fundamentals_000001(tmp_store):
    """真实拉取 000001 基本面,断言 pe_ttm/pb 为合理真实 float.

    网络/数据源受限拉不到时,明确记录并跳过断言,不回填模拟值。
    """
    store = tmp_store
    pulled = store.refresh_fundamentals(["000001"])
    if not pulled or "000001" not in pulled:
        pytest.skip(
            "[环境受限] 腾讯行情本次未拉取到 000001 真实基本面;"
            "store.refresh_fundamentals 返回空/缺失,已如实记录,不伪造数据"
        )
    row = pulled["000001"]
    assert isinstance(row.get("pe_ttm"), float), f"pe_ttm 应为真实 float, got {row.get('pe_ttm')!r}"
    assert isinstance(row.get("pb"), float), f"pb 应为真实 float, got {row.get('pb')!r}"
    assert row.get("pe_ttm", -1) > 0, "银行股 PE 应为正值"
    assert row.get("market_cap", -1) > 0, "市值应为正值"
    assert row.get("roe") is None, "腾讯行情不提供 ROE,应如实为 None"

    # 已落库: 从 get 读回与 refresh 一致且非空
    from_db = store.get_fundamentals("000001")
    assert from_db and from_db["pe_ttm"] == row["pe_ttm"]


# 清理
def teardown_module():
    if TMP_DB.exists():
        TMP_DB.unlink()
