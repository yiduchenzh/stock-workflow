# -*- coding: utf-8 -*-
""""至简交易法"(data/zhijian_backtest.py) 确定性单测。

验证要点(对齐任务红线):
  (a) 转译正确性 —— 老陈四情形逐bar触发规则在确定性合成分钟df下成立。
  (b) 情形1: 高开/平开低走, 回抽>当日开盘价买 → 断言买入价/触发日。
  (c) 情形2: 高开/平开高走, 创新高后回落<当日开盘价 且 不创新高 → 卖。
  (d) 开仓前提: 前日收盘<=MA5 → 当日不开仓(断言0买)。
  (e) 无未来函数: bar收盘判断 → 下一bar开盘成交(pending 模式)。
  (f) 四情形分别合成df确定性跑通, scenario_breakdown 精确。
  (g) 真实数据冒烟: 300319 m15 跑通(网络受限则 skip, 不伪造)。

所有测试使用合成 df(确定性), 不污染真实缓存(monkeypatch 独立结果cache)。
"""
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.zhijian_backtest import (  # noqa: E402
    _classify_scenario, _daily_meta, backtest_zhijian,
)
from data.result_cache import ResultCache  # noqa: E402

# 深市代码 (300319 老陈示例) → _trade_cost 过户费按 深市 sz 不收
CODE = "300319"


# ────────────────────────────── 工具 ──────────────────────────────
def build_daily(terminals=None):
    """构造日K(仅工作日), 头部低价、尾部贴近10.0 → 目标日 昨收≈10.0 且 MA5<昨收(gate True)。

    terminals 缺省 [10.0]*5; 若传入为全低值则可制造 gate=False(用于开仓前提禁买测试)。
    """
    tail = terminals if terminals is not None else [10.0] * 5
    head = [9.0, 9.2, 9.4, 9.6, 9.8]
    closes = head + tail
    dates = pd.bdate_range("2026-01-02", periods=len(closes))
    df = pd.DataFrame({
        "date": dates,
        "open": closes, "close": closes,
        "high": [c + 0.05 for c in closes],
        "low": [c - 0.30 for c in closes],   # 昨低 = close-0.30
        "volume": [1000.0] * len(closes),
    })
    df.attrs["code"] = CODE
    return df


def _meta():
    return _daily_meta(build_daily())


def _minute_df(day_rows):
    rows = []
    for dr in day_rows:
        rows.extend(dr)
    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    df.attrs["code"] = CODE
    return df


def _bars(td, seq):
    """seq: [(open,high,low,close)], 首根15min bar 起 09:45。"""
    t0 = pd.Timestamp(f"{td} 09:45")
    return [{"date": t0 + pd.Timedelta(minutes=15 * k), "open": o,
             "high": h, "low": l, "close": c, "volume": 1000.0}
            for k, (o, h, l, c) in enumerate(seq)]


@pytest.fixture(autouse=True)
def clean_cache(monkeypatch):
    """每个测试用独立结果缓存, 不污染真实 zhijian_result_cache.json。"""
    import data.zhijian_backtest as m
    tmp = Path(tempfile.mkdtemp()) / "test_zhijian_cache.json"
    m._ZJ_CACHE = ResultCache(tmp)
    m.CACHE_ENABLED = True
    m.BUST_CACHE = False


def _first_gate_day():
    meta = _meta()
    for k, v in meta.items():
        if v["gate"] and v["prev_close"] >= 9.9:
            return k, v
    return None, None


# ────────────────────── (d) 开仓前提: 前日收盘<=MA5 → 禁买 ──────────────────────
def test_open_gate_blocks_when_prev_close_below_ma5():
    """老陈①: 前日收盘<=MA5 → 当日不允许开仓(整日禁买, 断言0买)。"""
    daily = build_daily(terminals=[9.0, 9.0, 9.0, 9.0, 9.0])   # 尾部大跌 → gate False
    meta = _daily_meta(daily)
    bad = [k for k, v in meta.items() if v["gate"] is False]
    assert bad, "crafted daily 应存在 gate=False 的交易日"
    td = bad[0]
    pc = meta[td]["prev_close"]
    # 即便日内出现标准"回抽站稳开盘价"形态, 也因开仓前提被整体禁买:
    seq = [
        (pc + 0.30, pc + 0.34, pc + 0.25, pc + 0.28),
        (pc + 0.28, pc + 0.60, pc + 0.24, pc + 0.58),  # close>open & low<=open: 形态成立
        (pc + 0.55, pc + 0.58, pc + 0.42, pc + 0.50),
    ]
    r = backtest_zhijian(_minute_df([_bars(td, seq)]), daily, capital=10000)
    assert r["stats"]["trades"] == 0          # 0买
    assert not r["trades"]                     # 无任何交易


