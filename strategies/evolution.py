"""策略自进化 v2.0 — IC跟踪 + regime子胜率 + 盈利半衰期 + 多维评分 · R24升级
在原有WR淘汰基础上增加3个新维度:
  1. IC(信息系数) — 策略评分与未来收益的相关性
  2. Regime子胜率 — 不同市场状态下的独立统计
  3. 盈利半衰期 — 策略盈利的持续性/集中度"""
import json, logging, numpy as np
from pathlib import Path
from datetime import datetime, timedelta
logger = logging.getLogger("aurora.evolve")
DATA = Path(__file__).resolve().parent.parent / "data" / "strategy_evolution.json"

def _load():
    try: return json.loads(DATA.read_text()) if DATA.exists() else {}
    except Exception: return {}

def _save(d):
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(d, indent=2, ensure_ascii=False))


# ── 基础记录 (与v1.0兼容) ──

def record_signal(strategy_name: str, score: float):
    """记录每次信号"""
    d = _load()
    entry = d.get(strategy_name, {"signals": [], "ic_records": [], "regime": {}, "last_updated": ""})
    entry.setdefault("signals", [])
    entry["signals"].append({"score": score, "time": datetime.now().isoformat()})
    entry["signals"] = entry["signals"][-100:]
    entry["last_updated"] = datetime.now().isoformat()
    d[strategy_name] = entry
    _save(d)

def record_trade_result(strategy_name: str, pnl_pct: float, is_win: bool):
    """记录交易结果 (兼容v1.0调用)"""
    d = _load()
    entry = d.get(strategy_name, {"trades": [], "last_updated": ""})
    entry.setdefault("trades", [])
    entry["trades"].append({"pnl": pnl_pct, "win": is_win, "time": datetime.now().isoformat()})
    entry["trades"] = entry["trades"][-200:]
    entry["last_updated"] = datetime.now().isoformat()
    d[strategy_name] = entry
    _save(d)


# ── R24 新维度记录 ──

def record_regime(strategy_name: str, regime: str):
    """记录策略所处的市场状态"""
    d = _load()
    entry = d.get(strategy_name, {"regime": {}, "last_updated": ""})
    entry.setdefault("regime", {})
    r = entry["regime"].setdefault(regime, {"signals": 0, "wins": 0, "trades": 0})
    r["signals"] = r.get("signals", 0) + 1
    entry["last_updated"] = datetime.now().isoformat()
    d[strategy_name] = entry
    _save(d)

def record_regime_trade(strategy_name: str, regime: str, is_win: bool):
    """记录某regime下的交易结果"""
    d = _load()
    entry = d.get(strategy_name, {"regime": {}, "last_updated": ""})
    entry.setdefault("regime", {})
    r = entry["regime"].setdefault(regime, {"signals": 0, "wins": 0, "trades": 0})
    r["trades"] = r.get("trades", 0) + 1
    if is_win:
        r["wins"] = r.get("wins", 0) + 1
    entry["last_updated"] = datetime.now().isoformat()
    d[strategy_name] = entry
    _save(d)

def record_ic(strategy_name: str, score: float, future_return_pct: float):
    """记录IC数据 — 策略评分与未来收益的对应关系"""
    d = _load()
    entry = d.get(strategy_name, {"ic_records": [], "last_updated": ""})
    entry.setdefault("ic_records", [])
    entry["ic_records"].append({
        "score": score,
        "future_return": future_return_pct,
        "time": datetime.now().isoformat(),
    })
    entry["ic_records"] = entry["ic_records"][-200:]
    entry["last_updated"] = datetime.now().isoformat()
    d[strategy_name] = entry
    _save(d)


# ── 分析函数 ──

def compute_ic(strategy_name: str) -> dict:
    """计算信息系数: corr(score, future_return)
    IC > 0.05 = 有预测能力
    IC < 0    = 反向指标"""
    d = _load().get(strategy_name, {})
    records = d.get("ic_records", [])
    if len(records) < 10:
        return {"ic": None, "ic_ir": None, "n": len(records), "reliable": False}

    scores = np.array([r["score"] for r in records])
    returns = np.array([r["future_return"] for r in records])
    if np.std(scores) == 0 or np.std(returns) == 0:
        return {"ic": 0, "ic_ir": 0, "n": len(records), "reliable": False}

    ic = np.corrcoef(scores, returns)[0, 1]
    # IC_IR = mean(IC) / std(IC) — 用rolling近似
    # 简单版本: IC / sqrt(1/N)
    ic_ir = ic * np.sqrt(len(records)) if not np.isnan(ic) else 0
    if np.isnan(ic):
        ic = 0; ic_ir = 0

    return {
        "ic": float(round(ic, 4)),
        "ic_ir": float(round(ic_ir, 2)),
        "n": len(records),
        "reliable": len(records) >= 20,
    }

def compute_regime_health(strategy_name: str) -> dict:
    """计算各regime下的胜负统计"""
    d = _load().get(strategy_name, {})
    regime_data = d.get("regime", {})
    result = {}
    for regime, r in regime_data.items():
        trades = r.get("trades", 0)
        wins = r.get("wins", 0)
        wr = wins / trades * 100 if trades > 0 else 0
        signals = r.get("signals", 0)
        result[regime] = {
            "wr": round(wr, 1),
            "trades": trades,
            "signals": signals,
        }
    return result

