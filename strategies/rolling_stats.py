"""策略滚动胜率+信号IC v1.0 — 策略健康度、信息系数、退化检测"""
import json, logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict

PROJ = Path(__file__).resolve().parent.parent
STATS_FILE = PROJ / "data" / "rolling_stats.json"
logger = logging.getLogger("aurora.rolling_stats")

ROLLING_WINDOW = 20
DEGENERATE_WR_THRESHOLD = 0.30


def _load_stats() -> dict:
    if not STATS_FILE.exists():
        return {"strategies": {}, "signals": {}}
    try:
        return json.loads(STATS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[RollingStats] 加载失败: {e}")
        return {"strategies": {}, "signals": {}}


def _save_stats(stats: dict):
    STATS_FILE.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")


def update_rolling_stats(strategy: str, pnl_pct: float):
    """
    每笔交易后更新该策略的近20笔滚动胜率
    strategy: 策略名称 (如 'momentum_breakout')
    pnl_pct: 该笔交易盈亏百分比 (如 0.03 表示+3%)
    """
    stats = _load_stats()
    strat = stats["strategies"].setdefault(strategy, {
        "all_trades": [],
        "rolling_trades": [],
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "total_pnl": 0.0,
        "last_updated": "",
    })

    is_win = 1 if pnl_pct > 0 else 0
    trade_record = {
        "pnl_pct": round(pnl_pct, 4),
        "is_win": is_win,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    strat["all_trades"].append(trade_record)
    strat["rolling_trades"].append(trade_record)
    strat["total_trades"] += 1
    strat["wins"] += is_win
    strat["losses"] += (1 - is_win)
    strat["total_pnl"] = round(strat["total_pnl"] + pnl_pct, 4)
    strat["last_updated"] = trade_record["time"]

    # 仅保留最近ROLLING_WINDOW笔
    if len(strat["rolling_trades"]) > ROLLING_WINDOW:
        strat["rolling_trades"] = strat["rolling_trades"][-ROLLING_WINDOW:]

    _save_stats(stats)
    wr_rolling = sum(t["is_win"] for t in strat["rolling_trades"]) / max(len(strat["rolling_trades"]), 1)
    logger.info(f"[RollingStats] {strategy}: wr_20={wr_rolling:.2%} ({len(strat['rolling_trades'])}/{ROLLING_WINDOW})")


def get_strategy_health(strategy: str) -> dict:
    """获取策略健康度报告"""
    stats = _load_stats()
    strat = stats["strategies"].get(strategy)
    if not strat or strat["total_trades"] == 0:
        return {
            "strategy": strategy,
            "wr_20": 0.0,
            "wr_all": 0.0,
            "avg_pnl": 0.0,
            "trend": "unknown",
            "confidence": 0.0,
            "total_trades": 0,
        }

    rolling = strat["rolling_trades"]
    wr_20 = sum(t["is_win"] for t in rolling) / max(len(rolling), 1)
    wr_all = strat["wins"] / max(strat["total_trades"], 1)
    avg_pnl = round(strat["total_pnl"] / strat["total_trades"], 4)

    # 趋势判断: 将rolling_trades分成前后两半
    trend = "stable"
    if len(rolling) >= 10:
        half = len(rolling) // 2
        first_half_wr = sum(t["is_win"] for t in rolling[:half]) / max(half, 1)
        second_half_wr = sum(t["is_win"] for t in rolling[half:]) / max(len(rolling) - half, 1)
        if second_half_wr > first_half_wr + 0.1:
            trend = "improving"
        elif second_half_wr < first_half_wr - 0.1:
            trend = "declining"

    # 置信度: 基于交易样本量
    confidence = min(strat["total_trades"] / 50.0, 1.0)

    return {
        "strategy": strategy,
        "wr_20": round(wr_20, 4),
        "wr_all": round(wr_all, 4),
        "avg_pnl": avg_pnl,
        "trend": trend,
        "confidence": round(confidence, 2),
        "total_trades": strat["total_trades"],
        "wins": strat["wins"],
        "losses": strat["losses"],
    }


def calc_signal_ic(history: list) -> dict:
    """
    计算每个信号的IC (信息系数: 信号评分与未来收益的Spearman秩相关)
    history: [{"signal_name": str, "score": float, "future_return": float}, ...]
    返回: {"signal_ic": {"momentum_breakout": 0.12, ...}, "avg_ic": 0.05, "reliable_signals": [...]}
    """
    from collections import defaultdict
    from scipy.stats import spearmanr
    import numpy as np

    signal_scores = defaultdict(list)
    signal_returns = defaultdict(list)

    for item in history:
        name = item.get("signal_name", "unknown")
        score = item.get("score", 50)
        ret = item.get("future_return", 0)
        signal_scores[name].append(score)
        signal_returns[name].append(ret)

    ic_results = {}
    for name in signal_scores:
        scores = signal_scores[name]
        returns = signal_returns[name]
        if len(scores) < 10:
            continue
        try:
            rho, p_value = spearmanr(scores, returns)
            if not np.isnan(rho):
                ic_results[name] = round(rho, 4)
        except Exception:
            continue

    avg_ic = round(sum(ic_results.values()) / max(len(ic_results), 1), 4) if ic_results else 0.0

    # 可靠信号: |IC| > 0.05 且样本量>=20
    reliable = [
        {"signal": name, "ic": ic, "samples": len(signal_scores[name])}
        for name, ic in ic_results.items()
        if abs(ic) > 0.05 and len(signal_scores[name]) >= 20
    ]
    reliable.sort(key=lambda x: abs(x["ic"]), reverse=True)

    return {
        "signal_ic": ic_results,
        "avg_ic": avg_ic,
        "reliable_signals": reliable,
        "total_signals_analyzed": len(ic_results),
    }


def flag_degenerate_strategies() -> list:
    """
    标记近20笔胜率<30%且持续恶化的策略
    返回: [{"strategy": "xxx", "wr_20": 0.25, "trend": "declining", "suggested_action": "disable"}, ...]
    """
    stats = _load_stats()
    degenerate = []

    for strategy, strat in stats["strategies"].items():
        if strat["total_trades"] < 5:
            continue  # 样本太少,不判定

        rolling = strat["rolling_trades"]
        if not rolling:
            continue

        wr_20 = sum(t["is_win"] for t in rolling) / max(len(rolling), 1)

        # 趋势检测
        trend = "stable"
        if len(rolling) >= 8:
            half = len(rolling) // 2
            first_wr = sum(t["is_win"] for t in rolling[:half]) / max(half, 1)
            second_wr = sum(t["is_win"] for t in rolling[half:]) / max(len(rolling) - half, 1)
            if second_wr < first_wr - 0.1:
                trend = "declining"

        if wr_20 < DEGENERATE_WR_THRESHOLD and (trend == "declining" or wr_20 < 0.2):
            degenerate.append({
                "strategy": strategy,
                "wr_20": round(wr_20, 4),
                "trend": trend,
                "total_trades": strat["total_trades"],
                "suggested_action": "disable" if wr_20 < 0.2 else "reduce_weight",
            })

    degenerate.sort(key=lambda x: x["wr_20"])
    if degenerate:
        logger.warning(f"[RollingStats] 退化策略: {[d['strategy'] for d in degenerate]}")

    return degenerate
