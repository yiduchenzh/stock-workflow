# -*- coding: utf-8 -*-
"""合规措辞映射表 v3 — 全策略覆盖"""
from __future__ import annotations
ACTION_MAP = {"buy":"多因子评分偏高","sell":"多因子评分偏低","hold":"持仓评分中性","stop_loss":"触发风控阈值","enter":"条件匹配","exit":"条件失效"}
STRATEGY_MAP = {
    "wave_point":"波段低点反弹形态","mean_reversion":"均值回归形态",
    "momentum_breakout":"动量突破形态","chan_theory":"缠论买卖点形态",
    "chan_buy1":"缠论第一类买点(趋势背驰)","chan_sell1":"缠论第一类卖点(趋势背驰)",
    "chan_buy2":"缠论第二类买点(回抽确认)","chan_sell2":"缠论第二类卖点(反弹不过)",
    "chan_buy3":"缠论第三类买点(中枢上突破)","chan_sell3":"缠论第三类卖点(中枢下跌破)",
    "naked_pinbar":"裸K PinBar(锤头/吊颈)","naked_insidebar":"裸K InsideBar(孕线)",
    "naked_engulf":"裸K Engulfing(吞没)","naked_fakey":"裸K Fakey(假突破反向)",
    "naked_supply_demand":"裸K供需区突破","naked_k":"裸K综合形态",
    "sector_rotation":"板块轮动跟随","test_line":"大下影/大上影线",
    "123_rule":"斯波朗迪123法则","ma_breakout":"均线突破形态","williams_r":"Williams%R超买超卖信号","orb":"开盘区间突破形态","williams_compression":"波动收缩蓄力形态",
    "first_board":"首板突破形态","pullback":"回调支撑形态",
}
INDICATOR_MAP = {"macd":"MACD指标","kdj":"KDJ指标","rsi":"RSI指标","atr":"ATR指标","ma20":"20日均线"}
REGIME_MAP = {"bull_strong":"市场偏积极","bull_weak":"市场偏暖","range":"震荡格局","bear_weak":"偏弱","bear_strong":"弱势"}
FULL_DISCLAIMER = "量化分析仅供参考，不构成投资建议"
def safe_action(a):return ACTION_MAP.get(a.lower(),"变化")
def safe_strategy(s):return STRATEGY_MAP.get(s.lower().replace("strategy_",""),s)
def safe_indicator(i):return INDICATOR_MAP.get(i.lower(),i)
def safe_regime(r):return REGIME_MAP.get(r,"未知")
def signal_strength(s):
    if s>=70:return {"label":"较强","icon":"fire"}
    if s>=50:return {"label":"中等","icon":"chart"}
    if s>=30:return {"label":"温和","icon":"leaf"}
    return {"label":"偏弱","icon":"seedling"}
def random_disclaimer():return "仅演示"