def compute_half_life(strategy_name: str) -> dict:
    """计算盈利半衰期 — 盈利的持续性度量
    方法: 按时间排序交易, 统计盈利是否集中在少数几笔中
    Gini系数: 0=完全均匀, 1=完全集中在一笔
    半衰期: 累计50%盈利所需的交易笔数占比"""
    d = _load().get(strategy_name, {})
    trades = d.get("trades", [])
    if len(trades) < 6:
        return {"gini": None, "half_life": None, "n": len(trades)}

    # 按时间排序
    sorted_trades = sorted(trades, key=lambda t: t.get("time", ""))
    pnls = [t.get("pnl", 0) for t in sorted_trades]
    total_pnl = sum(pnls)
    if total_pnl <= 0:
        return {"gini": 1.0, "half_life": 1.0, "n": len(trades), "note": "总体亏损"}

    # Gini系数: 按PnL排序后的集中度
    pos_pnls = sorted([p for p in pnls if p > 0], reverse=True)
    if not pos_pnls:
        return {"gini": 0, "half_life": 0, "n": len(trades), "note": "无盈利交易"}

    # 半衰期: 多少笔交易贡献了50%的盈利
    half_target = total_pnl * 0.5
    cumulative = 0
    half_count = 0
    for p in pos_pnls:
        cumulative += p
        half_count += 1
        if cumulative >= half_target:
            break

    half_life = half_count / max(len(trades), 1)

    # 简化Gini: 前20%交易贡献了多少盈利
    top_pct = len(pos_pnls) // 5 if len(pos_pnls) >= 5 else 1
    top_contribution = sum(pos_pnls[:top_pct]) / max(total_pnl, 1) * 100

    return {
        "gini": round(top_contribution / 100, 2),  # 近似值
        "half_life": round(half_life, 3),
        "half_count": half_count,
        "total_trades": len(trades),
        "top20_contribution_pct": round(top_contribution, 1),
        "note": "健康" if half_life < 0.3 else ("集中" if half_life < 0.5 else "过度集中"),
    }


# ── 多维健康评分 ──

def get_strategy_health(strategy_name: str) -> dict:
    """v2.0 多维健康评分 — 兼容v1.0返回结构"""
    d = _load().get(strategy_name, {})
    trades = d.get("trades", [])
    n = len(trades)

    if n < 6:
        return {
            "status": "new",
            "trades": n,
            "win_rate": None,
            "recommendation": "积累数据中(>=6笔)",
        }

    wins = sum(1 for t in trades if t.get("win"))
    wr = wins / n
    avg_pnl = sum(t.get("pnl", 0) for t in trades) / n if n > 0 else 0
    total_pnl = sum(t.get("pnl", 0) for t in trades)

    # IC
    ic_info = compute_ic(strategy_name)
    ic = ic_info.get("ic", 0) or 0

    # Regime
    regime = compute_regime_health(strategy_name)

    # 半衰期
    hl = compute_half_life(strategy_name)
    gini = hl.get("gini", 1) or 1

    # ── 综合评分 (0-100) ──
    # WR得分 (0-40)
    wr_score = min(40, max(0, (wr - 0.20) / 0.40 * 40))

    # IC得分 (0-25)
    ic_score = min(25, max(0, ic * 100 * 2))

    # 半衰期得分 (0-20) — Gini越低越好(盈利均匀)
    gini_score = max(0, 20 - gini * 20)

    # 交易量得分 (0-15) — 样本量越大越可靠
    volume_score = min(15, n / 2)

    composite = min(100, max(0, int(wr_score + ic_score + gini_score + volume_score)))

    # ── 状态判定 ──
    if composite >= 70 and wr >= 0.40 and total_pnl > 0:
        status = "healthy"
        rec = f"综合评分{composite}/100 — 维持权重"
    elif composite >= 50 or (wr >= 0.40 and total_pnl > 0):
        status = "warning"
        rec = f"综合评分{composite}/100 — 降低权重至50%"
    elif composite >= 35 or (wr >= 0.30 and total_pnl > 0):
        status = "critical"
        rec = f"综合评分{composite}/100 — 降低权重至20%"
    else:
        status = "dead"
        rec = f"综合评分{composite}/100 — 建议停用"

    return {
        "status": status,
        "trades": n,
        "win_rate": round(wr, 3),
        "avg_pnl": round(avg_pnl, 3),
        "total_pnl": round(total_pnl, 2),
        "composite": composite,
        "ic": ic_info,
        "regime": regime,
        "half_life": hl,
        "recommendation": rec,
    }


def get_all_health() -> dict:
    """获取所有策略的健康状态"""
    result = {}
    for name in _load():
        result[name] = get_strategy_health(name)
    return result


def recommend_weights() -> dict:
    """基于多维健康评分输出建议权重"""
    health = get_all_health()
    weights = {}
    for name, h in health.items():
        if h["status"] == "healthy":
            weights[name] = 1.0
        elif h["status"] == "warning":
            weights[name] = 0.5
        elif h["status"] == "critical":
            weights[name] = 0.2
        else:
            weights[name] = 0.0
    return weights

def mark_strategy_inactive(strategy_name: str, reason: str = "auto"):
    """Mark strategy as inactive (disabled)"""
    d = _load()
    entry = d.get(strategy_name, {})
    entry["active"] = False
    entry["inactive_reason"] = reason
    entry["inactive_time"] = datetime.now().isoformat()
    d[strategy_name] = entry
    _save(d)
    logger.info("[Evolve] {} marked inactive: {}".format(strategy_name, reason))
