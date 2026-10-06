# -*- coding: utf-8 -*-
"""阶段2 终验: 模拟 engine._apply_profile 注入顺序(core/engine.py:154-173), 打印 5 画像有效权重

不实例化引擎(无需行情/不碰状态), 只走 profiling.strategy_mapping 的配置链:
    cfg[risk][strategy_weights] ← profile.strategy_weights  (engine.py:163)
    cfg[risk][strategy_weights] ← SCREENING_CONFIGS.signal_prefer  (engine.py:170, 后应用=覆盖)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from profiling.strategy_mapping import get_engine_config, get_screening_params  # noqa: E402
from profiling.trader_types import TRADER_PROFILES  # noqa: E402

print("=" * 26, "有效权重复核（engine 注入顺序模拟）")
eff_all = {}
for nm in TRADER_PROFILES:
    pc = get_engine_config(nm)
    sp = get_screening_params(nm).get("signal_prefer") or {}
    eff = {}
    eff.update(pc.get("strategy_weights") or {})   # :163
    eff.update(sp)                                  # :170 后应用
    eff_all[nm] = eff
    conf = sorted([k for k, v in eff.items() if v >= 2.0])
    print(f"\n  {nm}")
    print(f"    risk.max_positions = {pc['risk']['max_positions']}  止损 {pc['risk']['stop_loss_pct']}")
    print(f"    可单信号确认(≥2.0): {conf}")
    print(f"    全部有效权重: {eff}")

print("\n" + "=" * 26, "不变量校验")
sets = {nm: frozenset(k for k, v in eff.items() if v >= 2.0) for nm, eff in eff_all.items()}
print(f"  ① 每个画像都有 ≥2.0 信号源(防死仓): " +
      ("✅ 全部通过" if all(s for s in sets.values()) else f"❌ {[n for n,s in sets.items() if not s]}"))
print(f"  ② 可确认信号集合种类数 ≥3(防同质化): {len(set(sets.values()))} → " +
      ("✅" if len(set(sets.values())) >= 3 else "❌"))
b = [n for n, s in sets.items() if "prev_close_B" in s]
print(f"  ③ prev_close_B 不再覆盖所有画像: {len(b)}/{len(sets)} 个画像含 B → " +
      ("✅" if len(b) < len(sets) else "❌"))
print(f"  ④ 趋势跟踪者不再依赖 momentum_breakout: " +
      ("✅" if eff_all["趋势跟踪者"].get("momentum_breakout", 0) == 0 else "❌"))
print("\n各画像主战法画像: " + " | ".join(f"{n}={sorted(s)[0] if s else '-'}" for n, s in sets.items()))
