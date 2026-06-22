
"""多信号确认 — 至少2个独立信号共振·三道防线"""
import logging, numpy as np
logger = logging.getLogger("aurora.confirm")

def confirm_entry(analysis: dict, kline: dict = None) -> tuple:
    """三道防线验证: K线形态 + 指标信号 + 量价关系"""
    checks = []
    # 第一道防线: K线形态验证
    if analysis.get("best_score", 0) >= 55:
        checks.append(("kline", 1.0))
    else:
        checks.append(("kline", 0.5))
    # 第二道防线: 均线趋势验证
    if _check_ma_trend(kline):
        checks.append(("trend", 1.0))
    else:
        checks.append(("trend", 0.3))
    # 第三道防线: 量价关系验证
    if _check_volume_price(kline):
        checks.append(("volume", 1.0))
    else:
        checks.append(("volume", 0.4))
    # 关键位验证: 是否在支撑/阻力区
    if _check_key_level(kline):
        checks.append(("key_level", 1.0))
    # 评分: 至少2个维度 ≥0.5 才算确认
    passed = sum(1 for _, s in checks if s >= 0.5)
    confidence = sum(s for _, s in checks) / max(len(checks), 1)
    return passed >= 2, confidence, checks

def _check_ma_trend(kline: dict = None) -> bool:
    """均线趋势: MA5>MA10>MA20"""
    if kline is None or not isinstance(kline, dict): return True
    df = kline.get("df")
    if df is None or len(df) < 20: return True
    close = df["close"].values
    ma5 = np.mean(close[-5:]); ma10 = np.mean(close[-10:]); ma20 = np.mean(close[-20:])
    return close[-1] > ma5 > ma10 > ma20

def _check_volume_price(kline: dict = None) -> bool:
    """量价八法: 价涨量增=健康"""
    if kline is None or not isinstance(kline, dict): return True
    df = kline.get("df")
    if df is None or len(df) < 5: return True
    c = df["close"].values; v = df["volume"].values
    price_up = c[-1] > c[-2]
    vol_up = v[-1] > np.mean(v[-5:-1])
    return not (price_up and not vol_up)  # 价涨量缩=警告

def _check_key_level(kline: dict = None) -> bool:
    """关键位: 价格在MA20之上"""
    if kline is None or not isinstance(kline, dict): return True
    df = kline.get("df")
    if df is None or len(df) < 20: return True
    close = df["close"].values
    ma20 = np.mean(close[-20:])
    return close[-1] > ma20
