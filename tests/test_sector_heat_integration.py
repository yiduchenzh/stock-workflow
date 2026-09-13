"""core.engine._inject_sector_heat 板块热度注入集成测试.

覆盖:
(a) helper 单测: 一股多板块,取所属板块 max(change_pct);
(b) code 无 stock_sector 记录但有 industry → 回退 industry 兜底;
(c) 两路皆无 → sector_heat=0;
(d) 批量: 一次 update 多只多板块,helper 批量版每股都拿到自己所属板块的 max 热度;
(e) 批量读函数 get_stock_sectors_bulk 语义正确(单次 IN 查询).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from data import fundamentals_store as fs  # noqa: E402
from core.engine import _inject_sector_heat  # noqa: E402

# 测试用独立临时库,避免污染 data/fundamentals.db
TMP_DB = Path(__file__).parent / "_tmp_sector_heat.db"


@pytest.fixture()
def tmp_store(monkeypatch):
    """每个测试用独立临时库(monkeypatch DB_PATH),与 test_fundamentals_asof 一致."""
    if TMP_DB.exists():
        TMP_DB.unlink()
    monkeypatch.setattr(fs, "DB_PATH", TMP_DB)
    fs.init()
    yield fs
    if TMP_DB.exists():
        TMP_DB.unlink()


# ------------------------------------------------------------------ (a) 一股多板块 → max 热度
def test_helper_max_of_member_sectors(tmp_store):
    store = tmp_store
    store.update_stock_sectors({"TEST01": [("板块A", 1), ("板块B", 1)]})
    candidates = [{"code": "TEST01", "industry": "板块C"}]
    sectors = {"板块A": 5, "板块B": 8, "板块C": 1}
    _inject_sector_heat(candidates, sectors)
    # 股票同时属于 板块A(5) 和 板块B(8),应取 max=8,而非单 industry 的板块C(1)
    assert candidates[0]["sector_heat"] == 8


# ------------------------------------------------------------------ (b) 无 stock_sector → industry 兜底
def test_helper_fallback_to_industry(tmp_store):
    store = tmp_store
    # TEST02 不写入 stock_sector
    candidates = [{"code": "TEST02", "industry": "板块C"}]
    sectors = {"板块C": 3, "板块A": 9}
    _inject_sector_heat(candidates, sectors)
    assert candidates[0]["sector_heat"] == 3


def test_helper_fallback_industry_not_in_ranking(tmp_store):
    """industry 不在板块涨幅榜内 → 0."""
    candidates = [{"code": "TEST02", "industry": "神秘板块"}]
    sectors = {"板块C": 3}
    _inject_sector_heat(candidates, sectors)
    assert candidates[0]["sector_heat"] == 0


# ------------------------------------------------------------------ (c) 两路皆无 → 0
def test_helper_no_source_returns_zero(tmp_store):
    candidates = [{"code": "TEST03", "industry": ""}]
    sectors = {"板块A": 5}
    _inject_sector_heat(candidates, sectors)
    assert candidates[0]["sector_heat"] == 0


def test_helper_empty_candidates_noop(tmp_store):
    _inject_sector_heat([], {"板块A": 5})
    assert True  # 不抛异常


# ------------------------------------------------------------------ (d) 批量: 多股多板块各自 max 热度
def test_helper_bulk_per_stock_max(tmp_store):
    store = tmp_store
    store.update_stock_sectors({
        "TEST10": [("板块A", 1), ("板块B", 1)],   # max=8
        "TEST11": [("板块C", 1), ("板块D", 1)],   # max=4
        "TEST12": [("板块E", 1)],                  # max=9
        "TEST13": [("不在榜板块", 1)],             # 无命中 → 0
    })
    sectors = {"板块A": 5, "板块B": 8, "板块C": 4, "板块D": 2, "板块E": 9}
    candidates = [
        {"code": "TEST10", "industry": "x"},
        {"code": "TEST11", "industry": "x"},
        {"code": "TEST12", "industry": "x"},
        {"code": "TEST13", "industry": "x"},
    ]
    _inject_sector_heat(candidates, sectors)
    heat = {c["code"]: c["sector_heat"] for c in candidates}
    assert heat["TEST10"] == 8
    assert heat["TEST11"] == 4
    assert heat["TEST12"] == 9
    assert heat["TEST13"] == 0


# ------------------------------------------------------------------ (e) 批量读函数语义
def test_get_stock_sectors_bulk(tmp_store):
    store = tmp_store
    store.update_stock_sectors({
        "TEST20": [("A", 1), ("B", 1)],
        "TEST21": [("C", 1)],
    })
    m = store.get_stock_sectors_bulk(["TEST20", "TEST21", "NOPE"])
    assert set(m) == {"TEST20", "TEST21"}          # 无记录的不出现
    assert m["TEST20"] == ["A", "B"]
    assert m["TEST21"] == ["C"]
    assert store.get_stock_sectors_bulk([]) == {}   # 空入参


def teardown_module():
    if TMP_DB.exists():
        TMP_DB.unlink()
