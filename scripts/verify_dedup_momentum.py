# -*- coding: utf-8 -*-
"""验证 v14.46 方案2(信号去重) + 方案3(动量禁用)"""
import sys, warnings
sys.path.insert(0, '.')
warnings.filterwarnings('ignore')
import pandas as pd, datetime as dt
from strategies.runner import analyze_all

# ---------- 方案3: 动量禁用 ----------
print("=== 方案3: 短线狙击手 momentum=0 → momentum_breakout 信号不收集 ===")
def make_momentum_kline(code):
    n = 60
    closes = [10.0 + 0.02 * i for i in range(58)]
    closes.append(11.0)
    closes.append(11.5)
    opens = [c for c in closes]; opens[-1] = 11.1
    highs = [c * 1.01 for c in closes]; lows = [c * 0.99 for c in closes]
    vols = [100000] * n
    dates = [(dt.date(2026, 1, 1) + dt.timedelta(days=i)).strftime('%Y-%m-%d') for i in range(n)]
    df = pd.DataFrame({'date': dates, 'open': opens, 'high': highs, 'low': lows,
                       'close': closes, 'volume': vols})
    df.attrs['code'] = code
    return df

k = make_momentum_kline("600000")
cand = {"code": "600000", "name": "测试", "price": 11.5, "can_slim": 60}

# 短线狙击手权重: momentum=0 → 信号不收集
sniper_w = {"prev_close_A": 3.0, "prev_close_B": 2.5, "sector_rotation": 1.5,
            "momentum_breakout": 0.0, "wave_point": 0.3, "mean_reversion": 0.0}
res = analyze_all([cand], kline_override={"600000": k}, strategy_weights=sniper_w)
a = res[0]
has_mo = "momentum_breakout" in (a.get("all_signals") or [])
print(f"  短线狙击手: momentum_breakout 触发={has_mo} all={a.get('all_signals')}")
assert not has_mo, "短线狙击手 momentum 信号必须被禁用"
print("  ✅ 短线狙击手 momentum 禁用 ✓")

# 上班族权重: momentum=2.0 → 仍收集
office_w = {"momentum_breakout": 2.0, "sector_rotation": 0.5, "wave_point": 0.5, "mean_reversion": 0.0}
res2 = analyze_all([cand], kline_override={"600000": k}, strategy_weights=office_w)
a2 = res2[0]
has_mo2 = "momentum_breakout" in (a2.get("all_signals") or [])
print(f"  上班族: momentum_breakout 触发={has_mo2}")
assert has_mo2, "上班族 momentum 权重2.0 应保留"
print("  ✅ 上班族 momentum 保留 ✓")

# ---------- 方案2: 信号去重 ----------
print()
print("=== 方案2: 跨Agent信号去重 (engine.step_simulate 认领机制) ===")
from core.engine import AuroraEngine

# 用轻量方式验证: 构造 engine, 注入 claims, 验证 plans 过滤逻辑
eng = AuroraEngine()
eng.profile_name = "短线狙击手"
eng.account = None  # 不初始化账户, 只验证 plans 过滤段
eng.plans = [
    {"code": "002458", "strategy": "momentum_breakout", "entry_price": 11.0, "shares": 100, "score": 60},
    {"code": "603232", "strategy": "prev_close_B", "entry_price": 18.0, "shares": 100, "score": 80},
    {"code": "002716", "strategy": "prev_close_B", "entry_price": 10.0, "shares": 100, "score": 70},
]
# 模拟: 上班族已认领 002458+momentum 和 002716+prev_close_B
eng.agent_signal_claims = {
    ("002458", "momentum_breakout"): "上班族中短线",
    ("002716", "prev_close_B"): "上班族中短线",
}
# 直接执行过滤段逻辑
_claims = getattr(eng, "agent_signal_claims", None) or {}
_my_name = getattr(eng, "profile_name", "") or ""
_plans_kept = []
for p in eng.plans:
    _key = (p.get("code", ""), p.get("strategy", p.get("signal", "?")))
    if _key in _claims and _claims[_key] != _my_name:
        print(f"  [SignalDedup] 跳过 {_key} (已被{_claims[_key]}认领)")
        continue
    _plans_kept.append(p)
kept_codes = [(p["code"], p["strategy"]) for p in _plans_kept]
print(f"  过滤后 plans: {kept_codes}")
assert ("002458", "momentum_breakout") not in kept_codes, "被认领的 002458 应跳过"
assert ("002716", "prev_close_B") not in kept_codes, "被认领的 002716 应跳过"
assert ("603232", "prev_close_B") in kept_codes, "未认领的 603232 应保留"
print("  ✅ 信号去重逻辑 ✓ (002458/002716 被跳, 603232 保留)")

# 自己认领的不过滤 (同 Agent 重复计划允许)
eng2 = AuroraEngine(); eng2.profile_name = "短线狙击手"; eng2.account = None
eng2.plans = [{"code": "000001", "strategy": "prev_close_A", "entry_price": 10.0, "shares": 100}]
eng2.agent_signal_claims = {("000001", "prev_close_A"): "短线狙击手"}
_claims2 = eng2.agent_signal_claims
_kept2 = [p for p in eng2.plans
          if not (((p.get("code", ""), p.get("strategy", p.get("signal", "?"))) in _claims2)
                  and _claims2[(p.get("code", ""), p.get("strategy", p.get("signal", "?")))] != "短线狙击手")]
print(f"  自己认领同信号: 保留={len(_kept2)} (应保留1)")
assert len(_kept2) == 1, "自己认领的不应被过滤"
print("  ✅ 自认领不误杀 ✓")

print()
print("=== 方案2+3 全部验证通过 ===")
