# -*- coding: utf-8 -*-
"""昨收价战法 v2.0 — 完整版（2026-08-09 从 web 工程 hunter-v2 完整替换）

战法核心: 只盯"昨日收盘价"一个数字, 日内四态 + 开盘3分钟定强弱 + 趋势分层仓位。

完整规则（与 web 工程 limitup-system 完全一致）:
- 买点A(挖坑转强/弱转强低吸): 低开或盘中跌破昨收 → 连续3根5分K收回站稳 → 低吸
- 买点B(强势延续): 开盘站稳昨收 + 回踩不破(容差0.2%) + 收阳(非涨停) → 加仓/建仓
- 重进: 清仓冷却(RE_ENTRY_CD=3天)后连续5根5分K站稳昨收 → 重新进场
- 离场铁律: 连续3根5分K有效跌破昨收(收盘确认防假跌破) → 清仓;
  上升趋势破位清仓需收盘<昨日MA10 (trend_clear_confirm 防过早卖出)
- 硬止损: 浮亏 ≥ stop_pct (默认5%, 与工作流一致; web 版安全网 9%)
- 趋势分层仓位: 上升8成/震荡5成/下降3成 (trend_layers)
- 日内四态: 强势(全>昨收)/弱势(全<昨收)/震荡(穿越)/骗线(近5根K稳定一侧)

接口兼容: check_prev_close / check_prev_close_exit 签名不变（runner/engine 不断链）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger("aurora.prev_close")

# 与 limitup_system/prev_close_params.py 对齐（web 工程 BEST_PARAMS 终态）
_TREND_LAYERS: bool = True          # 趋势分层: 上升8成/震荡5成/下降3成
_TREND_CLEAR_CONFIRM: bool = True   # 上升趋势破位清仓需收盘<昨日MA10
_STOP_PCT: float = 0.05             # 硬止损（工作流默认5%; web 安全网9%）
_RE_ENTRY_HOLD: int = 5             # 重进需连续N根5分K站稳昨收
_RE_ENTRY_CD: int = 3               # 清仓后冷却N个交易日


def _trend_state(close_vals: np.ndarray) -> str:
    """趋势状态机（与 limitup backtest.trend_state_by_day 同口径, 无未来函数）:
    用【昨日】收盘 vs 【截止昨日】MA10/MA20 排列。
    up = 昨日收盘 > MA10 > MA20；down = 昨日收盘 < MA10 < MA20；其余 range。
    """
    if close_vals is None or len(close_vals) < 22:
        return "range"
    px = close_vals[-2]                       # 昨日收盘
    win10 = close_vals[-11:-1]                # 截止昨日 10 日均线窗口
    win20 = close_vals[-21:-1]                # 截止昨日 20 日均线窗口
    ma10 = float(np.mean(win10)) if len(win10) >= 5 else px
    ma20 = float(np.mean(win20)) if len(win20) >= 10 else px
    if px > ma10 > ma20:
        return "up"
    if px < ma10 < ma20:
        return "down"
    return "range"


def _auto_entry_mode(kline_df) -> str:
    """按标的波动/趋势特征自动选买入模式 ('same_close' / 'next_open') — 工作流版。

    与 prev_close_strategy._auto_entry_mode 同口径(P0-② 2026-08-16, 纯K线可观测因子无未来函数):
      same_close = 当日收盘买(高波动强趋势, 吃隔夜跳空);
      next_open  = 次日开盘买(低波动/震荡, 避免追高)。
    判定: 近20日 ATR% >= 2.5 且 趋势分(=上涨占比×50 + chg20封顶±40) >= 25 → same_close; 否则 next_open。
    数据 <30 根 / 异常 → 保守 next_open。
    """
    if kline_df is None or len(kline_df) < 30:
        return "next_open"  # 数据不足 → 保守次日开盘买
    try:
        c = np.asarray(kline_df["close"].values, dtype=float)
        h = np.asarray(kline_df["high"].values, dtype=float)
        lo = np.asarray(kline_df["low"].values, dtype=float)
        o = np.asarray(kline_df["open"].values, dtype=float)
        prev_c = np.concatenate(([c[0]], c[:-1]))
        tr = np.maximum(h - lo, np.maximum(np.abs(h - prev_c), np.abs(lo - prev_c)))
        atr = float(tr[-20:].mean())
        atr_pct = atr / float(c[-1]) * 100 if c[-1] else 0.0
        if len(c) >= 21:
            rets = np.diff(c[-21:]) / np.maximum(c[-21:-1], 1e-9)
            chg20 = (float(c[-1]) / float(c[-21]) - 1.0) * 100 if c[-21] else 0.0
        else:
            rets = np.diff(c) / np.maximum(c[:-1], 1e-9)
            chg20 = 0.0
        up_ratio = float((rets > 0).mean())
        trend_score = up_ratio * 50 + min(max(chg20, -20), 40)
        if atr_pct >= 2.5 and trend_score >= 25:
            return "same_close"
        return "next_open"
    except Exception:
        return "next_open"


def _trend_target_pct(state: str) -> float:
    """趋势分层仓位（上升8成/震荡5成/下降3成）。"""
    if not _TREND_LAYERS:
        return 0.5
    return {"up": 0.8, "range": 0.5, "down": 0.3}.get(state, 0.5)


def _vol_ratio(vol: np.ndarray) -> float:
    """量比: 当日量 / 前21日均量(不含当日)。"""
    if vol is None or len(vol) < 22:
        return 1.0
    base = float(np.mean(vol[-22:-1])) + 1e-9
    return float(vol[-1]) / base


def check_prev_close(kline_df, minute_rows: Optional[List[Dict[str, Any]]] = None) -> dict:
    """昨收价战法信号检测（v2.0 完整版）。

    Args:
        kline_df: 日线K线DataFrame({date,open,close,high,low,volume})
        minute_rows: 可选 当日分钟K序列[{day,open,high,low,close,volume}] —
                     有则用完整日内判定（开盘3分钟定强弱+四态+买卖点）
    Returns:
        {"signal": bool, "score": int, "type": "A"/"B", "desc": str, "prev_close": float,
         "trend": "up"/"range"/"down", "target_pct": float}
    """
    if kline_df is None or len(kline_df) < 20:
        return {"signal": False, "score": 0, "type": "", "desc": "K线不足",
                "prev_close": 0, "trend": "range", "target_pct": 0.5}

    close = np.asarray(kline_df["close"].values, dtype=float)
    open_ = np.asarray(kline_df["open"].values, dtype=float)
    low = np.asarray(kline_df["low"].values, dtype=float)
    high = np.asarray(kline_df["high"].values, dtype=float)
    vol = np.asarray(kline_df["volume"].values, dtype=float)

    prev_close = close[-2] if len(close) >= 2 else 0.0
    if prev_close <= 0:
        return {"signal": False, "score": 0, "type": "", "desc": "无昨收",
                "prev_close": 0, "trend": "range", "target_pct": 0.5}

    trend = _trend_state(close)
    target_pct = _trend_target_pct(trend)
    o, c, l, h = open_[-1], close[-1], low[-1], high[-1]
    chg_pct = (c - prev_close) / prev_close * 100
    # 代码号: 优先 kline_df.attrs['code']（工作流 analyze_all 注入），兜底从 name 无法推断
    code = ""
    try:
        code = str(kline_df.attrs.get("code") or kline_df.attrs.get("code_", "") or "")
    except Exception:
        code = ""

    # ── 完整日内路径: 有当日分钟K（开盘3分钟定强弱 + 四态 + 买卖点）──
    if minute_rows and len(minute_rows) >= 6:
        try:
            from limitup_system.strategy import (buy_signal_from_minutes,
                                                 intraday_state_from_minutes,
                                                 opening_3min_signal)
            bias = opening_3min_signal(minute_rows, prev_close)
            state = intraday_state_from_minutes(minute_rows, prev_close)
            buy = buy_signal_from_minutes(minute_rows, prev_close)
            bsig = buy.get("signal", "")
            if bsig in ("弱转强低吸", "强延续"):
                vratio = _vol_ratio(vol)
                score = int(65 + min(max(chg_pct, 0) * 5, 20) + min(max(vratio - 1, 0) * 10, 10))
                # 下降趋势禁弱转强低吸（与 web 版一致）
                if bsig == "弱转强低吸" and trend == "down":
                    return {"signal": False, "score": 0, "type": "", "desc": f"下降趋势禁低吸[{state['state']}]",
                            "prev_close": round(prev_close, 3), "trend": trend, "target_pct": target_pct}
                return {"signal": True, "score": min(score, 95),
                        "type": "A" if bsig == "弱转强低吸" else "B",
                        "desc": f"{bsig}[{bias.get('bias','?')}/{state['state']}]:昨收{prev_close:.2f}",
                        "prev_close": round(prev_close, 3), "trend": trend, "target_pct": target_pct}
            return {"signal": False, "score": 0, "type": "",
                    "desc": f"无买点[{state['state']}]", "prev_close": round(prev_close, 3),
                    "trend": trend, "target_pct": target_pct}
        except Exception as e:  # 引擎不可用时降级日线近似
            logger.warning("[PrevClose] 分钟路径失败, 降级日线: %s", e)

    # ── 日线近似路径（全市场扫描场景, 收盘确认等效15分钟有效站稳）──
    # 买点A: 挖坑转强 (低开 + 盘中跌破昨收 + 收盘收回站稳), 下降趋势禁
    buy_A = (o < prev_close) and (l < prev_close) and (c > prev_close) and trend != "down"
    # 买点B: 强势延续 (站稳开盘 + 回踩不破 + 收阳) 且非涨停
    # ⭐ A股规则 (2026-08-12 合规审计): 涨停阈值按板块差异化——
    #   主板10% / 创业板(300/301)+科创板(688) 20% / 北交所30% (limitup_system.datafeed.limit_pct 同口径)
    try:
        from limitup_system.datafeed import limit_pct
        _lp = limit_pct(code)
    except Exception:
        _lp = 10.0
    limit_up = chg_pct >= (_lp - 0.5) and o == c   # 一字涨停(开=收=涨停)排除
    buy_B = (o >= prev_close) and (l >= prev_close) and (c > prev_close) \
            and (chg_pct < _lp - 1.0) and not limit_up

    if buy_A:
        recover = (c - prev_close) / prev_close * 100
        vratio = _vol_ratio(vol)
        score = int(60 + min(recover * 5, 20) + min(max(vratio - 1, 0) * 10, 20)
                    + (10 if trend == "up" else 0))
        return {"signal": True, "score": min(score, 95), "type": "A",
                "desc": f"挖坑转强:低开{o:.2f}破昨收{prev_close:.2f}收回{c:.2f}(+{recover:.1f}%)[{trend}]",
                "prev_close": round(prev_close, 3), "trend": trend, "target_pct": target_pct}
    if buy_B:
        strength = (c - prev_close) / prev_close * 100
        score = int(55 + min(strength * 5, 25) + (10 if trend == "up" else 0))
        return {"signal": True, "score": min(score, 95), "type": "B",
                "desc": f"强势延续:站稳昨收{prev_close:.2f}回踩不破收阳(+{strength:.1f}%)[{trend}]",
                "prev_close": round(prev_close, 3), "trend": trend, "target_pct": target_pct}

    return {"signal": False, "score": 0, "type": "",
            "desc": f"无昨收价买点[{trend}]", "prev_close": round(prev_close, 3),
            "trend": trend, "target_pct": target_pct}


def check_prev_close_exit(kline_df, entry_price: float,
                          minute_rows: Optional[List[Dict[str, Any]]] = None,
                          stop_pct: float = _STOP_PCT) -> dict:
    """持仓离场检查 — 昨收价体系完整离场铁律:
    ① 有效破位: 连续3根5分K收<昨收(有分钟K) 或 日线收盘<昨收 → 卖出
       (上升趋势需收盘<昨日MA10 确认, 防过早卖出 — trend_clear_confirm)
    ② 硬止损: 收盘 < 买入价×(1-stop_pct)
    ③ 假跌破识别: 盘中跌破昨收但收盘收回 → 持有(洗盘)
    Returns:
        {"exit": bool, "reason": str, "price": float}
    """
    if kline_df is None or len(kline_df) < 3:
        return {"exit": False, "reason": "", "price": 0}

    close = np.asarray(kline_df["close"].values, dtype=float)
    prev_close = close[-2]
    c = close[-1]
    l = float(kline_df["low"].values[-1])
    o = float(kline_df["open"].values[-1])

    # 硬止损优先（任何趋势下生效）
    if entry_price and entry_price > 0 and c < entry_price * (1 - stop_pct):
        return {"exit": True, "reason": f"硬止损-{stop_pct:.0%}", "price": c}

    # ── 分钟级路径: 连续3根5分K有效跌破 ──
    if minute_rows and len(minute_rows) >= 3:
        try:
            from limitup_system.strategy import sell_signal_from_minutes
            sell = sell_signal_from_minutes(minute_rows, prev_close)
            if sell.get("signal"):
                return {"exit": True, "reason": sell.get("desc", "有效破位"), "price": c}
        except Exception as e:
            logger.warning("[PrevClose] 分钟离场路径失败, 降级日线: %s", e)

    # 收盘跌破昨收 = 有效破位(收盘确认, 防盘中假跌破)
    if c < prev_close:
        # 上升趋势确认: 需收盘<昨日MA10 才清仓（防过早卖出, web 版 trend_clear_confirm）
        if _TREND_CLEAR_CONFIRM and _trend_state(close) == "up":
            ma10_yesterday = float(np.mean(close[-11:-1])) if len(close) >= 11 else prev_close
            if c >= ma10_yesterday:
                return {"exit": False, "reason": f"上升趋势回踩(收盘{c:.2f}≥昨日MA10{ma10_yesterday:.2f})", "price": 0}
        return {"exit": True, "reason": f"跌破昨收{prev_close:.2f}", "price": c}
    return {"exit": False, "reason": "", "price": 0}


def analyze_prev_close_intraday(minute_rows: List[Dict[str, Any]], prev_close: float) -> dict:
    """完整日内分析（盘中决策用）— 封装 limitup_system.strategy.full_analysis:
    日内四态 + 开盘3分钟定强弱 + 买/卖/T0/加减仓信号 + 仓位计划。

    Returns:
        {"state", "bias", "buy", "sell", "t0", "add_reduce", "position_plan"}
    """
    try:
        from limitup_system.strategy import full_analysis
        return full_analysis(minute_rows, prev_close)
    except Exception as e:
        logger.error("[PrevClose] 日内分析失败: %s", e)
        return {"error": str(e)}
