
"""GARCH(1,1)波动率预测 + 动态VaR — Tsay 第3版"""
import numpy as np
import logging
logger = logging.getLogger("aurora.garch")

def fit_garch_11(returns, max_iter=100):
    """拟合GARCH(1,1): sigma2_t = omega + alpha*eps2_{t-1} + beta*sigma2_{t-1}"""
    if len(returns) < 60: return {"omega": 0.0001, "alpha": 0.10, "beta": 0.85, "converged": False}
    r = np.array(returns)
    # 简单最小二乘近似
    omega = np.var(r) * 0.01
    alpha = 0.10
    beta = max(0.80, 1.0 - alpha - 0.01)
    for _ in range(max_iter):
        sigma2 = np.zeros(len(r))
        sigma2[0] = np.var(r)
        for t in range(1, len(r)):
            sigma2[t] = omega + alpha * r[t-1]**2 + beta * sigma2[t-1]
        omega_new = np.mean(r**2) * (1 - alpha - beta)
        alpha_new = np.corrcoef(r[1:]**2, r[:-1]**2)[0,1] * 0.1 if len(r) > 1 else 0.1
        beta_new = 1.0 - alpha_new - omega_new / max(np.mean(r**2), 0.0001)
        alpha_new = max(0.01, min(0.30, alpha_new))
        beta_new = max(0.60, min(0.98, beta_new))
        omega_new = max(0.00001, np.var(r) * (1 - alpha_new - beta_new))
        if abs(alpha - alpha_new) < 0.001 and abs(beta - beta_new) < 0.001:
            break
        omega, alpha, beta = omega_new, alpha_new, beta_new
    converged = alpha + beta < 1.0
    return {"omega": round(omega, 6), "alpha": round(alpha, 4), "beta": round(beta, 4),
            "persistence": round(alpha + beta, 4), "converged": converged,
            "annual_vol": round(np.sqrt(omega / (1 - alpha - beta) * 252) * 100, 2) if converged else 0}

def predict_var_garch(returns, confidence=0.99, horizon=1):
    """GARCH-VaR: VaR_t = z_alpha * sigma_{t+1}"""
    result = fit_garch_11(returns)
    if not result["converged"]: return 0.03
    r = np.array(returns)
    sigma2_last = result["omega"] / (1 - result["alpha"] - result["beta"]) if result["persistence"] < 1 else np.var(r)
    sigma_next = np.sqrt(sigma2_last)
    z_scores = {0.95: 1.645, 0.99: 2.326, 0.999: 3.090}
    z = z_scores.get(confidence, 2.326)
    var = z * sigma_next * np.sqrt(horizon)
    return round(min(max(var, 0.005), 0.15), 4)

def get_garch_kelly_adjustment(kline_df):
    """GARCH波动率→Kelly仓位调整系数"""
    if kline_df is None or len(kline_df) < 30: return 1.0
    close = kline_df["close"].values
    returns = np.diff(np.log(close))
    result = fit_garch_11(returns)
    if not result["converged"]: return 1.0
    # 波动率越低→仓位越大, 波动率越高→仓位越小
    daily_vol = np.sqrt(result["omega"] / (1 - result["alpha"] - result["beta"]))
    if daily_vol < 0.01: return 1.3     # 极低波动: 加仓
    elif daily_vol < 0.02: return 1.0    # 正常
    elif daily_vol < 0.03: return 0.7    # 高波动: 减仓
    else: return 0.4                      # 极高波动: 大减仓
