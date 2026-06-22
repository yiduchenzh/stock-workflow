
"""波动率预测 + VaR — EWMA方法 (RiskMetrics/Tsay)"""
import numpy as np
import logging
logger = logging.getLogger("aurora.garch")

def ewma_volatility(returns, lambda_=0.94):
    """EWMA波动率: sigma2_t = lambda*sigma2_{t-1} + (1-lambda)*r2_{t-1}
    
    RiskMetrics标准: lambda=0.94(日频), 0.97(月频)
    比之前的手动GARCH迭代更可靠、更标准
    """
    if len(returns) < 20: return {"sigma_daily": 0.02, "annual_vol": 31.7}
    r = np.array(returns)
    sigma2 = np.var(r)  # 初始值
    for t in range(1, min(len(r), 60)):
        sigma2 = lambda_ * sigma2 + (1 - lambda_) * r[t-1]**2
    daily_vol = np.sqrt(max(sigma2, 0.000001))
    annual_vol = daily_vol * np.sqrt(252) * 100
    return {
        "sigma_daily": round(daily_vol, 6),
        "annual_vol": round(annual_vol, 2),
        "method": "EWMA",
    }

def predict_var(returns, confidence=0.99):
    """EWMA-VaR: VaR = z_alpha * sigma_t"""
    result = ewma_volatility(returns)
    z = {0.95: 1.645, 0.99: 2.326, 0.999: 3.090}.get(confidence, 2.326)
    var = z * result["sigma_daily"]
    return round(max(var, 0.005), 4)

def get_kelly_adjustment(kline_df):
    """波动率→Kelly调整: 低波加仓, 高波减仓"""
    if kline_df is None or len(kline_df) < 20: return 1.0
    close = kline_df["close"].values
    returns = np.diff(np.log(close))
    result = ewma_volatility(returns)
    daily = result["sigma_daily"]
    if daily < 0.008: return 1.25      # 极低波(<20%年化)
    elif daily < 0.015: return 1.0     # 正常(20-38%年化)
    elif daily < 0.025: return 0.7     # 偏高(38-63%)
    else: return 0.4                    # 极高波(>63%)
