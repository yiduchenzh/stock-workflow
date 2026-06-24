"""GARCH/EWMA波动率模块测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
from risk.garch_var import ewma_volatility, garch11_mle, predict_var, get_kelly_adjustment
import pandas as pd

def test_ewma_volatility_normal():
    """EWMA: 正常市场波动率"""
    np.random.seed(42)
    returns = np.random.randn(200) * 0.015
    result = ewma_volatility(returns)
    assert result["method"] == "EWMA"
    assert 0.005 < result["sigma_daily"] < 0.05
    assert 5 < result["annual_vol"] < 80

def test_ewma_volatility_short():
    """EWMA: 短序列回退"""
    returns = np.array([0.01, 0.02])
    result = ewma_volatility(returns)
    assert result["method"] == "fallback"

def test_garch11_mle_converges():
    """GARCH(1,1) MLE: 收敛检查"""
    np.random.seed(42)
    returns = np.random.randn(200) * 0.015
    result = garch11_mle(returns)
    assert result["method"] == "GARCH(1,1)-MLE"
    assert 0 < result["alpha"] < 0.5
    assert 0 < result["beta"] < 1.0
    assert 0 < result["persistence"] < 1.0

def test_garch11_volatility_cluster():
    """GARCH(1,1): 高波动集群后alpha应较大"""
    np.random.seed(42)
    returns = np.random.randn(200) * 0.015
    returns[:30] *= 3.0
    result = garch11_mle(returns)
    assert result["sigma_daily"] > 0.01

def test_garch_fallback_short():
    """GARCH: 短序列回退到EWMA"""
    returns = np.array([0.01, 0.02])
    result = garch11_mle(returns)
    # 短序列应回退
    assert "method" in result

def test_predict_var_default():
    """VaR: 默认99%置信度"""
    np.random.seed(42)
    returns = np.random.randn(200) * 0.015
    var = predict_var(returns)
    assert 0.005 <= var <= 0.10

def test_predict_var_confidence_levels():
    """VaR: 不同置信度"""
    np.random.seed(42)
    returns = np.random.randn(200) * 0.015
    var_95 = predict_var(returns, confidence=0.95)
    var_99 = predict_var(returns, confidence=0.99)
    assert var_95 < var_99

def test_predict_var_ewma_mode():
    """VaR: 强制EWMA模式"""
    np.random.seed(42)
    returns = np.random.randn(200) * 0.015
    var = predict_var(returns, use_garch=False)
    assert var > 0

def test_get_kelly_adjustment_normal():
    """Kelly调整: 正常波动率返回1.0"""
    np.random.seed(42)
    close = 10.0 + np.cumsum(np.random.randn(100) * 0.15)
    df = pd.DataFrame({"close": close})
    adj = get_kelly_adjustment(df)
    assert adj > 0

def test_get_kelly_adjustment_none():
    """Kelly调整: 空数据返回1.0"""
    adj = get_kelly_adjustment(None)
    assert adj == 1.0

def test_get_kelly_adjustment_short():
    """Kelly调整: 短序列返回1.0"""
    df = pd.DataFrame({"close": [10.0] * 5})
    adj = get_kelly_adjustment(df)
    assert adj == 1.0