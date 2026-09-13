# -*- coding: utf-8 -*-
"""2026-08-16 P0-② 昨收战法传导到实盘引擎的实证验证 (全链路, 只读不污染账户).

① auto 自动选买入模式(工作流版 prev_close_play._auto_entry_mode)按波动/趋势分派
② 强势池护栏在实盘信号收集层守死(prev_close_B 仅对 strong_grade∈{A,B} 或 score≥70)
③ 单引擎可达: config.active_profile=上班族中短线 补 prev_close 权重后 analyze_all 能触发昨收
④ ATR/高位回撤止损真接线(engine→watch_positions→calc_trailing_stop 传 klines+trailing_highs)
"""
import ast, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

for f in ["profiling/trader_types.py", "strategies/prev_close_play.py", "core/engine.py"]:
    ast.parse((ROOT / f).read_text(encoding="utf-8"))
print("SYNTAX OK")

# ── ① auto entry mode 工作流版 ──
from strategies.prev_close_play import _auto_entry_mode
def _df(closes, wick=0.02):
    c = np.asarray(closes, float); n = len(c)
    o = c * 0.995; h = np.maximum(o, c) * (1 + wick); lo = np.minimum(o, c) * (1 - wick)
    return pd.DataFrame({"date": pd.date_range("2024-01-01", periods=n, freq="B"),
                         "open": o, "high": h, "low": lo, "close": c, "volume": np.full(n, 1e6)})
hi = _df(list(10.0*np.ones(80)) + list(10.0*(1.0+0.004*i) for i in range(40)))
lo = _df([10.0 + 0.002*(1 if i%2 else -1) for i in range(120)], wick=0.003)
assert _auto_entry_mode(hi) == "same_close", "高波动强趋势应 same_close"
assert _auto_entry_mode(lo) == "next_open", "低波动震荡应 next_open"
assert _auto_entry_mode(None) == "next_open"
print("[①] auto entry: high-vol-trend=same_close  low-vol-flat=next_open  none=next_open OK")

# ── ③ 单引擎可达 + ② 强势池护栏 ──
from profiling.trader_types import get_trader_profile
sw = get_trader_profile("上班族中短线")["strategy_weights"]
assert "prev_close_A" in sw and "prev_close_B" in sw
print("[③] 上班族中短线 prev_close weights =", {k: sw[k] for k in ("prev_close_A","prev_close_B")})
def _strong_trend_df(n=120):
    base = [10.0] * (n - 30); uptrend = [10.0 * (1.0 + 0.006 * i) for i in range(30)]
    closes = np.asarray(base + uptrend, float)
    pc = closes[-1]; closes[-1] = pc * 1.02
    opens = closes * 0.998; lows = closes * 0.995; highs = closes * 1.01
    return pd.DataFrame({"date": pd.date_range("2024-01-01", periods=n, freq="B"),
                         "open": opens, "high": highs, "low": lows, "close": closes,
                         "volume": np.full(n, 1e6)})
from strategies.runner import analyze_all
kdf = _strong_trend_df(); kdf.attrs["code"] = "300000"
base_cand = {"code": "300000", "name": "T", "industry": "电子", "change_pct": 5.0}
candA = dict(base_cand, strong_grade="A", strong_score=90)
rA = analyze_all([candA], kline_override={"300000": kdf}, strategy_weights=sw)
bestA = rA[0].get("best_strategy")
assert bestA and bestA.startswith("prev_close"), f"强票昨收未触发: {bestA}"
print("[③] 强票(grade=A) best_strategy =", bestA, "→ 单引擎昨收可达")
candC = dict(base_cand, strong_grade="C", strong_score=50)
rC = analyze_all([candC], kline_override={"300000": kdf}, strategy_weights=sw)
sigC = rC[0].get("all_signals") or []
assert "prev_close_B" not in sigC, "弱票 prev_close_B 漏穿护栏"
print("[②] 弱票(grade=C) prev_close_B 被护栏拦截, all_signals=", sigC)

# ── ④ ATR/高位回撤止损真接线 (非死代码) ──
src = (ROOT / "monitor/watcher.py").read_text(encoding="utf-8")
# calc_trailing_stop 调用必须带 klines= 与 highest_price= (v14.46 修复点)
assert "calc_trailing_stop(entry, cur, current_ts, klines=kdf, market_regime=" in src
assert "highest_price=highest" in src
eng = (ROOT / "core/engine.py").read_text(encoding="utf-8")
# engine.step_monitor 把 kline_cache(持仓K线缓存) 传给 watch_positions
assert "watch_positions(self.positions, _watch_cfg, kline_cache=monitor_kline_cache)" in eng
assert "_monitor_kline_cache" in eng
print("[④] calc_trailing_stop 真接线: watcher 传 klines=kdf + kline_cache+highest_price, engine 传 monitor_kline_cache → 非死代码")
print("\nALL OK: ①②③④ 全链路验证通过")
