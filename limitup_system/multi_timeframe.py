# -*- coding: utf-8 -*-
"""
multi_timeframe.py — 多周期战法融合（四级金字塔）

  日线(240)  定方向：四态(强势/弱势/震荡) + 打板形态评分（选什么）
     ↓
  60分       定强弱：K线相对昨收 + MA20 位置（趋势是否延续）
     ↓
  15分       找买点：回踩不破昨收/缩量企稳（何时进）
     ↓
  5分/分时   执行：开盘3分钟定强弱 + 弱转强/强延续买点 + 破位离场（怎么执行）

核心原则（多周期共振才动手）：
  - 日线强势 + 60分站稳 + 15分回踩不破 → 高优先级买点
  - 日线弱势 → 任何周期都不动手（文字②：弱势形态0仓）
  - 日线震荡 → 只做 60/15 分共振的突破/回踩，仓位1-2成
"""
from __future__ import annotations

from statistics import mean
from typing import Any, Dict, List, Optional

import datafeed
import screener
import strategy
from datafeed import attach_prev_close, fetch_daily_kline, fetch_minute_kline


def _ma_last(rows: List[Dict[str, Any]], n: int) -> Optional[float]:
    if len(rows) < n:
        return None
    return mean(r["close"] for r in rows[-n:])


