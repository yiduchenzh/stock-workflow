"""WF 缓存 key 数据段正确性测试 — 修复: 换日期命中旧缓存缺陷
覆盖:
  (a) 同 codes/train_days/test_days/windows 但不同数据段(data_key) → key 不同
  (b) 完全相同参数+数据段 → key 相同
  (c) 老参数(windows/train_days/test_days/codes)变化仍会变 key — 不退化
"""
import pandas as pd
import pytest

from backtest.engine import BacktestEngine


def _mk_df(dates, close):
    """构造 K线 df(date + close)"""
    return pd.DataFrame({"date": dates, "close": close})


def _klines(version="a"):
    """构造两组 K线: 同根数、同收盘和, 但首末日期不同(模拟换日期)。"""
    if version == "a":
        # 2026-07 段
        dates = [f"2026-0{7}-{d:02d}" for d in range(1, 16)]
        close = [float(10 + i) for i in range(15)]        # sum=255
    else:
        # 2026-08 段: 根数15同, 收盘和255同, 但日期后移 →
        # 若不纳入日期则 key 相同(碰撞), 纳入日期则 key 变
        dates = [f"2026-08-{d:02d}" for d in range(1, 16)]
        close = [float(10 + i) for i in range(15)]
    return [_mk_df(dates, close)]


@pytest.fixture
def engine():
    return BacktestEngine()


# ---------- (a) 不同数据段 → key 不同 ----------
def test_diff_data_period_diff_key(engine):
    """同 codes 同参数, 只有数据段(首末日期)不同 → key 必须不同 (核心修复点)。"""
    codes = ["600000", "000001"]
    params = dict(train_days=200, test_days=50, windows=3)

    dk_a = engine._data_period_key(_klines("a"))
    dk_b = engine._data_period_key(_klines("b"))
    assert dk_a != dk_b, "不同数据段 data_key 不应碰撞"

    key_a = engine._cache_key(codes, **params, data_key=dk_a)
    key_b = engine._cache_key(codes, **params, data_key=dk_b)
    assert key_a != key_b, "换日期(数据段变)后 key 必须变, 否则会命中旧缓存"


def test_diff_data_same_close_len_same_keys_still_distinct(engine):
    """仅日期不同仍必须变 key — 即使根数/收盘和完全一致。"""
    codes = ["600520"]
    dk_jul = engine._data_period_key(_klines("a"))
    dk_aug = engine._data_period_key(_klines("b"))
    assert engine._cache_key(codes, 200, 50, 3, dk_jul) != engine._cache_key(codes, 200, 50, 3, dk_aug)


# ---------- (b) 同数据同参 → key 相同 ----------
def test_same_data_same_params_same_key(engine):
    codes = ["600000", "000001"]
    params = dict(train_days=200, test_days=50, windows=3)
    dk = engine._data_period_key(_klines("a"))
    k1 = engine._cache_key(codes, **params, data_key=dk)
    k2 = engine._cache_key(list(reversed(codes)), **params, data_key=dk)  # codes 乱序应归一
    assert k1 == k2, "相同数据+相同参数(含codes乱序)必须同 key, 才能命中缓存"


def test_same_dates_different_close_csum_changes_key(engine):
    """同日期但收盘数据不同(同根数)→ 收盘和变 → key 变, 避免同窗不同量价误命中。"""
    codes = ["600000"]
    dk1 = engine._data_period_key(_klines("a"))
    df2 = _mk_df([f"2026-07-{d:02d}" for d in range(1, 16)], [float(10 + i) for i in range(15)])
    dk2 = engine._data_period_key([df2])  # 与 a 完全相同 → 同 key
    assert dk1 == dk2

    # 收盘价整体 +100, 日期/根数不变 → 收盘和变 → key 变
    df3 = _mk_df([f"2026-07-{d:02d}" for d in range(1, 16)], [float(110 + i) for i in range(15)])
    dk3 = engine._data_period_key([df3])
    assert dk3 != dk1


# ---------- (c) 老参数变化仍变 key (不退化) ----------
def test_windows_change_changes_key(engine):
    codes = ["600000"]
    dk = engine._data_period_key(_klines("a"))
    assert engine._cache_key(codes, 200, 50, 3, dk) != engine._cache_key(codes, 200, 50, 4, dk)


def test_train_days_change_changes_key(engine):
    codes = ["600000"]
    dk = engine._data_period_key(_klines("a"))
    assert engine._cache_key(codes, 200, 50, 3, dk) != engine._cache_key(codes, 250, 50, 3, dk)


def test_test_days_change_changes_key(engine):
    codes = ["600000"]
    dk = engine._data_period_key(_klines("a"))
    assert engine._cache_key(codes, 200, 50, 3, dk) != engine._cache_key(codes, 200, 60, 3, dk)


def test_codes_change_changes_key(engine):
    dk = engine._data_period_key(_klines("a"))
    assert engine._cache_key(["600000"], 200, 50, 3, dk) != engine._cache_key(["600519"], 200, 50, 3, dk)


# ---------- 附加: 数据段描述工具 ----------
def test_period_desc_notes_date_len_sum(engine):
    df = _mk_df(["2026-07-01", "2026-07-02"], [10.0, 20.0])
    desc = BacktestEngine._kline_period_desc(df)
    assert "2026-07-01..2026-07-02" in desc
    assert "n:2" in desc
    assert "csum:30.00" in desc
