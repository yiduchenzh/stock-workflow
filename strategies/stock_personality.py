"""股性画像 — 波动率/振幅/涨停基因/Beta/量能特征"""
import numpy as np
import logging
logger = logging.getLogger("aurora.personality")

def profile_stock(code: str, name: str, kline_df) -> dict:
    """为每只股票建立股性画像"""
    if kline_df is None or len(kline_df) < 60:
        return {"code": code, "name": name, "type": "unknown", "suitable_strategies": []}
    
    close = kline_df["close"].values
    high = kline_df["high"].values
    low = kline_df["low"].values
    vol = kline_df["volume"].values
    
    # 日收益率统计
    returns = np.diff(close) / close[:-1] * 100
    
    # 波动率分类
    daily_vol = np.std(returns)  # 日波动率(%)
    if daily_vol > 3.5: vol_type = "high_vol"      # 高波: 科创板/次新/题材
    elif daily_vol > 2.0: vol_type = "mid_vol"     # 中波: 一般个股
    else: vol_type = "low_vol"                       # 低波: 银行/蓝筹
    
    # 日内振幅
    amplitudes = (high[1:] - low[1:]) / close[:-1] * 100
    avg_amp = np.mean(amplitudes)
    t0_suitable = avg_amp >= 2.5  # 振幅>=2.5%才适合做T
    
    # 涨停基因
    chg = np.diff(close) / close[:-1] * 100
    limit_ups_60d = sum(1 for c in chg[-60:] if c >= 9.5)
    limit_up_gene = "strong" if limit_ups_60d >= 3 else ("normal" if limit_ups_60d >= 1 else "none")
    
    # 量能趋势
    avg_vol_20d = np.mean(vol[-20:]) if len(vol) >= 20 else np.mean(vol)
    avg_vol_60d = np.mean(vol[-60:]) if len(vol) >= 60 else avg_vol_20d
    vol_trend = "increasing" if avg_vol_20d > avg_vol_60d * 1.2 else ("stable" if avg_vol_20d > avg_vol_60d * 0.8 else "decreasing")
    
    # Beta 简化: 与沪深300相关性(用自身波动率代理)
    beta_approx = min(daily_vol / 2.0, 2.5)
    
    # 策略适配
    suitable = []
    if vol_type in ("high_vol", "mid_vol"):
        suitable.extend(["wave_point", "first_board", "naked_k"])
    if limit_up_gene in ("strong", "normal"):
        suitable.append("first_board")
    if vol_type == "low_vol":
        suitable.extend(["ma_breakout", "pullback"])
    if t0_suitable:
        suitable.append("t0_friendly")
    # 去重
    suitable = list(dict.fromkeys(suitable))
    
    return {
        "code": code, "name": name, "type": vol_type,
        "daily_vol": round(daily_vol, 2), "avg_amplitude": round(avg_amp, 2),
        "limit_up_gene": limit_up_gene, "limit_ups_60d": limit_ups_60d,
        "vol_trend": vol_trend, "beta_approx": round(beta_approx, 2),
        "t0_suitable": t0_suitable, "suitable_strategies": suitable,
        "advice": _get_advice(vol_type, limit_up_gene, t0_suitable),
    }

def _get_advice(vol_type, limit_gene, t0_ok):
    tips = []
    if vol_type == "high_vol": tips.append("高波动→适合波动点/裸K战法,止损宜宽(8-10%)")
    elif vol_type == "mid_vol": tips.append("中等波动→适合首板回踩/123法则")
    else: tips.append("低波动→适合均线突破/缠论三买,止损宜紧(3-5%)")
    if limit_gene == "strong": tips.append("涨停基因强→优先首板起爆战法")
    if t0_ok: tips.append("振幅适合做T→可启用日内T+0")
    else: tips.append("振幅太小→T+0收益覆盖不了费用,不建议做T")
    return " | ".join(tips)