def daily_direction(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """日线层：四态 + 均线结构 + 打板形态。"""
    rows = attach_prev_close(rows)
    last = rows[-1]
    state = strategy.classify_daily_state(last)
    ma5 = _ma_last(rows, 5)
    ma10 = _ma_last(rows, 10)
    ma20 = _ma_last(rows, 20)
    bull = ma5 and ma10 and ma20 and ma5 > ma10 > ma20
    sig = screener.score_signal(rows, len(rows) - 1)
    return {
        "state": state,
        "ma5": round(ma5, 2) if ma5 else None,
        "ma10": round(ma10, 2) if ma10 else None,
        "ma20": round(ma20, 2) if ma20 else None,
        "bull_align": bool(bull),
        "limitup_signal": sig,
    }


def hour_60_strength(minute60: List[Dict[str, Any]], prev_close: float) -> Dict[str, Any]:
    """60分层：相对昨收 + MA20 位置。"""
    if not minute60 or prev_close <= 0:
        return {"level": "未知", "detail": "数据不足"}
    last = minute60[-1]
    above_prev = last["close"] >= prev_close
    ma20 = _ma_last(minute60, 20)
    above_ma = ma20 is not None and last["close"] >= ma20
    if above_prev and above_ma:
        return {"level": "强", "detail": f"60分K站上昨收({prev_close})且站上MA20({ma20:.2f}) → 趋势延续"}
    if above_prev:
        return {"level": "中", "detail": f"60分K站上昨收但低于MA20({ma20:.2f}) → 弱反弹"}
    return {"level": "弱", "detail": f"60分K压制昨收下方 → 与日线强势冲突，谨慎/回避"}


def minute_15_setup(minute15: List[Dict[str, Any]], prev_close: float) -> Dict[str, Any]:
    """15分层：回踩不破昨收 = 买点准备区。"""
    if not minute15 or prev_close <= 0:
        return {"setup": "无", "detail": "数据不足"}
    lows = [r["low"] for r in minute15[-6:]]   # 最近90分钟
    if min(lows) >= prev_close:
        return {"setup": "回踩不破", "detail": f"15分级别近6根K低点≥昨收{prev_close} → 支撑有效，等待放量确认"}
    if minute15[-1]["close"] > prev_close:
        return {"setup": "收回站上", "detail": "15分级别曾破昨收但已收回 → 观察能否站稳"}
    return {"setup": "压制", "detail": "15分级别运行昨收下方 → 无买点"}


def multi_timeframe_analysis(code: str) -> Dict[str, Any]:
    """四级金字塔综合（一只股票）。

    返回：方向(做/轻仓/回避) + 各周期明细 + 综合建议。
    """
    daily = fetch_daily_kline(code, count=120)
    if len(daily) < 40:
        return {"code": code, "error": "日K数据不足"}
    daily = attach_prev_close(daily)
    prev_close = daily[-1]["prev_close"]

    # 60分 / 15分 / 5分（新浪分钟K）
    minute60 = fetch_minute_kline(code, scale=60, count=60)
    minute15 = fetch_minute_kline(code, scale=15, count=80)
    minute5 = fetch_minute_kline(code, scale=5, count=96)

    d = daily_direction(daily)
    s60 = hour_60_strength(minute60, prev_close) if minute60 else {"level": "未知", "detail": "60分数据不足"}
    s15 = minute_15_setup(minute15, prev_close) if minute15 else {"setup": "无", "detail": "15分数据不足"}

    # 综合决策（文字①+②融合）
    state = d["state"]
    lim = d["limitup_signal"]
    signals = []

    if state == "强势":
        direction = "做"
        pos = "5-6成"
        signals.append("日线强势（全天站上昨收）→ 做多窗口")
    elif state == "震荡":
        direction = "轻仓"
        pos = "1-2成"
        signals.append("日线震荡（穿越昨收）→ 只做共振机会")
    else:
        direction = "回避"
        pos = "0仓"
        signals.append("日线弱势（压制昨收）→ 空仓观望，任何周期不动手")

    if lim["type"] != "无形态":
        signals.append(f"打板形态：{lim['name']}（评分{lim['score']} {lim['level']}级）{lim['position']}")
        if lim["level"] in ("A", "B"):
            direction = "做" if direction != "回避" else "轻仓"
            pos = "5-6成" if direction == "做" else "1-2成"

    if s60["level"] == "弱":
        signals.append("⚠️ 60分级别压制昨收 → 与日线方向冲突，降低优先级")
        if direction == "做":
            direction = "轻仓"
            pos = "1-2成"

    if s15["setup"] == "回踩不破":
        signals.append("15分回踩不破昨收 → 买点准备区，等待5分放量确认")
    elif s15["setup"] == "压制":
        signals.append("15分压制昨收下方 → 无买点")

    t0 = strategy.t0_signal_from_minutes(minute5, prev_close) if minute5 else {"signal": "不做", "detail": "5分数据不足"}
    add_reduce = strategy.add_reduce_signal_from_minutes(minute5, prev_close) if minute5 else {"action": "持有", "detail": "5分数据不足"}
    # 多周期共振：60分强 + 15分回踩不破 → 加仓②③可触发
    if s60["level"] == "强" and s15["setup"] == "回踩不破" and add_reduce["action"] == "持有":
        add_reduce = {"action": "加仓", "level": "+0.5份(60分共振)",
                      "detail": "60分强+15分回踩不破 → 放量突破站稳昨收可加0.5份（金字塔递减）"}
    return {
        "code": code,
        "prev_close": prev_close,
        "last_price": daily[-1]["close"],
        "direction": direction,
        "position": pos,
        "signals": signals,
        "daily": d,
        "min60": s60,
        "min15": s15,
        "min5_execute": strategy.opening_3min_signal(minute5, prev_close) if minute5 else {"signal": "未知"},
        "t0_signal": t0,
        "add_reduce": add_reduce,
    }


def batch_analysis(codes: List[str], top_n: int = 10) -> List[Dict[str, Any]]:
    """批量多周期分析（打板候选 → 逐只四级金字塔）。"""
    out = []
    for code in codes:
        try:
            r = multi_timeframe_analysis(code)
            if "error" not in r:
                out.append(r)
        except Exception:
            continue
    order = {"做": 0, "轻仓": 1, "回避": 2}
    out.sort(key=lambda x: (order.get(x.get("direction"), 3), -x["last_price"]))
    return out[:top_n]
