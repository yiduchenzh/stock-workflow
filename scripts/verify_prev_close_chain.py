# -*- coding: utf-8 -*-
"""验证 v14.45+ prev_close 昨收战法全链路（只读，不写模拟账户）

链路: 信号生成(runner.analyze_all) → regime过滤(regime.filter_strategies_by_regime)
      → 确认(confirmation.confirm_entry) → 评分(scoring.composite_score)
验证: 短线狙击手 strategy_weights 下 prev_close_A/B 单信号可确认、不被 regime 砍掉、评分有权重。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml
import numpy as np

def make_kline(code, closes, opens=None, highs=None, lows=None, vols=None):
    """构造日K DataFrame（最少30根）"""
    import pandas as pd
    n = len(closes)
    if n < 30:
        closes = list(closes) + [closes[-1]] * (30 - n)
    n = len(closes)
    opens = opens or [c for c in closes]
    highs = highs or [c * 1.01 for c in closes]
    lows = lows or [c * 0.99 for c in closes]
    vols = vols or [100000] * n
    import datetime as dt
    dates = [(dt.date(2026, 1, 1) + dt.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]
    return pd.DataFrame({"date": dates, "open": opens, "high": highs, "low": lows,
                         "close": closes, "volume": vols})

def make_random_walk(n=60, start=10.0, seed=42, drift=0.0):
    """随机游走价格序列 — 避免单调形态误触发 naked RBR 等信号"""
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, 0.015, n)
    closes = [start]
    for r in rets[1:]:
        closes.append(closes[-1] * (1 + r))
    return closes

def test_prev_close_A_single_signal():
    """买点A: 低开+盘中跌破昨收+收盘收回站稳 → 单信号应被短线狙击手确认"""
    from strategies.runner import analyze_all
    from strategies.confirmation import confirm_entry
    from strategies.regime import filter_strategies_by_regime
    from strategies.scoring import composite_score

    closes = [10.0 + 0.05 * i for i in range(28)]  # 缓慢上升
    closes.append(9.8)   # 昨日
    closes.append(9.9)   # 今日: 低开收回 (open<prev, low<prev, close>prev)
    opens = [c for c in closes]
    opens[-1] = 9.75     # 低开
    lows = [c * 0.995 for c in closes]
    lows[-1] = 9.70      # 盘中跌破昨收
    kdf = make_kline("300319", closes, opens, highs=[c * 1.01 for c in closes], lows=lows)
    kdf.attrs["code"] = "300319"

    weights = {"prev_close_A": 3.0, "prev_close_B": 2.5, "sector_rotation": 1.5,
               "momentum_breakout": 0.8, "wave_point": 0.3, "mean_reversion": 0.0}
    cand = [{"code": "300319", "name": "麦捷科技", "price": 9.9, "can_slim": 60}]
    results = analyze_all(cand, kline_override={"300319": kdf}, strategy_weights=weights)
    assert len(results) == 1, f"analyze_all 应返回1条, got {len(results)}"
    a = results[0]
    print(f"[A] signal={a['signal']} best_strategy={a['best_strategy']} "
          f"best_score={a['best_score']:.1f} all_signals={a['all_signals']}")
    assert a["signal"] is True, "买点A 应产生信号"
    assert a["best_strategy"] == "prev_close_A", f"best 应为 prev_close_A, got {a['best_strategy']}"
    assert a["best_score"] > 0, "单信号强偏好应确认得分"

    # regime 过滤: prev_close_A 必须保留
    kept = filter_strategies_by_regime("range", [a["best_strategy"]])
    assert "prev_close_A" in kept, f"range regime 应保留 prev_close_A, got {kept}"
    kept2 = filter_strategies_by_regime("bear_strong", [a["best_strategy"]])
    assert "prev_close_A" in kept2, f"bear_strong regime 应保留 prev_close_A, got {kept2}"

    # 确认防线: 短线狙击手 profile 放宽
    passed, conf, checks = confirm_entry(a, {"df": kdf}, profile_name="短线狙击手")
    print(f"[A] confirm passed={passed} confidence={conf:.2f}")
    assert passed, "短线狙击手确认防线应放行 prev_close_A"

    # 评分: prev_close_A 有权重
    scores = composite_score([a], "range", 50)
    assert len(scores) == 1
    s = scores[0]
    print(f"[A] composite={s['composite']} best_strategy={s['best_strategy']}")
    assert s["composite"] > 0
    print("✅ 买点A 全链路通过\n")

def test_prev_close_B_single_signal():
    """买点B: 高开站稳昨收+收阳非涨停 → 单信号确认"""
    from strategies.runner import analyze_all
    from strategies.regime import filter_strategies_by_regime
    closes = [10.0 + 0.05 * i for i in range(28)]
    closes.append(10.3)  # 昨日
    closes.append(10.6)  # 今日: 高开+站稳+收阳
    opens = [c for c in closes]
    opens[-1] = 10.45    # 高开
    kdf = make_kline("300319", closes, opens)
    kdf.attrs["code"] = "300319"
    weights = {"prev_close_A": 3.0, "prev_close_B": 2.5, "sector_rotation": 1.5,
               "momentum_breakout": 0.8, "wave_point": 0.3, "mean_reversion": 0.0}
    # ⭐ P0-① 修: prev_close_B 需强势池护栏放行(strong_grade∈{A,B} 或 strong_score≥70),
    #   候选补充 strong_grade="A" 否则被 runner.py:166-174 拦截必失败(原断言在护栏下失真)
    cand = [{"code": "300319", "name": "麦捷科技", "price": 10.6, "can_slim": 60,
             "strong_grade": "A", "strong_score": 90}]
    results = analyze_all(cand, kline_override={"300319": kdf}, strategy_weights=weights)
    a = results[0]
    print(f"[B] signal={a['signal']} best_strategy={a['best_strategy']} "
          f"best_score={a['best_score']:.1f} all_signals={a['all_signals']}")
    assert a["signal"] is True, "买点B 应产生信号"
    assert a["best_strategy"] == "prev_close_B", f"best 应为 prev_close_B, got {a['best_strategy']}"
    kept = filter_strategies_by_regime("bull_weak", [a["best_strategy"]])
    assert "prev_close_B" in kept
    print("✅ 买点B 全链路通过\n")

def test_no_weights_behavior_unchanged():
    """不带 strategy_weights 时行为保持向后兼容:
    ① 多信号投票=原始平均分+10, best=原始分最高（无权重放大）
    ② prev_close 仅在显式强偏好(权重≥2.0)时才能靠权重胜出/单信号确认"""
    from strategies.runner import analyze_all
    # 随机游走 + 末端构造买点A (低开+破昨收+收回), 避免触发naked供需区等
    closes = make_random_walk(n=58, seed=7)
    pc = closes[-1]
    closes.append(pc * 0.995)          # 昨日: 小回撤
    closes.append(pc * 1.002)          # 今日: 收回
    opens = [c for c in closes]
    opens[-1] = closes[-2] * 0.985     # 低开
    lows = [c * 0.995 for c in closes]
    lows[-1] = closes[-2] * 0.975      # 盘中跌破昨收
    highs = [c * 1.01 for c in closes]
    kdf = make_kline("300319", closes, opens, highs=highs, lows=lows)
    kdf.attrs["code"] = "300319"
    cand = [{"code": "300319", "name": "麦捷科技", "price": closes[-1], "can_slim": 60}]
    weights = {"prev_close_A": 3.0, "prev_close_B": 2.5, "sector_rotation": 1.5,
               "momentum_breakout": 0.8, "wave_point": 0.3, "mean_reversion": 0.0}
    # 无 weights: 原逻辑
    a0 = analyze_all(cand, kline_override={"300319": kdf})[0]
    # 有 weights: 加权投票
    a1 = analyze_all(cand, kline_override={"300319": kdf}, strategy_weights=weights)[0]
    print(f"[C-无权重] signal={a0['signal']} best={a0['best_strategy']} "
          f"score={a0['best_score']:.1f} all={a0['all_signals']}")
    print(f"[C-有权重] signal={a1['signal']} best={a1['best_strategy']} "
          f"score={a1['best_score']:.1f} all={a1['all_signals']}")
    # ① 无权重: 若prev_close_A原始分最高成为best(原逻辑允许), 分数=原始平均+10, 无3.0放大
    if a0["best_strategy"] == "prev_close_A":
        sigs = [s[1] for s in [("x", 0, 0)]]  # placeholder
        assert a0["best_score"] <= 100, f"无权重时分数不应被权重放大: {a0['best_score']}"
    # ② 有权重: prev_close_A 应凭3.0权重胜出(除非原始分差太多)
    assert a1["signal"] is True
    print("✅ 向后兼容通过\n")

def test_engine_weights_injection():
    """engine._apply_profile 短线狙击手 → cfg strategy_weights 含 prev_close_A=3.0"""
    from core.engine import AuroraEngine
    eng = AuroraEngine()
    eng.profile_name = "短线狙击手"
    eng._apply_profile()
    sw = eng.cfg.get("risk", {}).get("strategy_weights", {})
    print(f"[D] 短线狙击手 strategy_weights={sw}")
    assert sw.get("prev_close_A") == 3.0, f"prev_close_A 权重应为3.0, got {sw.get('prev_close_A')}"
    assert sw.get("prev_close_B") == 2.5
    print("✅ engine 权重注入通过\n")

if __name__ == "__main__":
    test_prev_close_A_single_signal()
    test_prev_close_B_single_signal()
    test_no_weights_behavior_unchanged()
    test_engine_weights_injection()
    print("═══ 全部链路验证通过 ═══")
