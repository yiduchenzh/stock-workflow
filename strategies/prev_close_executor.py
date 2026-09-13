# -*- coding: utf-8 -*-
"""昨收战法盘中执行器 v1.0 — 与 web 工程 auto_trader.py 执行层完全一致（2026-08-09 移植）

信号链（与 hunter-v2/backend/auto_trader.py _tick_stock 1:1 对齐）:
  建仓 = 空仓 + 开盘3分钟站稳昨收(前3根5分K收>昨收) → 趋势分层仓位(升8成/震5成/降3成)
  破位清仓 = 连续5根5分K收<昨收
  T0高抛 = 冲高回落(high距昨收≥4%且上影≥0.3%) → 卖底仓30% → 回踩/尾盘15:00接回
  加仓 = 全天低点≥昨收×0.998 且放量(末量≥前5均量×ADD_VOL) → 加仓≤底仓30%（下降趋势禁/池外禁）
  减仓 = 当日涨幅达1.5% → 减半仓（锁盈）
  止损 = 持仓浮亏≥9% 且 ≥14:50 → 尾盘清仓（P2 安全网）
  重进 = 清仓当日黑名单(just_sold)禁买回；次日开盘3分钟站稳即可重进

纯信号函数，不依赖数据库；执行由调用方（engine.step_monitor）负责。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("aurora.prev_close_exec")

# ═══ 常量（与 web auto_trader.py 完全一致）═══
TREND_TARGET_PCT: Dict[str, float] = {"up": 0.8, "range": 0.5, "down": 0.3}
T0_PCT: float = 0.3            # 做T用底仓30%
STOP_SINGLE_PCT: float = 9.0   # 单笔止损（与回测 BEST_PARAMS 对齐）
ADD_VOL: float = 1.0           # 加仓放量倍数
# ⭐ 2026-08-16 P0-② 开盘跳空熔断: 开盘价相对持仓成本向下跳空超过此阈值 → 开盘无条件止损。
#   治 600363 案例(-19.5%): 硬止损 8% 只在盘中/尾盘按"跳空已实现"后的跳空价成交, 形同虚设;
#   只有在【开盘价 vs 成本】见杀时立即按开盘价卖出, 才能把亏损钳制在阈值附近。
#   默认 8.0(%); 可由 engine 传入 config.yaml risk.gap_down_stop_pct 覆盖（0=关闭熔断）。
GAP_DOWN_STOP_PCT: float = 8.0
# ⭐ 2026-08-11 对齐实盘 v14.54: 关闭减仓（原1.5=起步削仓吃不全趋势, 回测+65pp实证）
#   999=永不触发; 减仓代码保留但行为关闭（与 web REDUCE_UPPER=999 / 回测 reduce_upper=999 三侧一致）
REDUCE_UPPER: float = 999.0   # 关闭减仓（原 1.5）
T0_RISE_PCT: float = 4.0       # T0高抛: high距昨收≥4%
T0_UPPER_PCT: float = 0.3      # T0高抛: 上影≥0.3%
BREAK_HOLD: int = 5            # 破位: 连续5根5分K收<昨收


def trend_state(closes: List[float]) -> str:
    """趋势状态: up/range/down（MA10/MA20 快判定, 与 web _trend_state 同口径, 无未来函数）"""
    if not closes or len(closes) < 22:
        return "range"
    px_prev = float(closes[-2])
    ma10 = sum(float(x) for x in closes[-11:-1]) / 10
    ma20 = sum(float(x) for x in closes[-21:-1]) / 20
    if px_prev > ma10 > ma20:
        return "up"
    if px_prev < ma10 < ma20:
        return "down"
    return "range"


# ═══ 当时择优分（老陈 2026-08-10: "选出股票后怎么区分哪个最适合当时买入"）═══
# 公式: 0.35×信号强度分 + 0.20×竞价CC + 0.15×趋势 + 0.15×板块热度 + 0.15×龙头
# 原则: 信号分只是入场资格, 不是买入理由; 同样站稳昨收, 先买"竞价被抢筹+板块风口+龙头"
_PRIORITY_W = {
    "signal": 0.35, "cc": 0.20, "trend": 0.15, "heat": 0.15, "leader": 0.15,
}
_TREND_NORM = {"up": 1.0, "range": 0.5, "down": 0.0}


def buy_priority_score(c: Dict[str, Any]) -> float:
    """单只候选的"当时择优分"（0~1）。

    输入字段（全部归一化）:
      best_score/score   信号强度分 → /100 归一 (0.35)
      auction.cc         竞价承接力 → /3 封顶  (0.20)  ← 当日主力意图, 最新
      trend              up=1/range=0.5/down=0 (0.15)   ← 日线安全边际
      sector_heat        板块涨幅% → (heat+3)/8 归一 (0.15) ← 风口
      is_leader          板块龙头 → 1/0 (0.15)          ← 只做龙头
    """
    sig = float(c.get("best_score") or c.get("score") or 0)
    sig_n = min(max(sig / 100.0, 0.0), 1.0)

    cc = float((c.get("auction") or {}).get("cc") or 0)
    cc_n = min(max(cc / 3.0, 0.0), 1.0)

    tr = c.get("trend") or "range"
    tr_n = _TREND_NORM.get(tr, 0.5)

    heat = float(c.get("sector_heat") or 0)
    heat_n = min(max((heat + 3.0) / 8.0, 0.0), 1.0)

    leader_n = 1.0 if c.get("is_leader") else 0.0

    return (0.35 * sig_n + 0.20 * cc_n + 0.15 * tr_n
            + 0.15 * heat_n + 0.15 * leader_n)


def rank_buy_priority(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """候选池按"当时择优分"降序排序（不修改原候选, 返回副本 + buy_priority/is_leader 字段）。

    龙头近似（stock-workflow 无东财 leader_code 时）: 同板块内 change_pct 最高者视为龙头。
    趋势缺失时按 range 中性处理（调用方可预先挂 trend 字段）。
    """
    if not candidates:
        return []
    sector_best: Dict[str, float] = {}
    for c in candidates:
        ind = c.get("industry", "")
        chg = float(c.get("change_pct") or -999.0)
        if chg > sector_best.get(ind, -999.0):
            sector_best[ind] = chg
    out: List[Dict[str, Any]] = []
    for c in candidates:
        cc = dict(c)
        ind = cc.get("industry", "")
        chg = float(cc.get("change_pct") or -999.0)
        if not cc.get("is_leader") and ind and chg > 0 and chg >= sector_best.get(ind, -999.0):
            cc["is_leader"] = True  # 板块内涨幅最高 = 龙头近似
        cc["buy_priority"] = round(buy_priority_score(cc), 3)
        out.append(cc)
    out.sort(key=lambda x: x["buy_priority"], reverse=True)
    return out


def fetch_min5_today(code: str, day: str = "") -> List[Dict[str, Any]]:
    """mootdx 直拉当日5分钟K（frequency=0; ⭐ P1-1 修复: mootdx 5分K vol 单位=股, 不再×100），升序返回。

    （与 web _fetch_min5_today 同源: mootdx 通达信, 盘中包含未收盘的当前K）
    ⭐ 2026-08-11 审计实测: mootdx 5分K vol 单位是【股】(600667 10:55=1,487,600股),
      日K vol 单位是【手】(300426 08-10=576255手) —— 两个频率单位不同, 5分K 不能×100。
    """
    if not day:
        day = datetime.now().strftime("%Y-%m-%d")
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market="std")
        bars = client.bars(symbol=code, frequency=0, start=0, offset=800)
        if bars is None or len(bars) == 0:
            return []
        out: List[Dict[str, Any]] = []
        for _, row in bars.iterrows():
            dt = str(row.get("datetime"))[:16].replace("T", " ")
            if len(dt) < 16 or dt[:10] != day:
                continue
            out.append({
                "day": dt,
                "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"]),
                "volume": float(row.get("vol") or 0),  # ⭐ P1-1: 已是股, 不×100
            })
        out.sort(key=lambda x: x["day"])
        return out
    except Exception as e:
        logger.warning("[PrevCloseExec] %s 5分K失败: %s", code, e)
        return []


def check_entry(m5: List[Dict[str, Any]], prev_close: float,
                avg5_vol: float = 0.0, vol_confirm: float = 1.0) -> Tuple[bool, float]:
    """建仓判定: 开盘3分钟站稳昨收（前3根5分K收>昨收）+ 量能确认（P1, 与回测 BEST_PARAMS 一致）。

    ⭐ 2026-08-10 P1 同步: 开盘3根累计量 > 前5日日K均量(手)×vol_confirm——治"无量假强势"建仓
    Args:
        m5: 当日5分K(升序, volume=股)
        prev_close: 昨收
        avg5_vol: 前5日日K均量(手, 调用方喂入; 0=不检查)
        vol_confirm: 量能倍率(1.0=需放量)
    Returns:
        (是否可建仓, 建仓价)
    """
    if len(m5) < 3 or prev_close <= 0:
        return False, 0.0
    if not all(float(k["close"]) > prev_close for k in m5[:3]):
        return False, 0.0
    # ⭐ P1-量能确认: 开盘3根累计量(股) > 前5日均量(手×100)
    if avg5_vol > 0:
        vol3 = sum(float(k.get("volume") or 0) for k in m5[:3])
        if vol3 <= avg5_vol * 100.0 * vol_confirm:
            return False, 0.0
    return True, float(m5[2]["close"])


def analyze_hold(m5: List[Dict[str, Any]], prev_close: float, trend: str,
                 shares: int, sellable: int, cost: float, in_pool: bool,
                 t0_pending: int = 0, env_strong: bool = False,
                 gap_down_stop_pct: float = GAP_DOWN_STOP_PCT) -> Tuple[List[Dict[str, Any]], int]:
    """持仓逐根扫描（与 web _tick_stock 持仓段 1:1）。

    Args:
        m5: 当日5分K序列(升序)
        prev_close: 昨收
        trend: up/range/down
        shares: 总持仓股数
        sellable: 可卖股数(=shares - 今日买入锁定)
        cost: 持仓成本价(avg_cost)
        in_pool: 是否强势池内（池外禁加仓, web 强势股核心）
        t0_pending: 待接回股数（跨tick累计）
        env_strong: 大盘强(上证/创业板涨) —— ⭐ P2 环境分级清仓: up+大盘强 → 破位容忍+2根(洗盘不跑)
        gap_down_stop_pct: ⭐ P0-② 开盘跳空熔断阈值(%, 0=关闭)。开盘价相对成本
            向下跳空≥此阈值 → 开盘无条件止损（治 600363 -19.5%: 硬止损8%形同虚设）
    Returns:
        (signals, new_t0_pending)
        signals: [{action: 清仓/开门跳空止损/T0高抛/T0接回/加仓/减仓/止损清仓, price, shares, reason, time}]
    """
    signals: List[Dict[str, Any]] = []
    t0 = t0_pending
    if not m5 or prev_close <= 0:
        return signals, t0

    # ⭐ P0-② 开盘跳空熔断: 开盘第一根5分K open 相对持仓成本跳空超限 → 无条件开盘止损。
    #   这是当日最早的可成交信号, 必须先于破位/盘中/尾盘止损执行（否则止损按跳空后价成交形同虚设）。
    #   阈值 gap_down_stop_pct<=0 表示关闭熔断（不比较）。
    if cost > 0 and sellable >= 100 and gap_down_stop_pct > 0:
        open_px = float(m5[0]["open"])
        open_gap = (open_px - cost) / cost * 100.0
        if open_gap <= -gap_down_stop_pct:
            signals.append({"action": "开盘跳空止损", "price": open_px, "shares": sellable,
                            "reason": f"开盘跳空{open_gap:.1f}%≤-{gap_down_stop_pct}%, 开盘强制止损",
                            "time": str(m5[0].get("day", ""))[11:16]})
            return signals, t0

    day_high = 0.0
    day_min_low = float("inf")
    vols = [float(k["volume"]) for k in m5]
    # ⭐ P2 环境分级: up趋势+大盘强 → 破位容忍 +2 根（与回测 CLEAR_ENV_RELAX=2 一致）
    hold_eff = BREAK_HOLD + 2 if (trend == "up" and env_strong) else BREAK_HOLD

    for i, k in enumerate(m5):
        kt = str(k.get("day", ""))[11:16]
        kh = float(k["high"]); kl = float(k["low"]); kc = float(k["close"])
        day_high = max(day_high, kh)
        day_min_low = min(day_min_low, kl)

        # ① 破位清仓: 连续 hold_eff 根5分K收<昨收（up+大盘强容忍7根, 其余5根）
        if i >= hold_eff - 1 and all(float(x["close"]) < prev_close for x in m5[i - hold_eff + 1:i + 1]):
            if sellable >= 100:
                signals.append({"action": "清仓", "price": kc, "shares": sellable,
                                "reason": f"连续{hold_eff}根5分K跌破昨收" + ("(up+大盘强, 容忍洗盘)" if hold_eff > BREAK_HOLD else ""), "time": kt})
            return signals, t0  # 清仓后本 tick 结束

        # ①b 盘中浮动止损（⭐ 2026-08-13 同步 auto_trader.py _tick_stock 的盘中止损）:
        #    原止损只 ⑥ 尾盘14:50浮亏9% —— 盘中深亏(-5~-8%)拖到尾盘一刀割(本周艾罗-1165/引力-1156根因)。
        #    改为盘中逐K: 浮亏≥5% 且 连续3根5分K收<昨收 → 立即止损(T+1可卖部分当日止损)。
        if cost > 0 and sellable >= 100:
            loss_pct = (kc - cost) / cost * 100.0
            if loss_pct <= -5.0 and i >= 2 and all(float(m5[j]["close"]) < prev_close for j in range(i - 2, i + 1)):
                signals.append({"action": "盘中止损", "price": kc, "shares": sellable,
                                "reason": f"盘中止损: 浮亏{loss_pct:.1f}%≥5%且3根跌破昨收", "time": kt})
                return signals, t0

        # ② T0高抛: 冲高回落（high距昨收≥4% 且 上影≥0.3%）
        rise = (kh - prev_close) / prev_close * 100.0
        upper = (kh - max(float(k["open"]), kc)) / prev_close * 100.0
        if rise >= T0_RISE_PCT and upper >= T0_UPPER_PCT and sellable >= 100:
            t0_shares = int(sellable * T0_PCT / 100) * 100
            if t0_shares >= 100:
                signals.append({"action": "T0高抛", "price": kh * 0.998, "shares": t0_shares,
                                "reason": f"冲高回落(距昨收{rise:.1f}%), 高抛{t0_shares}股", "time": kt})
                t0 += t0_shares

        # ③ T0接回: 回踩昨收不破 或 尾盘15:00强制
        if t0 > 0 and ((kl <= prev_close * 1.005 and kc >= prev_close) or kt == "15:00"):
            signals.append({"action": "T0接回", "price": kc, "shares": t0,
                            "reason": "回踩接回/尾盘强制", "time": kt})
            t0 = 0

    # ④ 加仓: 全天低点≥昨收×0.998 且 放量(末量≥前5均量×ADD_VOL)
    #    下降趋势禁（防下降过多买入连亏）; 池外持仓票禁（web 强势股核心）; 可卖底仓≥200股
    if trend != "down" and in_pool and sellable >= 200:
        avg5v = sum(vols[-6:-1]) / 5 if len(vols) >= 6 else 0.0
        add_ok = day_min_low >= prev_close * 0.998 and avg5v > 0 and (vols[-1] if vols else 0) >= avg5v * ADD_VOL
        if add_ok:
            add_shares = int(sellable * 0.3 / 100) * 100  # 加仓≤底仓30%
            if add_shares >= 100:
                signals.append({"action": "加仓", "price": float(m5[-1]["close"]), "shares": add_shares,
                                "reason": f"回踩不破+放量, 加仓{add_shares}股({trend})", "time": str(m5[-1].get("day", ""))[11:16]})

    # ⑤ 减仓: 当日涨幅达1.5% → 减半仓（锁盈）
    if day_high > 0 and sellable >= 200:
        day_gain = (day_high - prev_close) / prev_close * 100.0
        if day_gain >= REDUCE_UPPER:
            red_shares = int(sellable * 0.5 / 100) * 100
            if red_shares >= 100:
                signals.append({"action": "减仓", "price": float(m5[-1]["close"]), "shares": red_shares,
                                "reason": f"当日涨幅{day_gain:.1f}%≥{REDUCE_UPPER}%, 减仓锁盈", "time": str(m5[-1].get("day", ""))[11:16]})

    # ⑥ 单笔止损: 持仓浮亏≥9% 且 ≥14:50 → 尾盘清仓（P2 安全网）
    if cost > 0 and m5 and str(m5[-1].get("day", ""))[11:16] >= "14:50":
        last_close = float(m5[-1]["close"])
        loss_pct = (last_close - cost) / cost * 100.0
        if loss_pct <= -STOP_SINGLE_PCT and sellable >= 100:
            signals.append({"action": "止损清仓", "price": last_close, "shares": sellable,
                            "reason": f"浮亏{loss_pct:.1f}%≥{STOP_SINGLE_PCT}%, 止损清仓", "time": str(m5[-1].get("day", ""))[11:16]})

    return signals, t0
