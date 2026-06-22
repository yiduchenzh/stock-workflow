
"""组合VaR — 含相关性矩阵 (Risk Manager审计修复)"""
import numpy as np
import logging
logger = logging.getLogger("aurora.portfolio_var")

def calc_portfolio_var(positions: dict, kline_cache: dict, confidence=0.99) -> dict:
    """组合VaR = sqrt(w' * Cov * w) * z_alpha"""
    if len(positions) < 2: return {"var_pct": 0.03, "method": "single_stock"}
    
    codes = list(positions.keys())
    returns_list = []
    weights = []
    
    for code in codes:
        pos = positions[code]
        weight = pos.get("shares", 0) * pos.get("current_price", pos.get("avg_cost", 0))
        weights.append(weight)
        df = kline_cache.get(code)
        if df is not None and len(df) >= 20:
            r = np.diff(np.log(df["close"].values[-60:]))
            returns_list.append(r[-min(20, len(r)):])
        else:
            returns_list.append(np.zeros(20))
    
    if len(returns_list) < 2:
        return {"var_pct": 0.03, "method": "insufficient_data"}
    
    # 相关性矩阵
    returns_matrix = np.array(returns_list).T
    cov = np.cov(returns_matrix, rowvar=False)
    weights = np.array(weights) / max(sum(weights), 1)
    
    # 组合方差
    port_var = weights @ cov @ weights
    port_vol = np.sqrt(max(port_var, 0))
    
    z = {0.95: 1.645, 0.99: 2.326}.get(confidence, 2.326)
    var_pct = z * port_vol * 100
    
    # 相关性警告
    avg_corr = (np.sum(np.abs(cov)) / (len(cov)**2 - len(cov))) if len(cov) > 1 else 0
    corr_warning = avg_corr > 0.5
    
    return {
        "var_pct": round(var_pct, 2),
        "port_vol_pct": round(port_vol * 100, 2),
        "avg_correlation": round(avg_corr, 2),
        "corr_warning": corr_warning,
        "method": "covariance",
        "advice": "组合高度相关, 分散化不足" if corr_warning else "组合分散化良好",
    }
