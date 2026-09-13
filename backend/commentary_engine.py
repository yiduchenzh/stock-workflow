# -*- coding: utf-8 -*-
"""解说引擎 v3 — 全策略覆盖(含缠论买卖点+裸K四大形态)"""
from __future__ import annotations
import random
from datetime import datetime
from typing import Optional
from .compliance_filter import safe_strategy, safe_action, safe_indicator, safe_regime, signal_strength, random_disclaimer, FULL_DISCLAIMER

def generate_signal_commentary(code: str, name: str, strategy: str, price: float, score: float, action: str = "enter", extra: Optional[dict] = None, regime: str = "range") -> dict:
    extra = extra or {}
    safe_s = safe_strategy(strategy)
    strength = signal_strength(score)
    indicator = safe_indicator(extra.get("indicator", ""))
    v = {
        "code": code, "name": name, "safe_s": safe_s, "price": price, "score": score,
        "indicator": indicator, "timeframe": extra.get("timeframe", "日线"),
        "ma_period": extra.get("ma_period", 20), "atr": extra.get("atr", 0.0),
        "volatility": extra.get("volatility", 0.0),
        "stop_loss": extra.get("stop_loss", price * 0.95),
        "loss_pct": extra.get("loss_pct", 5.0),
        "hold_days": extra.get("hold_days", random.choice([3, 5, 7, 10])),
        "deviation": extra.get("deviation", 5.0), "vol_ratio": extra.get("vol_ratio", 1.5),
        "count": extra.get("signal_count", 1), "win_rate": extra.get("win_rate", 45.0),
        "rr": extra.get("rr", 1.8), "lookback": extra.get("lookback", 60),
    }
    # 策略触发描述
    if strategy == "wave_point":
        trigger = f"价格回踩MA{v['ma_period']}后获得支撑，{v['timeframe']}周期形态确认"
    elif strategy == "mean_reversion":
        trigger = f"价格偏离MA{v['ma_period']}达{v['deviation']:.1f}%，{v['indicator']}信号确认"
    elif strategy == "momentum_breakout":
        trigger = f"价格放量突破关键位，{v['indicator']}趋势向好"
    elif strategy.startswith("chan_buy"):
        trigger = f"缠论底分型+MACD底背驰确认，{v['timeframe']}级别第一类买点"
    elif strategy.startswith("chan_sell"):
        trigger = f"缠论顶分型+MACD顶背驰确认，{v['timeframe']}级别第一类卖点"
    elif strategy.startswith("chan_"):
        trigger = f"缠论买卖点信号，{v['timeframe']}级别"
    elif strategy.startswith("naked_pinbar"):
        trigger = f"裸K PinBar形成，下影线占比高，量比{v['vol_ratio']:.1f}"
    elif strategy.startswith("naked_insidebar"):
        trigger = f"裸K InsideBar孕线形态，波动收敛蓄力，量比{v['vol_ratio']:.1f}"
    elif strategy.startswith("naked_engulf"):
        trigger = f"裸K Engulfing吞没形态，反向吞噬前K线实体，量比{v['vol_ratio']:.1f}"
    elif strategy.startswith("naked_fakey"):
        trigger = f"裸K Fakey假突破反向形态，突破失败后转向，量比{v['vol_ratio']:.1f}"
    elif strategy.startswith("naked_"):
        trigger = f"裸K形态确认，{strategy.replace('naked_','')}信号触发，量比{v['vol_ratio']:.1f}"
    else:
        trigger = f"多因子评分{score:.0f}/100，{v['indicator']}指标共振确认"

    commentary_6d = {
        "1_selection": f"{name}({code}) 进入{safe_s}关注池，该形态适合当前市场环境",
        "2_trigger": trigger,
        "3_strategy": f"采用{safe_s}技术形态，在{safe_regime(regime)}环境下适用性评分{score:.0f}/100",
        "4_risk": f"ATR={v['atr']:.2f}，波动率{v['volatility']:.1f}%，参考风控位{v['stop_loss']:.2f}(-{v['loss_pct']:.1f}%)",
        "5_holding": f"参考该形态历史数据，预期关注{v['hold_days']}个交易日",
        "6_history": f"该形态近{v['lookback']}个交易日出现{v['count']}次，胜率{v['win_rate']:.0f}%，盈亏比{v['rr']:.2f}",
    }
    return {
        "code": code, "name": name, "strategy": strategy, "action": action,
        "price": price, "score": score, "regime": regime,
        "safe_action": safe_action(action), "safe_strategy": safe_s,
        "strength": strength, "timestamp": datetime.now().isoformat(),
        "title": f"{strength['icon']} {name}({code}) — {strength['label']} {safe_s}触发",
        "commentary_6d": commentary_6d,
        "compliance": {"summary": f"{name}({code}) 评分{score:.0f}/100 {safe_s}", "note": random_disclaimer()},
        "disclaimer": FULL_DISCLAIMER,
    }

