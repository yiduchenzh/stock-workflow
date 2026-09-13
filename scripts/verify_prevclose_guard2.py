# -*- coding: utf-8 -*-
"""验证 v14.46 prev_close_B 强势池护栏 — 放行/拦截双分支合成K线"""
import sys, warnings
sys.path.insert(0, '.')
warnings.filterwarnings('ignore')
import pandas as pd, datetime as dt
from strategies.runner import analyze_all

weights = {"prev_close_A": 3.0, "prev_close_B": 2.5, "sector_rotation": 1.5,
           "momentum_breakout": 0.8, "wave_point": 0.3, "mean_reversion": 0.0}

def make_buyB_kline(code):
    """构造触发买点B的K线: 高开站稳昨收+回踩不破+收阳(涨幅7%<主板10%门槛)"""
    n = 60
    closes = [10.0 + 0.03 * i for i in range(58)]   # 缓慢上升
    closes.append(11.5)   # 昨收
    closes.append(12.3)   # 今收 +7.0%
    opens = [c for c in closes]
    opens[-1] = 11.6      # 高开
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    lows[-1] = 11.5       # 回踩不破昨收
    vols = [100000] * n
    dates = [(dt.date(2026, 1, 1) + dt.timedelta(days=i)).strftime('%Y-%m-%d') for i in range(n)]
    df = pd.DataFrame({'date': dates, 'open': opens, 'high': highs, 'low': lows,
                       'close': closes, 'volume': vols})
    df.attrs['code'] = code
    return df

def make_cand(code, name, grade, score):
    return {"code": code, "name": name, "price": 0, "can_slim": 60,
            "strong_grade": grade, "strong_score": score}

k = make_buyB_kline("600000")

print("=== 放行分支: A级强势票 + B形态 → prev_close_B 必须放行 ===")
c_a = make_cand("600000", "测试A级", "A", 90)
res = analyze_all([c_a], kline_override={"600000": k}, strategy_weights=weights)
a = res[0]
print(f"  A级: all_signals={a.get('all_signals')}")
assert "prev_close_B" in (a.get("all_signals") or []), "A级 B形态必须放行"
print("  ✅ A级放行 ✓")

print()
print("=== 放行分支: B级强势票 + B形态 → prev_close_B 必须放行 ===")
c_b = make_cand("600000", "测试B级", "B", 75)
res2 = analyze_all([c_b], kline_override={"600000": k}, strategy_weights=weights)
a2 = res2[0]
print(f"  B级: all_signals={a2.get('all_signals')}")
assert "prev_close_B" in (a2.get("all_signals") or []), "B级 B形态必须放行"
print("  ✅ B级放行 ✓")

print()
print("=== 拦截分支: C级弱票 + B形态 → prev_close_B 必须被拦 ===")
c_c = make_cand("600000", "测试C级", "C", 55)
res3 = analyze_all([c_c], kline_override={"600000": k}, strategy_weights=weights)
a3 = res3[0]
print(f"  C级: all_signals={a3.get('all_signals')}")
assert "prev_close_B" not in (a3.get("all_signals") or []), "C级 B形态必须被拦"
print("  ✅ C级拦截 ✓")

print()
print("=== 拦截分支: 无grade字段(候选未过strong_stock) + B形态 → 默认拦截 ===")
c_none = {"code": "600000", "name": "测试无级", "price": 0, "can_slim": 60}
res4 = analyze_all([c_none], kline_override={"600000": k}, strategy_weights=weights)
a4 = res4[0]
print(f"  无grade: all_signals={a4.get('all_signals')}")
assert "prev_close_B" not in (a4.get("all_signals") or []), "无grade B形态必须被拦(默认非强势)"
print("  ✅ 无grade默认拦截 ✓")

print()
print("=== prev_close_B 强势池护栏 全分支验证通过 ===")
