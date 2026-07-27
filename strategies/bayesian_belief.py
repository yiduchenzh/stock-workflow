"""
[Soul] 贝叶斯信念更新 — 每次决策后更新策略先验概率
- update_belief: 更新单个策略的后验胜率
- get_adjusted_kelly: 根据信念调整凯利公式
- 持久化: data/beliefs.json
"""
import logging
import json
import os
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("aurora.soul.bayesian_belief")

PROJ = Path(__file__).resolve().parent.parent
BELIEFS_PATH = PROJ / "data" / "beliefs.json"

# 默认先验: 每个策略Beta分布参数 (alpha=成功次数+1, beta=失败次数+1)
_DEFAULT_BELIEFS = {
    "momentum_breakout": {"alpha": 6, "beta": 4, "trades": 0, "last_update": ""},
    "sector_rotation": {"alpha": 5, "beta": 5, "trades": 0, "last_update": ""},
    "wave_point": {"alpha": 5, "beta": 5, "trades": 0, "last_update": ""},
    "mean_reversion": {"alpha": 4, "beta": 6, "trades": 0, "last_update": ""},
    "chan_": {"alpha": 5, "beta": 5, "trades": 0, "last_update": ""},
    "naked_": {"alpha": 4, "beta": 6, "trades": 0, "last_update": ""},
    "elliott_wave": {"alpha": 4, "beta": 6, "trades": 0, "last_update": ""},
    "mtf_resonance": {"alpha": 5, "beta": 5, "trades": 0, "last_update": ""},
}


def _load_beliefs() -> dict:
    """从 data/beliefs.json 加载信念, 不存在则返回默认"""
    try:
        if BELIEFS_PATH.exists():
            with open(BELIEFS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 补充缺失策略的默认值
            for name, default in _DEFAULT_BELIEFS.items():
                if name not in data:
                    data[name] = dict(default)
            return data
        else:
            return {k: dict(v) for k, v in _DEFAULT_BELIEFS.items()}
    except Exception as e:
        logger.warning(f"[Soul] 加载beliefs.json失败: {e}")
        return {k: dict(v) for k, v in _DEFAULT_BELIEFS.items()}


def _save_beliefs(beliefs: dict):
    """持久化信念到 data/beliefs.json"""
    try:
        BELIEFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(BELIEFS_PATH, "w", encoding="utf-8") as f:
            json.dump(beliefs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"[Soul] 保存beliefs.json失败: {e}")


def update_belief(strategy_name: str, outcome: bool) -> dict:
    """
    贝叶斯更新策略信念: Beta(alpha, beta) ← Beta(alpha+赢, beta+输)
    Args:
        strategy_name: 策略名称
        outcome: True=盈利, False=亏损
    Returns:
        dict: {strategy_name: {alpha, beta, win_rate, trades, last_update}}
    """
    try:
        beliefs = _load_beliefs()

        # 模糊匹配: 如果精确名称不存在, 尝试前缀匹配
        if strategy_name not in beliefs:
            matched = False
            for key in beliefs:
                if key.endswith("_") and strategy_name.startswith(key.rstrip("_")):
                    beliefs[strategy_name] = dict(beliefs[key])
                    matched = True
                    break
            if not matched:
                beliefs[strategy_name] = {"alpha": 3, "beta": 3, "trades": 0, "last_update": ""}

        entry = beliefs[strategy_name]
        if outcome:
            entry["alpha"] += 1
        else:
            entry["beta"] += 1
        entry["trades"] += 1
        entry["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        # 防止数值溢出
        entry["alpha"] = min(entry["alpha"], 1000)
        entry["beta"] = min(entry["beta"], 1000)

        win_rate = entry["alpha"] / (entry["alpha"] + entry["beta"])
        _save_beliefs(beliefs)

        logger.info(f"[Soul] update_belief: {strategy_name} "
                     f"outcome={'WIN' if outcome else 'LOSS'} "
                     f"wr={win_rate:.3f} trades={entry['trades']}")

        return {
            strategy_name: {
                "alpha": entry["alpha"],
                "beta": entry["beta"],
                "win_rate": round(win_rate, 4),
                "trades": entry["trades"],
                "last_update": entry["last_update"],
            }
        }
    except Exception as e:
        logger.warning(f"[Soul] update_belief 异常: {e}")
        return {strategy_name: {"alpha": 3, "beta": 3, "win_rate": 0.5, "trades": 0, "last_update": ""}}


def get_adjusted_kelly(base_kelly: float, strategy: str, regime: str) -> float:
    """
    根据贝叶斯信念调整凯利比率
    Args:
        base_kelly: 原始凯利比率(0~1)
        strategy: 策略名称
        regime: 市场状态(bull_strong/bull_weak/range/bear_weak/bear_strong)
    Returns:
        float: 调整后的凯利比率
    """
    try:
        beliefs = _load_beliefs()

        # 模糊匹配策略名称
        entry = None
        if strategy in beliefs:
            entry = beliefs[strategy]
        else:
            for key in beliefs:
                if key.endswith("_") and strategy.startswith(key.rstrip("_")):
                    entry = beliefs[key]
                    break

        if entry is None or entry["trades"] < 3:
            # 样本不足, 使用原始凯利
            adjusted = base_kelly
            logger.debug(f"[Soul] get_adjusted_kelly: {strategy} 样本不足, 使用原始kelly={base_kelly:.3f}")
        else:
            # 后验胜率
            posterior_wr = entry["alpha"] / (entry["alpha"] + entry["beta"])
            # 原始凯利 * (0.5 + 后验胜率 / 2) — 信念越强, 越接近原始凯利
            # 当 posterior_wr=0.5时乘数=0.75, posterior_wr=1.0时乘数=1.0
            multiplier = 0.5 + posterior_wr / 2
            adjusted = base_kelly * multiplier

        # 市场状态调整
        regime_mult = {
            "bull_strong": 1.0,
            "bull_weak": 0.85,
            "range": 0.7,
            "bear_weak": 0.5,
            "bear_strong": 0.3,
        }.get(regime, 0.7)
        adjusted *= regime_mult

        adjusted = max(0.01, min(0.5, round(adjusted, 4)))
        logger.debug(f"[Soul] get_adjusted_kelly: {strategy} "
                     f"base={base_kelly:.3f} adj={adjusted:.3f} regime={regime}")
        return adjusted
    except Exception as e:
        logger.warning(f"[Soul] get_adjusted_kelly 异常: {e}")
        return base_kelly


def get_belief_summary() -> dict:
    """获取所有策略的信念汇总"""
    try:
        beliefs = _load_beliefs()
        summary = {}
        for name, entry in beliefs.items():
            summary[name] = {
                "win_rate": round(entry["alpha"] / (entry["alpha"] + entry["beta"]), 4),
                "trades": entry["trades"],
                "confidence": round(
                    (entry["alpha"] - entry["beta"]) / (entry["alpha"] + entry["beta"]), 4
                ) if entry["trades"] > 0 else 0,
                "last_update": entry["last_update"],
            }
        return summary
    except Exception as e:
        logger.warning(f"[Soul] get_belief_summary 异常: {e}")
        return {}