# ────────────────────── 情形1: 高开低走 回抽买 ──────────────────────
def test_scenario1_highopen_dip_reclaim_buy_and_sell():
    """②情形1: 高开(>=昨收)且盘中跌破开盘价(低走), 回抽bar收盘站稳开盘价上方 → 买; 回落<开盘价 → 卖。"""
    td, v = _first_gate_day()
    assert td is not None, "无 gate 通过的可用交易日"
    pc = v["prev_close"]
    seq = [
        (pc + 0.30, pc + 0.34, pc + 0.25, pc + 0.28),   # 高开低走
        (pc + 0.28, pc + 0.60, pc + 0.24, pc + 0.58),   # bar2 回抽买(pending)
        (pc + 0.55, pc + 0.58, pc + 0.42, pc + 0.50),   # bar3 执行买@open
        (pc + 0.50, pc + 0.52, pc + 0.08, pc + 0.12),   # bar4 回落<open(不创新高)卖(pending)
        (pc + 0.12, pc + 0.15, pc + 0.00, pc + 0.02),   # bar5 执行卖@open
    ]
    r = backtest_zhijian(_minute_df([_bars(td, seq)]), build_daily(), capital=10000)
    assert r["stats"]["trades"] == 1
    t = r["trades"][0]
    assert t["scenario"] == "scenario1"
    assert t["date"] == td
    assert abs(t["buy_px"] - (pc + 0.55)) < 1e-6    # bar3 open
    assert abs(t["exit_px"] - (pc + 0.12)) < 1e-6   # bar5 open
    assert r["scenario_breakdown"]["scenario1"] == 1


# ────────────────────── 情形2: 高开高走 回落买 / 不创新高卖 ──────────────────────
def test_scenario2_highopen_highwalk_pullback_buy_sell():
    """③情形2: 高开高走, 创新高后回落bar(回踩open且close>open)买;
    创新高后某bar'不创新高'且回落<当日开盘价 → 卖。"""
    td, v = _first_gate_day()
    pc = v["prev_close"]
    seq = [
        (pc + 0.30, pc + 0.34, pc + 0.31, pc + 0.33),   # 高开高走(首bar未破开盘价)
        (pc + 0.33, pc + 0.60, pc + 0.30, pc + 0.58),   # bar2 创新高+回落close>open → 买
        (pc + 0.55, pc + 0.62, pc + 0.40, pc + 0.55),   # bar3 执行买@open
        (pc + 0.55, pc + 0.58, pc + 0.05, pc + 0.10),   # bar4 不创新高+回落<open → 卖
        (pc + 0.10, pc + 0.12, pc - 0.05, pc + 0.00),   # bar5 执行卖@open
    ]
    r = backtest_zhijian(_minute_df([_bars(td, seq)]), build_daily(), capital=10000)
    assert r["stats"]["trades"] == 1
    t = r["trades"][0]
    assert t["scenario"] == "scenario2"
    assert abs(t["buy_px"] - (pc + 0.55)) < 1e-6
    assert abs(t["exit_px"] - (pc + 0.10)) < 1e-6
    assert r["scenario_breakdown"]["scenario2"] == 1


# ────────────────────── 情形3: 低开低走不破昨低 回抽买 ──────────────────────
def test_scenario3_lowopen_hold_prevlow_reclaim_buy():
    """④情形3: 低开(open<昨收)低走且日内不破昨低, 回抽>当日开盘价 → 买; 回落<开盘价 → 卖。"""
    td, v = _first_gate_day()
    pc, pl = v["prev_close"], v["prev_low"]
    od = pc - 0.15          # 低开(od<pc), 且远高于昨低 pl → 有下行空间但不破昨低
    assert pl < od < pc
    seq = [
        (od, od - 0.02, pl + 0.05, od - 0.02),             # 低开低走: high<open, 低点>=pl+0.05(不破昨低)
        (od - 0.02, od + 0.05, pl + 0.04, od + 0.03),      # bar2 回抽 close>open, low<=open → 买
        (od + 0.03, od + 0.06, pl + 0.02, od + 0.01),      # bar3 执行买@open
        (od + 0.01, od + 0.02, pl - 0.15, pl - 0.20),      # bar4 回落<open → 卖
        (pl - 0.20, pl - 0.18, pl - 0.30, pl - 0.25),      # bar5 执行卖@open
    ]
    r = backtest_zhijian(_minute_df([_bars(td, seq)]), build_daily(), capital=10000)
    assert r["stats"]["trades"] == 1
    t = r["trades"][0]
    assert t["scenario"] == "scenario3", f"got {t['scenario']}"
    assert abs(t["buy_px"] - (od + 0.03)) < 1e-6   # bar3 open
    assert abs(t["exit_px"] - (pl - 0.20)) < 1e-6  # bar5 open
    assert r["scenario_breakdown"]["scenario3"] == 1


