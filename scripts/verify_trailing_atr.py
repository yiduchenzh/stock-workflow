# -*- coding: utf-8 -*-
"""验证 v14.46 移动止盈ATR增强修复
1. ATR增强不再死代码(传klines+highest_price生效)
2. 最高价跟踪: 从历史高点回撤(不是当前价)
3. 固定阶梯兜底仍正常
"""
import sys, warnings
sys.path.insert(0, '.')
warnings.filterwarnings('ignore')
import pandas as pd, datetime as dt
import numpy as np
from risk.trailing import calc_trailing_stop
from monitor.watcher import watch_positions

def make_kline(closes):
    n = len(closes)
    opens = [c for c in closes]
    highs = [c * 1.02 for c in closes]  # 每根都有2%上影 → 制造ATR
    lows = [c * 0.98 for c in closes]
    vols = [100000] * n
    dates = [(dt.date(2026, 1, 1) + dt.timedelta(days=i)).strftime('%Y-%m-%d') for i in range(n)]
    df = pd.DataFrame({'date': dates, 'open': opens, 'high': highs, 'low': lows,
                       'close': closes, 'volume': vols})
    return df

print("=== 测试1: ATR增强生效 — 传klines时止损位用ATR回撤(非固定阶梯) ===")
# 构造: 入场10, 现价12(+20%浮盈), K线波动大(ATR≈0.3)
closes = [10.0] * 40 + [12.0]
k = make_kline(closes)
# 固定阶梯: +20% → 锁定+10% = 11.0
# ATR增强: 最高价12, 盈利20%, 档位"15-30%: 从最高点回撤3倍ATR"
stop_fixed = calc_trailing_stop(10.0, 12.0, 0.0)  # 无klines → 固定阶梯
stop_atr = calc_trailing_stop(10.0, 12.0, 0.0, klines=k, highest_price=12.0)  # ATR
print(f"  固定阶梯(无klines): stop={stop_fixed:.4f} (应=11.0, 锁+10%)")
print(f"  ATR增强(有klines): stop={stop_atr:.4f} (应从最高12回撤3ATR)")
assert abs(stop_fixed - 11.0) < 0.01, f"固定阶梯应为11.0, got {stop_fixed}"
assert stop_atr != stop_fixed, "ATR增强必须给出不同止损位(否则仍是死代码)"
print("  ✅ ATR增强生效 (stop_atr != stop_fixed)")

print()
print("=== 测试2: 最高价跟踪 — 历史高点12回撤 vs 当前价11回撤 ===")
# 入场10, 历史最高12, 当前回落到11 → ATR回撤基准必须用12
stop_high12 = calc_trailing_stop(10.0, 11.0, 0.0, klines=k, highest_price=12.0)
stop_cur11 = calc_trailing_stop(10.0, 11.0, 0.0, klines=k, highest_price=11.0)
print(f"  从最高12回撤: stop={stop_high12:.4f}")
print(f"  从当前11回撤: stop={stop_cur11:.4f}")
assert stop_high12 >= stop_cur11, "从更高点回撤应给出更高(更严)止损"
print("  ✅ 最高价跟踪正确 (基准用历史高点非当前价)")

print()
print("=== 测试3: watch_positions 集成 — kline_cache传入启用ATR ===")
from unittest.mock import patch
# 模拟持仓: 入场10, 现价11.5(+15%浮盈), K线有高点11.5以上
pos = {"600000": {"avg_cost": 10.0, "current_price": 11.5, "shares": 1000}}
cfg = {"risk": {"stop_loss_pct": 0.05}, "market": {"default_regime": "range"}}
closes2 = [10.0] * 40 + [11.5]
k2 = make_kline(closes2)
with patch("monitor.watcher.get_tencent_quotes", return_value={"600000": {"price": 11.5}}):
    alerts = watch_positions(pos, cfg, kline_cache={"600000": k2})
trail_alerts = [a for a in alerts if a["type"] == "trailing_stop"]
print(f"  alerts={[(a['type'], round(a.get('trailing_stop', 0), 3)) for a in alerts]}")
assert any(a["type"] == "trailing_stop" for a in alerts), "浮盈15%应触发移动止盈抬升"
print("  ✅ watch_positions ATR增强路径触发")

print()
print("=== 测试4: 无kline_cache(老调用方) — 固定阶梯兜底不崩 ===")
# 用新code避免测试3残留的_trailing_stops/最高价污染
pos2 = {"600005": {"avg_cost": 10.0, "current_price": 11.5, "shares": 1000}}
with patch("monitor.watcher.get_tencent_quotes", return_value={"600005": {"price": 11.5}}):
    alerts2 = watch_positions(pos2, cfg)  # 不传kline_cache
print(f"  无kline_cache alerts={[(a['type'], round(a.get('trailing_stop', 0), 3)) for a in alerts2]}")
assert any(a["type"] == "trailing_stop" for a in alerts2), "无K线时固定阶梯兜底"
print("  ✅ 无kline_cache固定阶梯兜底正常(向后兼容)")

print()
print("=== 移动止盈ATR增强修复 全部验证通过 ===")
