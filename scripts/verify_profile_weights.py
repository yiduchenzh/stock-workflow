# -*- coding: utf-8 -*-
"""画像权重/差异化探针 — 零副作用(不实例化引擎 / 不碰行情 / 不写状态)

用途: 改完 `profiling/trader_types.py` 的画像权重后**必跑**, 校验 4 条不变量。
在项目根运行:
    .\\.venv\\Scripts\\python.exe <this>.py          # 或 python <this>.py
    # 输出重定向到文件再读(避免中文控制台 GBK 乱码):
    .\\.venv\\Scripts\\python.exe <this>.py > out_w.txt 2>&1 ; Get-Content out_w.txt -Encoding UTF8

为什么不直接读配置文件数字:
    engine._apply_profile()(core/engine.py) 先注入 `strategy_weights`,
    **后**注入 `SCREENING_CONFIGS[profile].signal_prefer`(后应用 = 覆盖)
    → 引擎里的**有效权重 = 并集且 signal_prefer 胜**。只看 strategy_weights 会误判。

不变量(任何一条挂掉都别提交):
    ① 每个画像至少有 1 个 ≥2.0 权重信号源  → 否则 runner 单信号确认永不达 = 死账户
    ② 可单信号确认(≥2.0)集合的**种类数 ≥3** → 否则画像同质化(全体做同一战法)
    ③ 指定的"不该通用"战法不得出现在全部画像里(默认 prev_close_B) → 防白名单全放行
    ④ 指定画像不得再依赖权重为 0 的战法(默认 趋势跟踪者/momentum_breakout)

⚠️ 差异化铁律: 只能"加权主导", 绝不能把某画像唯一信号源降到确认门槛下(会重演死账户)。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for cand in (ROOT, ROOT.parent):
    if (cand / "profiling" / "trader_types.py").exists():
        ROOT = cand
        break
sys.path.insert(0, str(ROOT))

GENERIC_SIGNAL = "prev_close_B"          # ③ 不应覆盖全部画像的战法
SPECIAL_PROFILE = "趋势跟踪者"            # ④ 样板画像
DEAD_STRATEGY = "momentum_breakout"      # ④ 该画像不应再依赖(历史权重 0)

from profiling.trader_types import TRADER_PROFILES  # noqa: E402
from profiling.strategy_mapping import get_engine_config, get_screening_params  # noqa: E402

print("=" * 26, "有效权重复核（engine._apply_profile 注入顺序模拟）")
eff_all, conf_sets = {}, {}
for nm in TRADER_PROFILES:
    pc = get_engine_config(nm)
    sp = get_screening_params(nm).get("signal_prefer") or {}
    eff = {}
    eff.update(pc.get("strategy_weights") or {})   # engine.py:163 先注入
    eff.update(sp)                                 # engine.py:170 后注入(=覆盖)
    eff_all[nm], conf_sets[nm] = eff, frozenset(k for k, v in eff.items() if v >= 2.0)
    print(f"\n  {nm}")
    print(f"    risk.max_positions = {pc['risk']['max_positions']}  止损 {pc['risk']['stop_loss_pct']}")
    print(f"    可单信号确认(≥2.0): {sorted(conf_sets[nm])}")
    print(f"    全部有效权重: {eff}")

print("\n" + "=" * 26, "不变量校验")
checks = [
    ("① 每个画像都有 ≥2.0 信号源(防死仓)",
     all(conf_sets.values()), [n for n, s in conf_sets.items() if not s]),
    ("② 可确认信号集合种类数 ≥3(防同质化)",
     len(set(conf_sets.values())) >= 3, f"{len(set(conf_sets.values()))} 种: {set(conf_sets.values())}"),
    (f"③ {GENERIC_SIGNAL} 不覆盖全部画像",
     len([n for n, s in conf_sets.items() if GENERIC_SIGNAL in s]) < len(conf_sets),
     [n for n, s in conf_sets.items() if GENERIC_SIGNAL in s]),
    (f"④ {SPECIAL_PROFILE} 不再依赖 {DEAD_STRATEGY}(权重 0)",
     eff_all.get(SPECIAL_PROFILE, {}).get(DEAD_STRATEGY, 0) == 0,
     eff_all.get(SPECIAL_PROFILE, {}).get(DEAD_STRATEGY)),
]
ok = True
for desc, passed, detail in checks:
    ok &= bool(passed)
    print(f"  {desc}: {'✅' if passed else '❌ 详情=' + str(detail)}")
print(f"\n  各画像主战法: " + " | ".join(
    f"{n}={sorted(s)[0] if s else '-'}" for n, s in conf_sets.items()))
print("\n  结论: " + ("✅ 全部通过" if ok else "❌ 有项未通过, 不要提交"))
sys.exit(0 if ok else 1)
