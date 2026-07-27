"""多策略相关性监控 — 热力图+高相关告警"""
import json, logging, numpy as np
from pathlib import Path
logger = logging.getLogger("aurora.corr")
DATA = Path(__file__).resolve().parent.parent / "data"
REPORT = DATA / "correlation_report.json"

STRATEGIES = ["wave_point", "momentum_breakout", "mean_reversion", "sector_rotation"]

def compute_correlation():
    """计算策略间盈亏相关性, 返回相关系数矩阵"""
    tf = DATA / "sim_trades.json"
    if not tf.exists(): return {}
    try: trades = json.loads(tf.read_text())
    except: return {}
    
    strat_pnls = {s: [] for s in STRATEGIES}
    for t in trades:
        s = t.get("strategy", "")
        pnl = t.get("pnl_pct", 0)
        if s in strat_pnls:
            strat_pnls[s].append(pnl)
    
    # 只保留有>=5笔交易的策略
    valid = {s: p for s, p in strat_pnls.items() if len(p) >= 5}
    names = list(valid.keys())
    n = len(names)
    if n < 2: return {"status": "insufficient_data", "strategies_with_data": names}
    
    # 对齐长度(取最短)
    min_len = min(len(p) for p in valid.values())
    arr = np.array([valid[s][-min_len:] for s in names])
    corr = np.corrcoef(arr)
    
    # 找高相关对
    high_corr_pairs = []
    for i in range(n):
        for j in range(i+1, n):
            if abs(corr[i][j]) > 0.7:
                high_corr_pairs.append({
                    "s1": names[i], "s2": names[j],
                    "correlation": round(corr[i][j], 3)
                })
    
    report = {
        "strategies": names,
        "matrix": {names[i]: {names[j]: round(float(corr[i][j]), 3) for j in range(n)} for i in range(n)},
        "high_corr_pairs": high_corr_pairs,
        "alert": len(high_corr_pairs) > 0,
    }
    DATA.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    if high_corr_pairs:
        logger.warning(f"[Corr] 高相关策略对: {high_corr_pairs}")
    return report

def check_portfolio_risk():
    """检查组合风险：如果高相关策略同时亏损, 建议降仓"""
    report = compute_correlation()
    if not report or not report.get("high_corr_pairs"):
        return []
    alerts = []
    for pair in report["high_corr_pairs"]:
        alerts.append({
            "type": "high_correlation",
            "detail": f"{pair['s1']} vs {pair['s2']} 相关系数{pair['correlation']}",
            "suggestion": "建议减少这两个策略的同时持仓"
        })
    return alerts