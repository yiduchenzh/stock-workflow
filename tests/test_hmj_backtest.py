# -*- coding: utf-8 -*-
"""涨停回马枪·观察池逐日滚动回测引擎单测 v3 (2026-08-21)"""
import sys
sys.path.insert(0, r'D:\Hermes Agent CN Desktop\hunter-v2\backend')
import hmj_backtest as hmj


def _make_rows(zt_at=60, pull_after=2, vol_ratio=0.4):
    """构造日K: 上涨30天(低位) -> 横盘到zt_at -> 涨停 -> 缩量回调pull_after天 -> 拉升20天
    总长>=130根满足引擎len>=80门槛。日期唯一递增。"""
    rows = []
    c = 10.0
    day_no = 0
    def mkday():
        nonlocal day_no
        day_no += 1
        return f"2024-{(day_no-1)//28+1:02d}-{(day_no-1)%28+1:02d}"
    for _ in range(30):
        rows.append({"day": mkday(), "open": c * 0.995, "high": c * 1.01,
                     "low": c * 0.99, "close": c, "volume": 600_000})
        c *= 1.003
    while len(rows) < zt_at:
        c = rows[-1]["close"]
        rows.append({"day": mkday(), "open": c * 0.998, "high": c * 1.005,
                     "low": c * 0.995, "close": c, "volume": 500_000})
    c1 = rows[-1]["close"]
    rows.append({"day": mkday(), "open": c1 * 1.01, "high": c1 * 1.10,
                 "low": c1 * 1.005, "close": c1 * 1.10, "volume": 1_500_000})
    for _ in range(pull_after):
        v = 1_500_000 * vol_ratio
        c2 = rows[-1]["close"]
        rows.append({"day": mkday(), "open": c2 * 0.995, "high": c2 * 1.005,
                     "low": c2 * 0.988, "close": c2 * 1.0, "volume": v})
    c3 = rows[-1]["close"]
    for _ in range(20):
        c3 *= 1.03
        rows.append({"day": mkday(), "open": c3 * 0.99, "high": c3 * 1.02,
                     "low": c3 * 0.98, "close": c3, "volume": 1_500_000})
    return rows


class _FakeKC:
    def __init__(self, rows_map):
        self._m = rows_map
    def get_kline(self, code, period="daily", count=500):
        rows = self._m.get(code)
        if rows:
            return rows[-count:] if count < len(rows) else rows
        return None


def test_v3_flow_basic():
    """逐日滚动: 涨停入池 -> 缩量回调买入 -> 交易发生"""
    rows = _make_rows()
    kc = _FakeKC({"TEST": rows})
    r = hmj.run_hmj_backtest(kc.get_kline, ["TEST"], capital=100000,
                             max_positions=2, start_date="2023-12-01", end_date="2024-06-01")
    assert r.get("error") is None, r.get("error")
    assert r["stats"]["trades"] >= 1, f"应至少1笔: {r['stats']}"
    assert "涨停回马枪" in r["strategy"]["name"]


def test_v3_cleanup_stale():
    """观察池清理: 放量回调(永不缩量) -> 过期移出 -> 0笔"""
    rows = _make_rows(vol_ratio=1.5)
    kc = _FakeKC({"TEST": rows})
    r = hmj.run_hmj_backtest(kc.get_kline, ["TEST"], capital=100000,
                             max_positions=2, start_date="2023-12-01", end_date="2024-06-01")
    assert r["stats"]["trades"] == 0, f"放量回调不应买入: {r['stats']}"


def test_v3_global_cash():
    """全局资金池: 3只同时出信号, max_positions=2 限制"""
    kc = _FakeKC({"A": _make_rows(), "B": _make_rows(zt_at=80), "C": _make_rows(zt_at=100)})
    r = hmj.run_hmj_backtest(kc.get_kline, ["A", "B", "C"], capital=100000,
                             max_positions=2, start_date="2023-12-01", end_date="2024-06-01")
    assert r["stats"]["trades"] >= 1
    assert r["stats"]["final_equity"] > 0


def test_v3_stop_loss_rule():
    """战法止损: 买入后大跌 -> 不崩盘"""
    rows = _make_rows()
    for i in range(len(rows) - 5, len(rows)):
        c = rows[i]["close"] * 0.9
        rows[i] = {"day": rows[i]["day"], "open": c, "high": c * 1.01,
                   "low": c * 0.98, "close": c, "volume": 900_000}
    kc = _FakeKC({"TEST": rows})
    r = hmj.run_hmj_backtest(kc.get_kline, ["TEST"], capital=100000,
                             max_positions=2, start_date="2023-12-01", end_date="2024-06-01")
    assert r["stats"]["final_equity"] > 0


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                print(f"FAIL {name}: {e}")