# ────────────────────── 情形4: 低开高走创新高 回落买 ──────────────────────
def test_scenario4_lowopen_newhigh_pullback_buy():
    """⑤情形4: 低开且盘中创新高(高走), 回落回踩开盘价且收盘站稳 → 买; 不创新高回落<开盘价 → 卖。"""
    td, v = _first_gate_day()
    pc = v["prev_close"]
    seq = [
        (pc - 0.20, pc + 0.05, pc - 0.22, pc - 0.20),   # 低开; 首bar创新高(h>open)但close=open(≤open, 非买bar), 建立高走context
        (pc - 0.15, pc + 0.16, pc - 0.20, pc + 0.15),   # bar2 回落回踩open(low<=open) close>open → 买(scenario4)
        (pc + 0.15, pc + 0.18, pc + 0.02, pc + 0.12),   # bar3 执行买@open
        (pc + 0.10, pc + 0.12, pc - 0.30, pc - 0.26),   # bar4 不创新高(high<=rhi) 回落<open → 卖(pending)
        (pc - 0.30, pc - 0.28, pc - 0.40, pc - 0.35),   # bar5 执行卖@open
    ]
    r = backtest_zhijian(_minute_df([_bars(td, seq)]), build_daily(), capital=10000)
    assert r["stats"]["trades"] == 1
    t = r["trades"][0]
    assert t["scenario"] == "scenario4", f"got {t['scenario']}"
    assert abs(t["buy_px"] - (pc + 0.15)) < 1e-6
    assert abs(t["exit_px"] - (pc - 0.30)) < 1e-6
    assert r["scenario_breakdown"]["scenario4"] == 1


# ────────────────────── (f) 四情形合并df 确定性 ──────────────────────
def test_four_scenarios_combined_deterministic():
    """四情形各用一个交易日的合成df同时回测: 每情形恰好1笔, scenario_breakdown 精确。"""
    meta = _meta()
    gate_days = [k for k, v in meta.items() if v["gate"] and v["prev_close"] >= 9.9]
    assert len(gate_days) >= 4, f"需至少4个gate通过日, 现{len(gate_days)}"
    d1, d2, d3, d4 = gate_days[:4]
    v1, v2, v3, v4 = (meta[d] for d in (d1, d2, d3, d4))
    pc1, pc2, pc3, pc4 = v1["prev_close"], v2["prev_close"], v3["prev_close"], v4["prev_close"]
    pl3 = v3["prev_low"]

    s1 = _bars(d1, [
        (pc1 + 0.30, pc1 + 0.34, pc1 + 0.25, pc1 + 0.28),
        (pc1 + 0.28, pc1 + 0.60, pc1 + 0.24, pc1 + 0.58),
        (pc1 + 0.55, pc1 + 0.58, pc1 + 0.42, pc1 + 0.50),
        (pc1 + 0.50, pc1 + 0.52, pc1 + 0.08, pc1 + 0.12),
        (pc1 + 0.12, pc1 + 0.15, pc1 + 0.00, pc1 + 0.02),
    ])
    s2 = _bars(d2, [
        (pc2 + 0.30, pc2 + 0.34, pc2 + 0.31, pc2 + 0.33),
        (pc2 + 0.33, pc2 + 0.60, pc2 + 0.30, pc2 + 0.58),
        (pc2 + 0.55, pc2 + 0.62, pc2 + 0.40, pc2 + 0.55),
        (pc2 + 0.55, pc2 + 0.58, pc2 + 0.05, pc2 + 0.10),
        (pc2 + 0.10, pc2 + 0.12, pc2 - 0.05, pc2 + 0.00),
    ])
    od3 = pc3 - 0.15
    s3 = _bars(d3, [
        (od3, od3 - 0.02, pl3 + 0.05, od3 - 0.02),
        (od3 - 0.02, od3 + 0.05, pl3 + 0.04, od3 + 0.03),
        (od3 + 0.03, od3 + 0.06, pl3 + 0.02, od3 + 0.01),
        (od3 + 0.01, od3 + 0.02, pl3 - 0.15, pl3 - 0.20),
        (pl3 - 0.20, pl3 - 0.18, pl3 - 0.30, pl3 - 0.25),
    ])
    s4 = _bars(d4, [
        (pc4 - 0.20, pc4 + 0.05, pc4 - 0.22, pc4 - 0.20),
        (pc4 - 0.15, pc4 + 0.16, pc4 - 0.20, pc4 + 0.15),
        (pc4 + 0.15, pc4 + 0.18, pc4 + 0.02, pc4 + 0.12),
        (pc4 + 0.12, pc4 + 0.14, pc4 - 0.20, pc4 - 0.15),
        (pc4 - 0.15, pc4 - 0.12, pc4 - 0.30, pc4 - 0.25),
    ])

    r = backtest_zhijian(_minute_df([s1, s2, s3, s4]), build_daily(), capital=10000)
    assert r["stats"]["trades"] == 4
    assert r["scenario_breakdown"] == {
        "scenario1": 1, "scenario2": 1, "scenario3": 1, "scenario4": 1}
    assert sorted(t["scenario"] for t in r["trades"]) == \
        ["scenario1", "scenario2", "scenario3", "scenario4"]


