"""
波动率预测 — EWMA + GARCH(1,1) 双模式

EWMA (RiskMetrics标准): lambda=0.94(日频) — 用于日常估计
GARCH(1,1) MLE: 纯numpy实现 — 用于精准VaR和波动率预测

参考: Tsay《金融时间序列分析》第3版 第3章
      RiskMetrics技术文档 (JPMorgan 1996)
"""
import numpy as np
import logging
logger = logging.getLogger("aurora.volatility")


def ewma_volatility(returns, lambda_=0.94):
    """EWMA波动率估计 (RiskMetrics标准)

    sigma2_t = lambda * sigma2_{t-1} + (1-lambda) * r_{t-1}^2
    """
    if len(returns) < 20:
        return {"sigma_daily": 0.02, "annual_vol": 31.7, "method": "fallback"}
    r = np.array(returns, dtype=np.float64)
    sigma2 = float(np.var(r))
    for t in range(1, min(len(r), 60)):
        sigma2 = lambda_ * sigma2 + (1 - lambda_) * float(r[t-1]**2)
    daily_vol = np.sqrt(max(sigma2, 1e-10))
    annual_vol = daily_vol * np.sqrt(252) * 100
    return {"sigma_daily": round(daily_vol, 6), "annual_vol": round(annual_vol, 2), "method": "EWMA"}


def garch11_mle(returns, max_iter=500):
    """GARCH(1,1) MLE估计 (纯numpy, 无外部依赖)

    sigma2_t = omega + alpha * r_{t-1}^2 + beta * sigma2_{t-1}
    约束: omega>0, alpha>=0, beta>=0, alpha+beta<1
    """
    r = np.array(returns, dtype=np.float64)
    n = len(r)
    if n < 30:
        result = ewma_volatility(returns)
        result.update({"omega": 0, "alpha": 0, "beta": 0, "persistence": 0})
        return result

    var_est = float(np.var(r))
    omega, alpha, beta = var_est * 0.05, 0.08, 0.88
    eps = 1e-8

    for _ in range(max_iter):
        sigma2 = np.full(n, var_est, dtype=np.float64)
        for t in range(1, n):
            s = omega + alpha * float(r[t-1]**2) + beta * float(sigma2[t-1])
            sigma2[t] = max(s, eps)

        nll = 0.5 * float(np.sum(np.log(sigma2) + r.astype(np.float64)**2 / sigma2))

        # 数值梯度 (有限差分)
        delta = 1e-6
        best_nll = nll
        best_params = (omega, alpha, beta)
        for da in (-delta, delta):
            for db in (-delta, delta):
                for do in (-delta, delta):
                    o2 = max(eps, omega + do)
                    a2 = max(0, min(0.5, alpha + da))
                    b2 = max(0, min(0.99, beta + db))
                    if a2 + b2 >= 1:
                        continue
                    s2 = np.full(n, var_est, dtype=np.float64)
                    for t in range(1, n):
                        s = o2 + a2 * float(r[t-1]**2) + b2 * float(s2[t-1])
                        s2[t] = max(s, eps)
                    nll2 = 0.5 * float(np.sum(np.log(s2) + r.astype(np.float64)**2 / s2))
                    if nll2 < best_nll:
                        best_nll = nll2
                        best_params = (o2, a2, b2)

        o_new, a_new, b_new = best_params
        change = abs(o_new - omega) + abs(a_new - alpha) + abs(b_new - beta)
        omega, alpha, beta = o_new, a_new, b_new
        if change < 1e-8:
            break

    sigma2_last = var_est
    for t in range(1, min(n, 252)):
        sigma2_last = omega + alpha * float(r[t-1]**2) + beta * sigma2_last
    daily_vol = np.sqrt(max(sigma2_last, eps))
    annual_vol = daily_vol * np.sqrt(252) * 100
    persistence = min(alpha + beta, 0.9999)

    return {"omega": round(omega, 8), "alpha": round(alpha, 6), "beta": round(beta, 6),
            "sigma_daily": round(daily_vol, 6), "annual_vol": round(annual_vol, 2),
            "persistence": round(persistence, 4), "method": "GARCH(1,1)-MLE"}


def predict_var(returns, confidence=0.99, use_garch=True):
    """VaR预测 — 支持EWMA和GARCH两种模式"""
    if use_garch and len(returns) >= 60:
        vol_result = garch11_mle(returns)
    else:
        vol_result = ewma_volatility(returns)
    z = {0.95: 1.645, 0.99: 2.326, 0.999: 3.090}.get(confidence, 2.326)
    var = z * vol_result["sigma_daily"]
    return round(max(var, 0.005), 4)


def get_kelly_adjustment(kline_df):
    """波动率→Kelly调整: GARCH(1,1)估计"""
    if kline_df is None or len(kline_df) < 20:
        return 1.0
    close = kline_df["close"].values
    returns = np.diff(np.log(close.astype(np.float64)))
    result = garch11_mle(returns) if len(returns) >= 60 else ewma_volatility(returns)
    daily = result["sigma_daily"]
    if daily < 0.008:
        return 1.25
    elif daily < 0.015:
        return 1.0
    elif daily < 0.025:
        return 0.7
    else:
        return 0.4


def get_market_volatility_score():
    """市场波动率评分: 0-100, 基于代表性股票波动率"""
    try:
        from data.sources import get_kline
        # 用上证50ETF(510050)或沪深300(510300)估计市场波动
        etf_codes = ["510050", "510300"]
        for code in etf_codes:
            df = get_kline(code, 60)
            if df is not None and len(df) >= 30:
                close = df["close"].values
                returns = np.diff(np.log(close.astype(np.float64)))
                result = garch11_mle(returns)
                annual_vol = result["annual_vol"]
                # 年化15-25%=正常(50分), <15%=低波(高分), >35%=高波(低分)
                if annual_vol < 15:
                    return 80
                elif annual_vol < 20:
                    return 65
                elif annual_vol < 30:
                    return 50
                elif annual_vol < 40:
                    return 30
                else:
                    return 15
    except Exception:
        pass
    return 50
