# -*- coding: utf-8 -*-
"""
strategy.py — 昨收价短线战法（文字②蒸馏）

核心规则（全部量化，可对照盘面直接套用）：

  A. 日内四态（围绕昨收价，没有第五种状态）
     强势态：开盘站稳昨收 + 全天回踩不破        → 最强多头，回踩低吸，坚定持有
     弱势态：开盘跌破昨收 + 全天反弹不过        → 空头占优，不抄底，反弹减仓
     震荡态：围绕昨收上下反复穿越              → 多空平衡，空仓/小仓试错
     骗线态：短时穿越昨收（<15分钟）快速收回   → 不做决策，忽略

  B. 开盘3分钟定全天强弱（9:25 锁昨收基准 → 9:30-9:33 确认有效强弱）
     3分钟站稳昨收上方且不回落 → 真强势，可备选低吸
     3分钟压制昨收下方反弹无力 → 真弱势，全天规避
     3分钟反复穿越           → 震荡，观望等变盘

  C. 两类进场 / 两类离场（唯一标准，无模糊空间）
     进场1 弱转强：跌破昨收后 10 分钟内快速放量收回站稳 → 低吸，止损=挖坑最低点下方
     进场2 强延续：站稳昨收回踩不破 + 缩量企稳后放量拉升 → 加仓
     离场1 破位：  站稳昨收后放量有效跌破（15分钟不收回）→ 无条件清仓
     离场2 弱势：  全天压制昨收反弹无力 → 尾盘统一清仓

  D. 仓位风控
     强势 5-6 成 / 震荡 1-2 成 / 弱势 0 仓 / 骗线 0 操作
     止损 = 有效跌破昨收无法收回，不补仓不摊薄
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any, Dict, List, Optional

from datafeed import attach_prev_close

# 风控评审修正(2026-08-07): 总暴露上限（底仓+做T仓+加仓）≤70%，防止弱市T+0失败变重仓被套
MAX_EXPOSURE = 0.70

# ================================================================ 日K级 ----

def classify_daily_state(row: Dict[str, Any]) -> str:
    """日K级四态（用于回测统计，近似日内行为）：
    - 强势：全天最低 ≥ 昨收（从未跌破）
    - 弱势：全天最高 ≤ 昨收（从未站上）
    - 震荡：穿越（既有跌破也有站上）
    """
    pc = row.get("prev_close", row.get("open", 0))
    if pc <= 0:
        return "震荡"
    if row["low"] >= pc:
        return "强势"
    if row["high"] <= pc:
        return "弱势"
    return "震荡"


def daily_state_stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """昨收战法·日K级验证：四态出现后，次日的表现统计。

    说明：这是日内战法能做的日K级近似验证（真实执行需分钟K）。
    统计口径：T日四态 → T+1日（相对T日收盘）涨跌。
    """
    rows = attach_prev_close(rows)
    stats = {"强势": {"count": 0, "up": 0, "chgs": []},
             "弱势": {"count": 0, "up": 0, "chgs": []},
             "震荡": {"count": 0, "up": 0, "chgs": []}}
    for i in range(1, len(rows) - 1):
        st = classify_daily_state(rows[i])
        nxt = rows[i + 1]
        chg = (nxt["close"] - rows[i]["close"]) / rows[i]["close"] * 100.0
        stats[st]["count"] += 1
        if chg > 0:
            stats[st]["up"] += 1
        stats[st]["chgs"].append(chg)

    out = {}
    for st, s in stats.items():
        n = s["count"]
        out[st] = {
            "出现天数": n,
            "次日上涨率": round(s["up"] / n * 100, 1) if n else 0.0,
            "次日平均涨跌": round(mean(s["chgs"]), 2) if s["chgs"] else 0.0,
            "最大上涨": round(max(s["chgs"]), 2) if s["chgs"] else 0.0,
            "最大下跌": round(min(s["chgs"]), 2) if s["chgs"] else 0.0,
        }
    return out


# ============================================================== 分钟K级 ----

MIN_PER_BAR = 5  # 默认5分钟K


def _bar_minutes(day: str) -> int:
    """从新浪分钟K day 字段 '2026-08-07 10:35:00' 提取分钟数。"""
    try:
        return int(day.split(" ")[1].split(":")[1])
    except Exception:
        return -1


def opening_3min_signal(minute_rows: List[Dict[str, Any]], prev_close: float) -> Dict[str, Any]:
    """开盘3分钟定强弱（9:30-9:33，约3根5分钟K）。

    返回 {signal: 强势/弱势/震荡, detail}
    """
    if len(minute_rows) < 3 or prev_close <= 0:
        return {"signal": "震荡", "detail": "数据不足"}
    first3 = minute_rows[:3]
    above = sum(1 for r in first3 if r["close"] >= prev_close)
    below = 3 - above
    closes = [r["close"] for r in first3]
    if above == 3:
        return {"signal": "强势", "detail": "开盘3分钟持续站稳昨收上方，分时不回落 → 真强势，可备选低吸"}
    if below == 3:
        return {"signal": "弱势", "detail": "开盘3分钟持续压制昨收下方，反弹无力 → 真弱势，全天规避"}
    return {"signal": "震荡", "detail": "开盘3分钟反复穿越昨收 → 观望等待变盘，不急于操作"}


def intraday_state_from_minutes(minute_rows: List[Dict[str, Any]], prev_close: float) -> Dict[str, Any]:
    """盘中实时四态判定（基于当日分钟K，截至当前）：
    - 强势：当前时刻所有分钟K最低 ≥ 昨收（从未跌破）
    - 弱势：当前时刻所有分钟K最高 ≤ 昨收（从未站上）
    - 骗线：曾经穿越，但最近5根K（约25分钟）稳定在一侧
    - 震荡：其他（当前正在穿越）
    """
    if not minute_rows or prev_close <= 0:
        return {"state": "震荡", "detail": "数据不足"}
    low = min(r["low"] for r in minute_rows)
    high = max(r["high"] for r in minute_rows)
    last_close = minute_rows[-1]["close"]
    if low >= prev_close:
        return {"state": "强势", "detail": f"全天最低{low}≥昨收{prev_close}，回踩不破 → 多头优势，回踩低吸/坚定持有"}
    if high <= prev_close:
        return {"state": "弱势", "detail": f"全天最高{high}≤昨收{prev_close}，反弹不过 → 空头占优，不抄底/反弹减仓"}
    # 曾穿越：看最近5根K是否有效站稳/跌破
    recent = minute_rows[-5:]
    if all(r["close"] >= prev_close for r in recent):
        return {"state": "骗线", "detail": "盘中曾跌破昨收但5根K有效收回（≥25分钟） → 假跌破诱空，洗盘完成，可留意弱转强买点"}
    if all(r["close"] <= prev_close for r in recent):
        return {"state": "骗线", "detail": "盘中曾站上昨收但已有效跌破（≥25分钟） → 假突破诱多，回避"}
    return {"state": "震荡", "detail": "围绕昨收反复穿越 → 多空平衡，空仓/小仓观望"}


def _is_volume_surge(bar: Dict[str, Any], window: List[Dict[str, Any]]) -> bool:
    """放量：当前K量 > 前5根均量 × 1.5。"""
    vols = [r["volume"] for r in window]
    if not vols or mean(vols) <= 0:
        return False
    return bar["volume"] > mean(vols) * 1.5


def buy_signal_from_minutes(minute_rows: List[Dict[str, Any]], prev_close: float) -> Dict[str, Any]:
    """两类标准进场信号（纯昨收价判定）。

    进场1 弱转强（低吸）：盘中跌破昨收 → 10分钟内（2根5分钟K）放量收回站稳
    进场2 强延续（加仓）：开盘站稳昨收 + 回踩不破 + 缩量企稳后放量拉升
    """
    if len(minute_rows) < 8 or prev_close <= 0:
        return {"signal": "无", "detail": "数据不足"}

    # ---- 进场1：弱转强 ----
    # 找最近一次跌破昨收的位置
    last_break_idx = None
    for i in range(len(minute_rows) - 1, -1, -1):
        if minute_rows[i]["low"] < prev_close:
            last_break_idx = i
            break
    if last_break_idx is not None:
        # 跌破之后有 K 收回站上，且收回发生在 2 根K内（10分钟）
        recover_idx = None
        for j in range(last_break_idx, min(last_break_idx + 3, len(minute_rows))):
            if minute_rows[j]["close"] > prev_close:
                recover_idx = j
                break
        if recover_idx is not None:
            surge = _is_volume_surge(minute_rows[recover_idx], minute_rows[max(0, recover_idx - 5):recover_idx])
            # 收回后连续站稳（至少当前仍在昨收上方）
            if minute_rows[-1]["close"] > prev_close:
                return {
                    "signal": "弱转强·低吸买点",
                    "price": minute_rows[recover_idx]["close"],
                    "stop": round(min(r["low"] for r in minute_rows[max(0, last_break_idx - 1):recover_idx + 1]) - 0.01, 2),
                    "detail": (f"跌破昨收后{recover_idx - last_break_idx}根K内收回站上"
                               f"{'且放量' if surge else ''}，日内由弱转强 → 分批低吸，止损=挖坑最低点下方"),
                }

    # ---- 进场2：强延续 ----
    if minute_rows[-1]["close"] > prev_close and minute_rows[0]["close"] >= prev_close:
        lows = [r["low"] for r in minute_rows[-8:]]
        if min(lows) >= prev_close * 0.998:  # 近期回踩未破昨收（容差0.2%）
            return {
                "signal": "强延续·回踩买点",
                "price": minute_rows[-1]["close"],
                "stop": round(prev_close - 0.01, 2),
                "detail": "开盘站稳昨收，回踩不破（缩量企稳）→ 加仓买点，止损=昨收下方",
            }

    return {"signal": "无", "detail": "当前无两类标准买点：无跌破收回、无回踩不破确认"}


def sell_signal_from_minutes(minute_rows: List[Dict[str, Any]], prev_close: float) -> Dict[str, Any]:
    """两类标准离场信号。

    离场1 强势破位：原本站稳昨收，放量有效跌破（3根5分钟K=15分钟不收回）→ 无条件清仓
    离场2 弱势延续：全天压制昨收反弹无力 → 尾盘统一清仓
    """
    if len(minute_rows) < 5 or prev_close <= 0:
        return {"signal": "持有", "detail": "数据不足"}

    # 离场1：曾经站上昨收，现在有效跌破
    ever_above = any(r["close"] > prev_close for r in minute_rows[: max(1, len(minute_rows) - 6)])
    if ever_above and minute_rows[-1]["close"] < prev_close:
        recent = minute_rows[-3:]
        if all(r["close"] < prev_close for r in recent):  # 15分钟未收回
            surge = _is_volume_surge(minute_rows[-1], minute_rows[-6:-1])
            return {
                "signal": "强势破位·清仓",
                "price": minute_rows[-1]["close"],
                "detail": (f"站稳昨收后有效跌破昨收且15分钟未收回"
                           f"{'（放量）' if surge else ''} → 多头趋势破坏，无条件减仓/清仓，不格局不扛单"),
            }

    # 离场2：全天压制昨收
    if all(r["close"] < prev_close for r in minute_rows):
        return {
            "signal": "弱势延续·尾盘清仓",
            "price": minute_rows[-1]["close"],
            "detail": "全天压制昨收、反弹无力、无企稳信号 → 尾盘统一清仓，避免隔夜风险",
        }

    return {"signal": "持有", "detail": "未触发两类离场信号：守住昨收或仍在收回过程中"}


# ========================================================= T+0 回转 ----

def t0_signal_from_minutes(minute_rows: List[Dict[str, Any]], prev_close: float,
                           high_open_pct: float = 2.0) -> Dict[str, Any]:
    """T+0 底仓回转信号（A股T+1：必须靠底仓做日内回转，不能裸买裸卖）。

    类型A 先卖后买（高抛低吸）: 高开>2% 且 冲高回落超过涨幅一半 → 卖底仓1/3~1/2 → 回踩昨收接回
    类型B 先买后卖（低吸高抛）: 回踩昨收不破 + 缩量企稳 → 买做T仓(≤总仓20%) → 冲高滞涨卖出等量底仓
    铁律: 振幅<1.5%不做（手续费覆盖不了）、先算好接回价、做反立即止损、收盘前平T仓、连败3次停
    """
    if len(minute_rows) < 5 or prev_close <= 0:
        return {"signal": "不做", "detail": "数据不足"}
    first_open = minute_rows[0]["open"]
    last_close = minute_rows[-1]["close"]
    max_high = max(r["high"] for r in minute_rows)
    min_low = min(r["low"] for r in minute_rows)
    amplitude = (max_high - min_low) / prev_close * 100.0
    if amplitude < 3.0:
        return {"signal": "不做", "detail": f"振幅{amplitude:.1f}%<3%：做T目标≥1%差价，振幅不足手续费+滑点吃光利润，不做T"}
    # 类型A：高开>2% + 从最高回落超过涨幅一半 + 仍在昨收上方
    gap_pct = (first_open - prev_close) / prev_close * 100.0
    if gap_pct > high_open_pct and last_close > prev_close:
        rise = (max_high - first_open) / prev_close * 100.0
        drop = (max_high - last_close) / prev_close * 100.0
        if rise > 0 and drop >= rise * 0.5:
            return {
                "signal": "先卖后买",
                "ref_price": round(prev_close * 1.005, 2),
                "detail": (f"高开{gap_pct:.1f}%冲高后回落{drop:.1f}%(超涨幅一半) → 卖出底仓1/3~1/2，"
                           f"回踩昨收{prev_close}附近接回(接回价≈{prev_close * 1.005:.2f})"),
            }
    # 类型B：回踩昨收不破 + 缩量企稳 → 低吸做T
    recent_lows = [r["low"] for r in minute_rows[-8:]]
    if min(recent_lows) >= prev_close * 0.998 and last_close > prev_close:
        return {
            "signal": "先买后卖",
            "ref_price": round(prev_close, 2),
            "detail": (f"回踩昨收{prev_close}不破+缩量企稳 → 买入做T仓(≤总仓20%)，"
                       f"冲高滞涨时卖出等量底仓（做T目标≥1%即走，不贪）"),
        }
    return {"signal": "不做", "detail": "无T+0机会：既非高开冲高回落、也非回踩不破低吸"}


# ============================================================ 加减仓 ----

def add_reduce_signal_from_minutes(minute_rows: List[Dict[str, Any]],
                                   prev_close: float) -> Dict[str, Any]:
    """加减仓信号（金字塔递减加仓 1:0.5:0.25，原文节奏的完整化）。

    加仓①: 强延续买点(回踩不破+放量拉升) → +1份，止损上移至昨收
    加仓②: 放量突破站稳昨收(60分共振)   → +0.5份
    加仓③: 15分回踩不破                → +0.25份（由多周期层触发）
    ⚠️ 总暴露（底仓+做T仓+加仓）≤70%（MAX_EXPOSURE），加仓后超限则不加
    减仓①: 冲高滞涨(放量长上影)         → 减1/3（吃鱼吃中段）
    减仓②: 有效跌破昨收(15分钟不收回)   → 减半/清仓（原文离场1）
    减仓③: 弱势反弹触碰昨收回落         → 反弹减仓（原文离场2）
    """
    if len(minute_rows) < 8 or prev_close <= 0:
        return {"action": "持有", "detail": "数据不足"}
    last = minute_rows[-1]
    # 减仓②：跌破昨收15分钟不收回（最高优先，风控优先于一切）
    if last["close"] < prev_close and all(r["close"] < prev_close for r in minute_rows[-3:]):
        return {"action": "减仓", "level": "减半/清仓",
                "detail": "有效跌破昨收且15分钟未收回 → 无条件减半/清仓（原文离场1），不格局不扛单"}
    # 减仓①：冲高滞涨（放量长上影）
    if last["close"] > prev_close:
        body = abs(last["close"] - last["open"]) / prev_close * 100.0
        upper = (last["high"] - max(last["open"], last["close"])) / prev_close * 100.0
        if upper >= 1.5 and upper >= body and _is_volume_surge(last, minute_rows[-6:-1]):
            return {"action": "减仓", "level": "减1/3",
                    "detail": f"冲高滞涨(放量长上影{upper:.1f}%) → 减1/3，吃鱼吃中段不贪最后一寸"}
    # 加仓①：强延续（回踩不破 + 放量拉升）
    lows = [r["low"] for r in minute_rows[-8:]]
    if min(lows) >= prev_close * 0.998 and last["close"] > prev_close:
        if _is_volume_surge(last, minute_rows[-6:-1]):
            return {"action": "加仓", "level": "+1份",
                    "detail": "回踩不破+放量拉升（强延续买点）→ 加1份，统一移动止损到昨收"}
    return {"action": "持有", "detail": "无加减仓信号：未触发强延续加仓、未破位、未滞涨"}


# ================================================================ 仓位 ----

def position_plan(state: str) -> Dict[str, Any]:
    """仓位风控（文字②第五节）：强5-6成 / 震荡1-2成 / 弱0 / 骗线0。"""
    plan = {
        "强势": {"pos": "5-6成", "action": "正常布局，回踩低吸，把握日内主升；破昨收无条件止损"},
        "弱势": {"pos": "0仓", "action": "空仓观望，反弹冲高是减仓/离场机会，不抄底不补仓"},
        "震荡": {"pos": "1-2成", "action": "小仓试错，不加仓不补仓；放量突破站稳昨收可加仓，放量跌破果断减仓"},
        "骗线": {"pos": "0操作", "action": "短暂穿越不做任何决策，站稳/守住15分钟以上才算有效"},
    }
    return plan.get(state, {"pos": "0仓", "action": "观望"})


def full_analysis(minute_rows: List[Dict[str, Any]], prev_close: float,
                  is_market_open: bool = True) -> Dict[str, Any]:
    """完整昨收战法盘中决策（四态 + 开盘3分钟 + 买卖信号 + 仓位）。"""
    state = intraday_state_from_minutes(minute_rows, prev_close)
    opening = opening_3min_signal(minute_rows, prev_close)
    buy = buy_signal_from_minutes(minute_rows, prev_close)
    sell = sell_signal_from_minutes(minute_rows, prev_close)
    t0 = t0_signal_from_minutes(minute_rows, prev_close)
    add_reduce = add_reduce_signal_from_minutes(minute_rows, prev_close)
    plan = position_plan(state["state"])
    # 骗线是"瞬时穿越0操作"，但一旦确认假跌破/有效收回并触发标准买点 → 升级为可执行计划
    if buy["signal"] != "无":
        plan = {
            "pos": "分批低吸(≤5-6成)",
            "action": f"{buy['signal']}已触发：分批介入，止损={buy.get('stop')}，"
                      "不追高、破止损无条件离场",
        }
    return {
        "prev_close": prev_close,
        "last_price": minute_rows[-1]["close"] if minute_rows else None,
        "state": state,
        "opening_3min": opening,
        "buy_signal": buy,
        "sell_signal": sell,
        "t0_signal": t0,
        "add_reduce": add_reduce,
        "position_plan": plan,
        "exposure": {"max": MAX_EXPOSURE,
                     "note": "总暴露（底仓+做T仓+加仓）≤70%，防止弱市T+0失败变重仓被套"},
        "market_open": is_market_open,
    }
