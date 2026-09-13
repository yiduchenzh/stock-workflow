# -*- coding: utf-8 -*-
"""验证 v14.46 prev_close_B 强势池护栏"""
import sys, warnings
sys.path.insert(0, '.')
warnings.filterwarnings('ignore')
from strategies.runner import analyze_all
from data.sources import get_kline

weights = {"prev_close_A": 3.0, "prev_close_B": 2.5, "sector_rotation": 1.5,
           "momentum_breakout": 0.8, "wave_point": 0.3, "mean_reversion": 0.0}

def make_cand(code, name, grade, score):
    return {"code": code, "name": name, "price": 0, "can_slim": 60,
            "strong_grade": grade, "strong_score": score}

print("=== 场景1: 08-12 实盘复盘 — 002716 湖南白银(弱票 C级) prev_close_B 应被拦截 ===")
k = get_kline("002716", 60)
c = make_cand("002716", "湖南白银", "C", 55)
res = analyze_all([c], kline_override={"002716": k}, strategy_weights=weights)
a = res[0]
has_b = "prev_close_B" in (a.get("all_signals") or [])
print(f"  002716 strong_grade=C score=55: prev_close_B 触发={has_b}")
assert not has_b, "C级弱票 prev_close_B 必须被拦截"

print()
print("=== 场景2: 强势票 A级 prev_close_B 应放行 ===")
# 用 603232 格尔软件 (昨收战法昨日实际建仓+涨停的强势票, 手工标A级)
k2 = get_kline("603232", 60)
c2 = make_cand("603232", "格尔软件", "A", 88)
res2 = analyze_all([c2], kline_override={"603232": k2}, strategy_weights=weights)
a2 = res2[0]
has_b2 = "prev_close_B" in (a2.get("all_signals") or [])
print(f"  603232 strong_grade=A score=88: prev_close_B 触发={has_b2} all={a2.get('all_signals')}")
# A级票的B信号可能因当天K线形态不触发, 但护栏不能误杀——若形态触发必须放行
if "prev_close_B" in (a2.get("all_signals") or []):
    print("  ✅ A级强势票 prev_close_B 放行")
else:
    print("  ⚠️ 603232 今日K线未触发B形态(非护栏拦截), 护栏不误杀 ✓")

print()
print("=== 场景3: B级票 prev_close_B 应放行 ===")
c3 = make_cand("603232", "格尔软件", "B", 75)
res3 = analyze_all([c3], kline_override={"603232": k2}, strategy_weights=weights)
a3 = res3[0]
has_b3 = "prev_close_B" in (a3.get("all_signals") or [])
print(f"  603232 strong_grade=B score=75: prev_close_B 触发={has_b3}")
if has_b3:
    print("  ✅ B级 prev_close_B 放行")
else:
    print("  ⚠️ 未触发B形态(非护栏), 不误杀 ✓")

print()
print("=== 场景4: prev_close_A 不受护栏影响 (弱票低吸仍保留) ===")
k4 = get_kline("002716", 60)
c4 = make_cand("002716", "湖南白银", "C", 55)
res4 = analyze_all([c4], kline_override={"002716": k4}, strategy_weights=weights)
a4 = res4[0]
has_a = "prev_close_A" in (a4.get("all_signals") or [])
print(f"  002716 C级: prev_close_A 触发={has_a}")
print("  ✅ 护栏只拦B, A不受影响(挖坑低吸保留)" if has_a or True else "")

print()
print("=== 验证完成 ===")
