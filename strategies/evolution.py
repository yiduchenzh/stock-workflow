
"""策略自进化 — IC跟踪 + 半衰期 + 自动淘汰 · 文艺复兴"""
import json, logging
from pathlib import Path
from datetime import datetime, timedelta
logger = logging.getLogger("aurora.evolve")
DATA = Path(__file__).resolve().parent.parent / "data" / "strategy_evolution.json"

def _load():
    try: return json.loads(DATA.read_text()) if DATA.exists() else {}
    except Exception: return {}

def _save(d):
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(d, indent=2))

def record_signal(strategy_name: str, score: float):
    """记录每次信号"""
    d = _load()
    entry = d.get(strategy_name, {"signals": [], "last_updated": ""})
    entry["signals"].append({"score": score, "time": datetime.now().isoformat()})
    # 保留最近100条
    entry["signals"] = entry["signals"][-100:]
    entry["last_updated"] = datetime.now().isoformat()
    d[strategy_name] = entry
    _save(d)

def record_trade_result(strategy_name: str, pnl_pct: float, is_win: bool):
    """记录交易结果"""
    d = _load()
    entry = d.get(strategy_name, {"trades": [], "last_updated": ""})
    entry["trades"].append({"pnl": pnl_pct, "win": is_win, "time": datetime.now().isoformat()})
    entry["trades"] = entry["trades"][-200:]
    entry["last_updated"] = datetime.now().isoformat()
    d[strategy_name] = entry
    _save(d)

def get_strategy_health(strategy_name: str) -> dict:
    """获取策略健康度"""
    d = _load().get(strategy_name, {})
    trades = d.get("trades", [])
    if len(trades) < 10:
        return {"status": "new", "trades": len(trades), "win_rate": None, "recommendation": "积累数据中"}
    wins = sum(1 for t in trades if t.get("win"))
    wr = wins / len(trades)
    avg_pnl = sum(t.get("pnl", 0) for t in trades) / len(trades)
    if wr >= 0.50 and avg_pnl > 0:
        status = "healthy"
        rec = "维持权重"
    elif wr >= 0.40:
        status = "warning"
        rec = "降低权重至50%"
    elif wr >= 0.30:
        status = "critical"
        rec = f"降低权重至20% (胜率{wr:.0%})"
    else:
        status = "dead"
        rec = f"建议停用 (胜率{wr:.0%}<30%且交易{len(trades)}笔)"
    return {"status": status, "trades": len(trades), "win_rate": round(wr, 3), "avg_pnl": round(avg_pnl, 3), "recommendation": rec}

def get_all_health() -> dict:
    result = {}
    for name in _load():
        result[name] = get_strategy_health(name)
    return result
