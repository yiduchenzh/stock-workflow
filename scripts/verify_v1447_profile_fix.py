# -*- coding: utf-8 -*-
"""验证 v14.47 全部修复: 信号白名单 + prev_close 权重过滤 + 止盈画像差异化"""
import sys, warnings
sys.path.insert(0, '.')
warnings.filterwarnings('ignore')
import pandas as pd, datetime as dt
from risk.position import plan_positions
from strategies.runner import analyze_all
from risk.trailing import calc_trailing_stop

def make_kline(code):
    n = 60
    closes = [10.0 + 0.03 * i for i in range(58)]
    closes.append(11.5); closes.append(12.3)
    opens = [c for c in closes]; opens[-1] = 11.6
    highs = [c * 1.01 for c in closes]; lows = [c * 0.99 for c in closes]
    lows[-1] = 11.5
    vols = [100000] * n
    dates = [(dt.date(2026, 1, 1) + dt.timedelta(days=i)).strftime('%Y-%m-%d') for i in range(n)]
    df = pd.DataFrame({'date': dates, 'open': opens, 'high': highs, 'low': lows,
                       'close': closes, 'volume': vols})
    df.attrs['code'] = code
    return df

k = make_kline("600000")
cand = [{"code": "600000", "name": "测试", "price": 12.3, "can_slim": 60,
         "strong_grade": "A", "strong_score": 90}]

print("=== P1a: prev_close 权重过滤 — 不同 Agent 信号收集 ===")
# 短线狙击手: prev_close_A/B 权重>0 → 收集
sniper_w = {"prev_close_A": 3.0, "prev_close_B": 2.5, "sector_rotation": 1.5,
            "momentum_breakout": 0.0, "wave_point": 0.3, "mean_reversion": 0.0}
r1 = analyze_all(cand, kline_override={"600000": k}, strategy_weights=sniper_w)
a1 = r1[0]
has_pc_s = any(s.startswith("prev_close_") for s in (a1.get("all_signals") or []))
print(f"  短线狙击手: prev_close 收集={has_pc_s} all={a1.get('all_signals')}")
assert has_pc_s, "短线狙击手应有 prev_close 信号"

# 价值投资者: 无 prev_close 权重 → 不收集
value_w = {"momentum_breakout": 1.5, "mean_reversion": 0.5, "wave_point": 0.5, "sector_rotation": 0.0}
r2 = analyze_all(cand, kline_override={"600000": k}, strategy_weights=value_w)
a2 = r2[0]
has_pc_v = any(s.startswith("prev_close_") for s in (a2.get("all_signals") or []))
print(f"  价值投资者: prev_close 收集={has_pc_v} all={a2.get('all_signals')}")
assert not has_pc_v, "价值投资者不应有 prev_close 信号"
print("  ✅ P1a: prev_close 仅短线狙击手收集")

print()
print("=== P0: plan_positions 信号白名单 ===")
# 构造 scores: best_strategy=prev_close_B (模拟穿透场景)
scores = [
    {"code": "600000", "name": "测试", "signal": True, "best_strategy": "prev_close_B",
     "entry_price": 12.3, "price": 12.3, "stop_loss": 11.0, "composite": 80, "confidence": 0.6},
]
# 价值投资者白名单 (无 prev_close) → 应被过滤
value_allow = {"momentum_breakout": 1.5, "mean_reversion": 0.5, "ma_breakout": 0.5, "wave_point": 0.5}
plans_v = plan_positions(scores, 1_000_000, {"risk": {"max_positions": 3}}, None,
                         profile_name="价值投资者", signal_allow=value_allow)
print(f"  价值投资者白名单: plans={len(plans_v)} (应=0, prev_close_B 被过滤)")
assert len(plans_v) == 0, "价值投资者 prev_close_B 应被白名单拦截"
# 短线狙击手白名单 (含 prev_close) → 应通过
sniper_allow = {"prev_close_A": 3.0, "prev_close_B": 2.5, "first_board": 2.0, "sector_rotation": 2.0,
                "naked_pinbar": 1.5, "naked_engulf": 1.0, "williams_r": 1.5, "orb": 1.0, "pullback": 1.0}
plans_s = plan_positions(scores, 1_000_000, {"risk": {"max_positions": 3}}, None,
                         profile_name="短线狙击手", signal_allow=sniper_allow)
print(f"  短线狙击手白名单: plans={len(plans_s)} (应=1, prev_close_B 放行)")
assert len(plans_s) == 1, "短线狙击手 prev_close_B 应放行"
print("  ✅ P0: 白名单过滤生效")

print()
print("=== P1b: 止盈画像差异化 ===")
# 价值投资者: 浮盈 8% 不应触发保本(阈值 5×1.5=7.5% → 8%>7.5% 触发... 用 6% 验证不触发)
stop_value_6 = calc_trailing_stop(10.0, 10.6, 0.0, profile_name="价值投资者")
stop_sniper_6 = calc_trailing_stop(10.0, 10.6, 0.0, profile_name="短线狙击手")
print(f"  浮盈6%: 价值投资者 stop={stop_value_6} (阈值7.5% → 不触发=0) / 短线 stop={stop_sniper_6} (阈值5% → 触发保本=10.0)")
assert stop_value_6 == 0, "价值投资者 6% 不应触发(阈值7.5%)"
assert stop_sniper_6 == 10.0, "短线狙击手 6% 应触发保本(阈值5%)"
# 价值投资者 8% → 触发保本
stop_value_8 = calc_trailing_stop(10.0, 10.8, 0.0, profile_name="价值投资者")
print(f"  浮盈8%: 价值投资者 stop={stop_value_8} (8%>7.5% → 触发保本=10.0)")
assert stop_value_8 == 10.0, "价值投资者 8% 应触发保本"
print("  ✅ P1b: 止盈阈值按画像差异化")

print()
print("=== v14.47 全部修复验证通过 ===")
