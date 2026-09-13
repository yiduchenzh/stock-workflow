# -*- coding: utf-8 -*-
"""方案3 验证 v2: 精确动量突破形态 — 上班族(权重2.0)保留 vs 短线狙击手(权重0)禁用"""
import sys, warnings
sys.path.insert(0, '.')
warnings.filterwarnings('ignore')
import pandas as pd, datetime as dt
from strategies.runner import analyze_all

def make_momentum_breakout(code):
    """平台整理40根 + 放量突破新高: 满足20日新高/放量1.5x/MA20>MA50/RS>60"""
    n = 60
    closes = []
    # 前20根缓慢上升建立MA50基础
    for i in range(20):
        closes.append(10.0 + i * 0.05)
    # 中20根平台整理 (10.8~11.0)
    base = closes[-1]
    for i in range(20):
        closes.append(10.95 + 0.02 * ((i % 3) - 1))
    # 后19根继续平台
    for i in range(19):
        closes.append(10.95 + 0.01 * ((i % 2) - 0.5))
    # 今日: 放量突破新高
    closes.append(12.0)
    opens = [c * 0.998 for c in closes]
    opens[-1] = 11.5
    highs = [c * 1.005 for c in closes]
    highs[-1] = 12.05
    lows = [c * 0.995 for c in closes]
    lows[-1] = 11.4
    vols = [100000] * (n - 1) + [300000]  # 最后一天3倍放量
    dates = [(dt.date(2026, 1, 1) + dt.timedelta(days=i)).strftime('%Y-%m-%d') for i in range(n)]
    df = pd.DataFrame({'date': dates, 'open': opens, 'high': highs, 'low': lows,
                       'close': closes, 'volume': vols})
    df.attrs['code'] = code
    return df

k = make_momentum_breakout("600000")
cand = {"code": "600000", "name": "测试", "price": 12.0, "can_slim": 60}

# 先确认形态本身触发 momentum (不带weights, 默认1.0)
res0 = analyze_all([cand], kline_override={"600000": k})
a0 = res0[0]
print(f"无weights: all={a0.get('all_signals')}")
assert "momentum_breakout" in (a0.get("all_signals") or []), "形态本身应触发momentum"

# 上班族: momentum=2.0 → 保留
office_w = {"momentum_breakout": 2.0, "sector_rotation": 0.5, "wave_point": 0.5, "mean_reversion": 0.0}
res1 = analyze_all([cand], kline_override={"600000": k}, strategy_weights=office_w)
a1 = res1[0]
has_o = "momentum_breakout" in (a1.get("all_signals") or [])
print(f"上班族(momentum=2.0): momentum触发={has_o}")
assert has_o, "上班族 momentum 必须保留"
print("  ✅ 上班族保留 ✓")

# 短线狙击手: momentum=0 → 禁用
sniper_w = {"prev_close_A": 3.0, "prev_close_B": 2.5, "sector_rotation": 1.5,
            "momentum_breakout": 0.0, "wave_point": 0.3, "mean_reversion": 0.0}
res2 = analyze_all([cand], kline_override={"600000": k}, strategy_weights=sniper_w)
a2 = res2[0]
has_s = "momentum_breakout" in (a2.get("all_signals") or [])
print(f"短线狙击手(momentum=0): momentum触发={has_s} all={a2.get('all_signals')}")
assert not has_s, "短线狙击手 momentum 必须禁用"
print("  ✅ 短线狙击手禁用 ✓")

# 无weights(其他Agent场景): 默认1.0 → 保留
res3 = analyze_all([cand], kline_override={"600000": k})
a3 = res3[0]
has_n = "momentum_breakout" in (a3.get("all_signals") or [])
print(f"无weights(默认1.0): momentum触发={has_n}")
assert has_n, "无weights时 momentum 应保留(默认行为)"
print("  ✅ 默认保留 ✓")

print()
print("=== 方案3 完整验证通过 ===")
