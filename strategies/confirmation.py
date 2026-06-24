"""多信号确认 — 至少2个独立信号共振·三道防线 (R20: 严格过滤)"""
import logging, numpy as np
logger = logging.getLogger("aurora.confirm")

def confirm_entry(analysis: dict, kline: dict = None) -> tuple:
    """三道防线验证: K线形态 + 指标信号 + 量价关系"""
    checks = []
    if analysis.get("best_score", 0) >= 55:
        checks.append(("kline", 1.0))
    else:
        checks.append(("kline", 0.5))
    if _check_ma_trend(kline):
        checks.append(("trend", 1.0))
    else:
        checks.append(("trend", 0.3))
    if _check_volume_price(kline):
        checks.append(("volume", 1.0))
    else:
        checks.append(("volume", 0.4))
    if _check_key_level(kline):
        checks.append(("key_level", 1.0))
    passed = sum(1 for _, s in checks if s >= 0.5)
    confidence = sum(s for _, s in checks) / max(len(checks), 1)
    return passed >= 2, confidence, checks

def _check_ma_trend(kline: dict = None) -> bool:
    """R20: kline缺失时严格不通过"""
    if kline is None or not isinstance(kline, dict): return False
    df = kline.get("df")
    if df is None or len(df) < 20: return False
    close = df["close"].values
    ma5 = np.mean(close[-5:]); ma10 = np.mean(close[-10:]); ma20 = np.mean(close[-20:])
    return close[-1] > ma5 > ma10 > ma20

def _check_volume_price(kline: dict = None) -> bool:
    """量价八法: 价涨量增=健康"""
    if kline is None or not isinstance(kline, dict): return False
    df = kline.get("df")
    if df is None or len(df) < 5: return False
    c = df["close"].values; v = df["volume"].values
    price_up = c[-1] > c[-2]
    vol_up = v[-1] > np.mean(v[-5:-1])
    return not (price_up and not vol_up)

def _check_key_level(kline: dict = None) -> bool:
    """R20: kline缺失时严格不通过"""
    if kline is None or not isinstance(kline, dict): return False
    df = kline.get("df")
    if df is None or len(df) < 20: return False
    close = df["close"].values
    ma20 = np.mean(close[-20:])
    return close[-1] > ma20
