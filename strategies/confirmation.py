"""多信号确认 — 至少2个独立信号共振·三道防线 (R20: 严格过滤)
v14.42: 支持按Agent画像差异化 — 短线狙击手放宽均线/量价确认(超短线信号天然不满足波段确认)
"""
import logging, numpy as np
logger = logging.getLogger("aurora.confirm")

# 短线风格确认参数: 首板/涨停/动量突破类信号, 确认防线放宽
_SHORT_STRATEGIES = ("first_board", "naked_pinbar", "naked_engulf", "williams_r", "orb",
                     "momentum_breakout", "sector_rotation", "naked_supply_demand")

def confirm_entry(analysis: dict, kline: dict = None, profile_name: str = None) -> tuple:
    """三道防线验证: K线形态 + 指标信号 + 量价关系
    v14.42: profile_name为短线狙击手时, 放宽MA趋势/量价防线(超短线刚启动的股票均线未理顺)
    """
    checks = []
    is_short = profile_name == "短线狙击手" or (
        profile_name is None and analysis.get("best_strategy", "") in _SHORT_STRATEGIES)
    if analysis.get("best_score", 0) >= 55:
        checks.append(("kline", 1.0))
    else:
        checks.append(("kline", 0.5))
    if _check_ma_trend(kline, relaxed=is_short):
        checks.append(("trend", 1.0))
    elif is_short:
        checks.append(("trend", 0.6))   # 短线: 均线未理顺但方向正确, 半认可
    else:
        checks.append(("trend", 0.3))
    if _check_volume_price(kline, relaxed=is_short):
        checks.append(("volume", 1.0))
    elif is_short:
        checks.append(("volume", 0.6))   # 短线: 缩量涨停/缩量回调也认可
    else:
        checks.append(("volume", 0.4))
    if _check_key_level(kline, relaxed=is_short):
        checks.append(("key_level", 1.0))
    elif is_short:
        checks.append(("key_level", 0.6))
    else:
        checks.append(("key_level", 0.3))
    passed = sum(1 for _, s in checks if s >= 0.5)
    confidence = sum(s for _, s in checks) / max(len(checks), 1)
    return passed >= 2, confidence, checks

def _check_ma_trend(kline: dict = None, relaxed: bool = False) -> bool:
    """R20: kline缺失时严格不通过; relaxed=短线放宽为close>MA20即可"""
    if kline is None or not isinstance(kline, dict): return False
    df = kline.get("df")
    if df is None or len(df) < 20: return False
    close = df["close"].values
    ma5 = np.mean(close[-5:]); ma10 = np.mean(close[-10:]); ma20 = np.mean(close[-20:])
    if relaxed:
        return close[-1] > ma20 and close[-1] > ma5   # 短线: 站上MA20且MA5之上即可
    return close[-1] > ma5 > ma10 > ma20

def _check_volume_price(kline: dict = None, relaxed: bool = False) -> bool:
    """量价八法: 价涨量增=健康; relaxed=短线允许缩量(缩量涨停/缩量回调是强势特征)"""
    if kline is None or not isinstance(kline, dict): return False
    df = kline.get("df")
    if df is None or len(df) < 5: return False
    c = df["close"].values; v = df["volume"].values
    price_up = c[-1] > c[-2]
    vol_up = v[-1] > np.mean(v[-5:-1])
    if relaxed:
        return True   # 短线: 量价防线让位给信号本身(首板/动量已含量能确认)
    return not (price_up and not vol_up)

def _check_key_level(kline: dict = None, relaxed: bool = False) -> bool:
    """R20: kline缺失时严格不通过; relaxed=短线放宽为close>MA10"""
    if kline is None or not isinstance(kline, dict): return False
    df = kline.get("df")
    if df is None or len(df) < 20: return False
    close = df["close"].values
    ma20 = np.mean(close[-20:])
    if relaxed:
        return close[-1] > np.mean(close[-10:])   # 短线: 站上MA10即认可
    return close[-1] > ma20