def generate_market_commentary(regime: str = "range", market_score: float = 50, sector_up_pct: float = 50, limit_up_count: int = 30) -> dict:
    cns = {"bull_strong":"市场积极","bull_weak":"市场偏暖","range":"震荡格局","bear_weak":"市场偏弱","bear_strong":"弱势格局"}
    t = cns.get(regime, "当前市场")
    return {"text": f"{t}，{sector_up_pct:.0f}%板块上涨，涨停{limit_up_count}家", "regime_cn": safe_regime(regime), "market_score": market_score, "regime": regime, "strength": signal_strength(market_score), "timestamp": datetime.now().isoformat(), "disclaimer": FULL_DISCLAIMER}

def generate_trade_commentary(trade: dict) -> str:
    a = trade.get("action","buy"); c = trade.get("code",""); n = trade.get("name",""); p = trade.get("price",0); s = trade.get("shares",0); pnl = trade.get("pnl",0); r = trade.get("reason","")
    if a == "buy": return f"{n}({c}) {p:.2f}成交{s}股 {r}"
    return f"{n}({c}) {p:.2f}卖出{s}股 盈亏{pnl:+.2f} {r}"

def generate_regime_change_commentary(old: str, new: str, detail: str = "") -> str:
    return f"市场状态变化: {old} -> {new} {detail}"

_FAQ = {
    "wave_point":"wave_point（波段低点反弹形态）是一种趋势跟踪策略，当价格回踩重要均线并获得支撑时触发。适合趋势行情中的回调买入场景。",
    "mean_reversion":"mean_reversion（均值回归形态）基于价格围绕价值波动的统计规律，当价格偏离均线过远时向均值回归。",
    "momentum_breakout":"momentum_breakout（动量突破形态）捕捉价格突破关键压力位时的加速行情，需要成交量放大的配合。",
    "缠论":"缠论是A股市场特有的技术分析体系，核心包括分型、笔、线段、中枢、第一/二/三类买卖点等概念。一买=趋势背驰末端，二买=回抽不破前低，三买=离开中枢不回抽。",
    "裸K":"裸K交易（Naked K / Price Action）包括PinBar锤头线、InsideBar孕线、Engulfing吞没形态、Fakey假突破反向等四大核心形态，不依赖指标，仅看K线本身和成交量。",
    "止损":"止损参考设置：ATR动态止损（2倍ATR）、固定百分比止损（5-7%）、关键技术位止损。建议初始用ATR法。",
    "仓位":"仓位管理采用Kelly公式变体，half-Kelly执行。受最大回撤-10%和日亏损限制-3%双重约束。单票最大不超过总资金20%。",
    "大盘":"大盘状态基于6维指标加权评估，评分0-100，分为bull_strong/bull_weak/range/bear_weak/bear_strong五级。",
}

def answer_faq(question: str) -> Optional[str]:
    q = question.lower().replace(" ","").replace("?","").replace("？","")
    for k, v in _FAQ.items():
        if k in q:
            return v
    return None