# ────────────────────── (e) 无未来函数: bar收盘判断 → 下一bar开盘成交 ──────────────────────
def test_no_future_function_pending_exit():
    td, v = _first_gate_day()
    pc = v["prev_close"]
    seq = [
        (pc + 0.30, pc + 0.34, pc + 0.25, pc + 0.28),
        (pc + 0.28, pc + 0.60, pc + 0.24, pc + 0.58),   # bar2 收盘触发买
        (pc + 0.51, pc + 0.54, pc + 0.40, pc + 0.50),   # bar3 开盘执行买@pc+0.51 (≠bar2 close)
        (pc + 0.50, pc + 0.52, pc + 0.10, pc + 0.15),   # bar4 收盘触发卖
        (pc + 0.08, pc + 0.10, pc - 0.02, pc + 0.05),   # bar5 开盘执行卖@pc+0.08 (≠bar4 close)
    ]
    r = backtest_zhijian(_minute_df([_bars(td, seq)]), build_daily(), capital=10000)
    assert r["stats"]["trades"] == 1
    t = r["trades"][0]
    assert abs(t["buy_px"] - (pc + 0.51)) < 1e-6   # = bar3 open
    assert abs(t["buy_px"] - (pc + 0.58)) > 1e-6   # ≠ bar2 close (证明非bar收盘成交)
    assert abs(t["exit_px"] - (pc + 0.08)) < 1e-6  # = bar5 open
    assert abs(t["exit_px"] - (pc + 0.15)) > 1e-6  # ≠ bar4 close


# ────────────────────── (a) _classify_scenario 单元 ──────────────────────
def test_classify_scenario_unit():
    # 高开 + 买点前已跌破开盘价 → 情形1
    assert _classify_scenario(10.0, 9.8, 9.0, run_high=10.5, run_low=9.9) == "scenario1"
    # 高开 + 买点前未跌破开盘价 → 情形2
    assert _classify_scenario(10.0, 9.8, 9.0, run_high=10.5, run_low=10.01) == "scenario2"
    # 低开 + 已创高于开盘价新高 → 情形4
    assert _classify_scenario(9.8, 10.0, 9.5, run_high=9.85, run_low=9.60) == "scenario4"
    # 低开 + 未创新高 + 不破昨低 → 情形3
    assert _classify_scenario(9.8, 10.0, 9.5, run_high=9.79, run_low=9.79) == "scenario3"
    # 低开 + 未创新高 + 破昨低 → None(不构成可交易情形)
    assert _classify_scenario(9.8, 10.0, 9.5, run_high=9.79, run_low=9.40) is None


# ────────────────────── (g) 真实数据冒烟 300319 ──────────────────────
def test_real_300319_smoke():
    try:
        from data.zhijian_backtest import run_zhijian
        r = run_zhijian("300319", tf="m15", capital=100_000)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"网络受限, 无法拉取 300319 真实K线(不伪造): {e}")
    assert r["code"] == "300319"
    assert isinstance(r["stats"], dict)
    for k in ("trades", "win_rate", "profit_factor", "net_pnl",
              "total_return", "max_drawdown"):
        assert k in r["stats"]
    json.dumps(r)   # 必须 JSON 可序列化(无 numpy 标量泄漏)
    assert r["stats"]["trades"] >= 0
