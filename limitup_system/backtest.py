# -*- coding: utf-8 -*-
"""
backtest.py — 回测引擎（诚实口径，不造数据）

  1. 打板隔日回测（文字①验证）
     形态日 T-1 收盘选出 → T 日开盘买入 → T+1 开盘卖出（隔日打板）
     T+1 合规。一字板（开盘=涨停价）跳过（买不进）。含印花税/佣金。
     注意：涨停日开盘买入的实际可成交性低于模型，胜率会高估 → 实盘扣5-10%。

  2. 昨收战法回测（文字②验证）
     A股 T+1：开盘买入当日不可卖 → 提供两个口径
       a) 开盘买→收盘卖（纯日内，仅统计参考，未实现底仓做T）
       b) 开盘买→次日开盘卖（T+1 合规，含隔夜风险）
     输出四态出现后的交易统计。

  所有指标：笔数/胜率/盈亏比/总收益/最大回撤/平均每笔。
"""
from __future__ import annotations

from statistics import mean
from typing import Any, Dict, List, Optional

from datafeed import attach_prev_close, fetch_daily_kline, is_limit_up, limit_pct
from screener import classify_prev_volume, score_signal
from strategy import classify_daily_state

COMMISSION = 0.00025   # 佣金万2.5（双边）
STAMP_TAX = 0.0005     # 印花税万5（卖出单边，2023后）


def _net(pnl_pct: float, sell: bool = True) -> float:
    """扣交易成本后的净收益%。"""
    cost = COMMISSION * 2 + (STAMP_TAX if sell else 0)
    return pnl_pct - cost * 100.0


def _max_drawdown(equity: List[float]) -> float:
    peak, mdd = -1e18, 0.0
    for v in equity:
        peak = max(peak, v)
        mdd = max(mdd, (peak - v) / peak if peak > 0 else 0)
    return mdd


def backtest_limitup(rows: List[Dict[str, Any]], code: str,
                     min_score: int = 50) -> Dict[str, Any]:
    """打板隔日回测：形态日(T-1)收盘评分 → T日开盘买入 → T+1开盘卖出。

    过滤：评分 < min_score 的不交易；一字板（T日开盘≈涨停价）跳过。
    """
    rows = attach_prev_close(rows)
    trades = []
    equity = [1.0]
    for idx in range(25, len(rows) - 2):
        sig = score_signal(rows, idx)          # T-1 形态评分
        if sig["type"] == "无形态":
            continue
        if sig["score"] < min_score:
            continue
        t = rows[idx + 1]                      # T 日
        t1 = rows[idx + 2]                     # T+1 日
        if t["open"] <= 0 or t1["open"] <= 0:
            continue
        # 一字板买不进：T日开盘 >= 涨停价-0.5%
        if is_limit_up(t, code, t["prev_close"]) and t["open"] >= t["close"] * 0.995:
            continue
        buy = t["open"]
        sell = t1["open"]
        pnl = (sell - buy) / buy * 100.0
        net = _net(pnl, sell=True)
        trades.append({
            "形态日": rows[idx]["day"], "形态": sig["type"], "评分": sig["score"],
            "买入日": t["day"], "买入价": round(buy, 2),
            "卖出日": t1["day"], "卖出价": round(sell, 2),
            "毛收益%": round(pnl, 2), "净收益%": round(net, 2),
        })
        equity.append(equity[-1] * (1 + net / 100.0))

    wins = [x for x in trades if x["净收益%"] > 0]
    gross = sum(x["毛收益%"] for x in trades)
    net_sum = sum(x["净收益%"] for x in trades)
    avg_win = mean(x["净收益%"] for x in wins) if wins else 0.0
    losses = [x for x in trades if x["净收益%"] <= 0]
    avg_loss = mean(x["净收益%"] for x in losses) if losses else 0.0

    # 按形态分组统计
    by_type: Dict[str, Dict[str, Any]] = {}
    for tr in trades:
        st = by_type.setdefault(tr["形态"], {"笔数": 0, "胜": 0, "净收益": 0.0})
        st["笔数"] += 1
        st["胜"] += 1 if tr["净收益%"] > 0 else 0
        st["净收益"] += tr["净收益%"]

    return {
        "code": code,
        "策略": "打板隔日（形态日T-1收盘选 → T开盘买 → T+1开盘卖）",
        "笔数": len(trades),
        "胜率%": round(len(wins) / len(trades) * 100, 1) if trades else 0.0,
        "盈亏比": round(avg_win / abs(avg_loss), 2) if avg_loss != 0 else None,
        "总收益%(复合)": round((equity[-1] - 1.0) * 100.0, 2),
        "平均每笔%": round(net_sum / len(trades), 2) if trades else 0.0,
        "最大回撤%": round(_max_drawdown(equity) * 100, 2),
        "按形态": {k: {**v, "胜率%": round(v["胜"] / v["笔数"] * 100, 1)}
                  for k, v in by_type.items()},
        "交易明细": trades[-20:],
    }


def backtest_prevclose(rows: List[Dict[str, Any]], code: str,
                        capital_model: bool = False) -> Dict[str, Any]:
    """昨收战法回测（四态统计 + 双口径模拟）。

    T日收盘判定四态 → 口径a: T+1开盘买收盘卖(纯日内参考)
                         口径b: T+1开盘买 → T+2开盘卖(T+1合规，隔夜)
    capital_model=True: 按半仓50%+手续费复合（与专业股数模型同资金约束的公平对比）
                        ——原版为满仓理想化，公平版才是可执行口径。
    """
    rows = attach_prev_close(rows)
    stats: Dict[str, Dict[str, Any]] = {}
    trades_a, trades_b = [], []
    equity_a, equity_b = [1.0], [1.0]
    HALF = 0.5 if capital_model else 1.0   # 公平版半仓（50%资金投入）

    for i in range(1, len(rows) - 2):
        st = classify_daily_state(rows[i])
        s = stats.setdefault(st, {"count": 0, "up_a": 0, "up_b": 0, "chgs": []})
        s["count"] += 1

        t1 = rows[i + 1]
        t2 = rows[i + 2]
        if t1["open"] <= 0 or t1["close"] <= 0 or t2["open"] <= 0:
            continue
        # 口径a：T+1 开盘买 → 收盘卖（纯日内参考）
        pnl_a = (t1["close"] - t1["open"]) / t1["open"] * 100.0
        net_a = _net(pnl_a, sell=True)
        trades_a.append({"形态日": rows[i]["day"], "形态": st, "净收益%": round(net_a, 2)})
        s["up_a"] += 1 if net_a > 0 else 0
        equity_a.append(equity_a[-1] * (1 + net_a * HALF / 100.0))

        # 口径b：T+1 开盘买 → T+2 开盘卖（T+1合规）
        pnl_b = (t2["open"] - t1["open"]) / t1["open"] * 100.0
        net_b = _net(pnl_b, sell=True)
        trades_b.append({"形态日": rows[i]["day"], "形态": st, "净收益%": round(net_b, 2)})
        s["up_b"] += 1 if net_b > 0 else 0
        s["chgs"].append(net_a)
        equity_b.append(equity_b[-1] * (1 + net_b * HALF / 100.0))

    def _summ(trades: List[Dict[str, Any]], equity: List[float]) -> Dict[str, Any]:
        wins = [x for x in trades if x["净收益%"] > 0]
        net_arith = sum(x["净收益%"] for x in trades)          # 算术和（诊断用）
        net_compound = (equity[-1] - 1.0) * 100.0 if equity else 0.0  # 真实复合
        avg_win = mean(x["净收益%"] for x in wins) if wins else 0.0
        losses = [x for x in trades if x["净收益%"] <= 0]
        avg_loss = mean(x["净收益%"] for x in losses) if losses else 0.0
        return {
            "笔数": len(trades),
            "胜率%": round(len(wins) / len(trades) * 100, 1) if trades else 0.0,
            "盈亏比": round(avg_win / abs(avg_loss), 2) if avg_loss != 0 else None,
            "总收益%(复合)": round(net_compound, 2),
            "平均每笔%(算术)": round(net_arith / len(trades), 2) if trades else 0.0,
        }

    return {
        "code": code,
        "说明": "四态统计：T日收盘四态 → 后续交易表现；A股T+1，口径b合规，口径a仅统计参考",
        "四态分布": {k: v["count"] for k, v in stats.items()},
        "形态统计": {k: {"出现天数": v["count"],
                       "日内胜率%(a)": round(v["up_a"] / v["count"] * 100, 1),
                       "隔夜胜率%(b)": round(v["up_b"] / v["count"] * 100, 1),
                       "日内平均净收益%": round(mean(v["chgs"]), 2) if v["chgs"] else 0}
                  for k, v in stats.items()},
        "口径a_日内": _summ(trades_a, equity_a),
        "口径b_隔夜T+1合规": _summ(trades_b, equity_b),
        "口径说明": "半仓50%+手续费复合(公平版)" if capital_model else "满仓理想化(原版)",
    }


def _vol_ma5(rows: List[Dict[str, Any]], idx: int) -> float:
    """第 idx 根前5日均量（不含当日）。"""
    if idx < 5:
        return 1.0
    return mean(r["volume"] for r in rows[idx - 5:idx])


def backtest_full_tactics(rows: List[Dict[str, Any]], code: str) -> Dict[str, Any]:
    """完整战法 2年回测（底仓 + T+0回转 + 加减仓，日K级近似，份数收益率模型）。

    ⚠️ 诚实近似声明：T+0 是日内行为，日K回测只能近似——
       - 先卖后买: 高开>2% 且 (high-close)≥(high-open)×0.5 且收在昨收上 → 冲高卖@high×0.995, 尾盘接回@close×0.995
       - 先买后卖: low≥昨收 且 收阳 → 低吸买@low×1.005, 冲高卖@high×0.995
       - 真实日内连续做T的收益通常高于此近似（日K只给了1次机会/日）

    模型: 昨日强势态收盘 → 今日建仓持有1份；持仓日每日底仓收益 + 做T差价(×0.3份)；
          加仓(低点不破+放量,+0.5份) / 减仓(放量长上影,-0.3份) / 清仓(close<昨收)。
    对比口径: backtest_prevclose 口径b（纯四态、开盘买次日卖，无做T/加减仓）。
    """
    rows = attach_prev_close(rows)
    pos = 0.0
    locked_today = 0.0        # ⭐ P1-1(2026-09-13): 今日买入份数（A股 T+1 当日不可卖）
    clear_pending = 0.0       # 已判清仓但被 T+1 锁定、待次日开盘执行的份数
    n_t0 = 0
    n_add = 0
    n_reduce = 0
    n_trades = 0          # 完整持仓周期数（建仓→清仓）
    t0_pnl = 0.0          # 做T累计收益%（相对份数）
    daily_ret: List[float] = []
    signals: List[Dict[str, Any]] = []  # 买卖信号序列（web K线图标注用）

    for i in range(1, len(rows)):
        r = rows[i]
        pc = r["prev_close"]
        if pc <= 0:
            continue
        # ── T+1 解锁：昨日买入今日可卖；昨日挂起的清仓在今日开盘执行 ──
        locked_today = 0.0
        if clear_pending > 0:
            pos = max(0.0, pos - clear_pending)
            signals.append({"day": r["day"], "action": "清仓(T+1次日)", "price": round(r["open"], 2),
                            "type": "sell", "note": "T+1：前一日判清仓但当日锁定，次日开盘卖出"})
            clear_pending = 0.0
        y = rows[i - 1]
        y_state = classify_daily_state(y)
        chg = (r["close"] - pc) / pc * 100.0
        day_ret = 0.0

        # 建仓：昨日强势态 且 空仓
        if y_state == "强势" and pos <= 0:
            pos = 1.0
            locked_today += 1.0        # T+1: 当日买入锁定
            n_trades += 1
            signals.append({"day": r["day"], "action": "建仓", "price": round(r["open"], 2), "type": "buy"})

        if pos > 0:
            day_ret += pos * chg
            # ---- T+0 回转（评审修正2: 振幅≥3%才做T，做T目标≥1%差价）----
            amp = (r["high"] - r["low"]) / pc * 100.0
            gap = (r["open"] - pc) / pc * 100.0
            rise = (r["high"] - r["open"]) / pc * 100.0
            drop = (r["high"] - r["close"]) / pc * 100.0
            t0_ret = 0.0
            if amp >= 3.0 and gap > 2.0 and rise > 0 and drop >= rise * 0.5 and r["close"] > pc:
                # 先卖后买：高开冲高回落 → 冲高卖0.3份，尾盘接回
                t0_ret = (r["high"] * 0.995 - r["close"] * 0.995) / pc * 100.0 * 0.3
                n_t0 += 1
                signals.append({"day": r["day"], "action": "T0卖(高抛)", "price": round(r["high"] * 0.995, 2), "type": "sell"})
            elif amp >= 3.0 and r["low"] >= pc * 0.998 and r["close"] > r["open"]:
                # 先买后卖：回踩不破低吸 → 低吸买0.3份，冲高卖
                t0_ret = (r["high"] * 0.995 - r["low"] * 1.005) / pc * 100.0 * 0.3
                n_t0 += 1
                signals.append({"day": r["day"], "action": "T0买(低吸)", "price": round(r["low"] * 1.005, 2), "type": "buy"})
            t0_pnl += t0_ret
            day_ret += t0_ret
            # ---- 加减仓 ----
            vma = _vol_ma5(rows, i)
            # 总暴露≤70%（1份≈50%仓，加仓上限1.4份）
            if r["low"] >= pc * 0.998 and vma > 0 and r["volume"] > vma * 1.5 and pos < 1.4:
                pos += 0.5
                n_add += 1
                signals.append({"day": r["day"], "action": "加仓", "price": round(r["close"], 2), "type": "add"})
            upper = (r["high"] - max(r["open"], r["close"])) / pc * 100.0
            body = abs(r["close"] - r["open"]) / pc * 100.0
            if upper >= 1.5 and upper >= body and vma > 0 and r["volume"] > vma * 1.2 and pos > 0.3:
                pos -= 0.3
                n_reduce += 1
                signals.append({"day": r["day"], "action": "减仓", "price": round(r["high"] * 0.995, 2), "type": "reduce"})
            # ---- 清仓：跌破昨收（日K近似15分钟不收回）----
                if r["close"] < pc:
                    # ⭐ P1-1(2026-09-13): A股 T+1——只卖可卖份数，当日新买的份数次日开盘执行（原实现直接 pos=0 当日清仓）
                    _sellable = max(0.0, pos - locked_today)
                    if _sellable > 0:
                        signals.append({"day": r["day"], "action": "清仓", "price": round(r["close"], 2), "type": "sell"})
                    if locked_today > 0:
                        clear_pending = locked_today
                    pos = pos - _sellable

        daily_ret.append(day_ret)

    equity = [1.0]
    for ret in daily_ret:
        equity.append(equity[-1] * (1 + ret / 100.0))
    wins = sum(1 for x in daily_ret if x > 0)
    total = (equity[-1] - 1.0) * 100.0

    # 对照：纯四态口径b（来自 backtest_prevclose）
    base = backtest_prevclose(rows, code)
    base_b = base["口径b_隔夜T+1合规"]

    return {
        "code": code,
        "daily_ret": daily_ret,
        "signals": signals,
        "完整战法(底仓+做T+加减仓)": {
            "总收益%(复合)": round(total, 2),
            "日胜率%": round(wins / len(daily_ret) * 100, 1) if daily_ret else 0.0,
            "最大回撤%": round(_max_drawdown(equity) * 100, 2),
            "做T次数": n_t0,
            "做T累计收益%": round(t0_pnl, 2),
            "加仓次数": n_add,
            "减仓次数": n_reduce,
            "持仓周期数": n_trades,
            "年化%(近似)": round((total / (len(rows) / 250)) if len(rows) else 0, 2),
        },
        "对照_纯四态口径b": {
            "总收益%(复合)": base_b.get("总收益%(复合)"),
            "胜率%": base_b.get("胜率%"),
            "笔数": base_b.get("笔数"),
        },
        "诚实声明": "T+0为日K级近似（每日最多1次回转机会）；真实日内连续做T收益通常更高；结果受单只标的影响大",
    }


def compute_positions(rows: List[Dict[str, Any]]) -> Dict[str, str]:
    """用现有日K计算每日位置（不增加指标）：高位=20日涨幅>30% 或 距60日高点<5%；低位=60日回撤≥15%且20日涨幅<10%；否则中途。"""
    positions: Dict[str, str] = {}
    for i in range(len(rows)):
        day = rows[i]["day"]
        if i < 20:
            positions[day] = "中途"
            continue
        j60 = max(0, i - 59)
        win60 = rows[j60:i + 1]
        hi60 = max(r["high"] for r in win60)
        close = rows[i]["close"]
        dist = (hi60 - close) / hi60 if hi60 else 0.0
        j20 = max(0, i - 20)
        p0 = rows[j20]["close"]
        ret20 = (close - p0) / p0 if p0 else 0.0
        if ret20 > 0.30 or dist < 0.05:
            positions[day] = "高位"
        elif dist >= 0.15 and ret20 < 0.10:
            positions[day] = "低位"
        else:
            positions[day] = "中途"
    return positions


def backtest_full_realtime(rows: List[Dict[str, Any]], min5_by_day: Dict[str, List[Dict[str, Any]]],
                            code: str, params: Optional[Dict[str, Any]] = None,
                            env_series: Optional[Dict[str, int]] = None,
                            position_filter: bool = False) -> Dict[str, Any]:
    """严格还原原文实时逻辑（老陈 2026-08-08 核心修正：所有操作=当前实时价 vs 昨收）。

    ⚠️ 无未来函数：不用全天high/low判定盘中动作，全部用5分钟K逐根推进：
      开盘3分钟: 前3根5分K收盘 vs 昨收 → 全站上=强开(可建仓) / 全压制=弱开 / 混合=震荡
      15分钟有效: 连续3根5分K收<昨收=有效破位(清仓)；连续3根收>昨收=有效站稳(弱转强低吸)
      弱转强: 当日曾跌破昨收 → 连续3根5分K收回站稳 → 低吸建仓（原文"10分钟内快速收回"）
      T+0: 高开>2% 且 冲高(5分K实时高点)回落超一半 → 卖；5分K低点不破昨收 且 收阳 → 买
      加仓: 回踩不破 + 5分K放量(>前5根均量×1.5) → +0.5份；减仓: 5分K放量长上影 → -0.3份
    无分钟数据日 → 日K近似兜底（5min 覆盖约1.75年）。
    收益: 底仓=当日收盘涨跌×份数；做T=实时分钟成交差价×0.3份；复合、含费近似。
    """
    params = params or {}
    HOLD_MIN = int(params.get("hold_min", 3))          # 15分钟有效 = 连续N根5分K
    T0_GAP = float(params.get("t0_gap_pct", 2.0))      # T0先卖后买: 高开阈值%
    T0_AMP = float(params.get("t0_amp_pct", 3.0))      # 做T振幅门槛%
    T0_DROP = float(params.get("t0_drop_ratio", 0.5))  # 冲高回落超一半比例
    ADD_VOL = float(params.get("add_vol", 1.5))        # 加仓放量倍数
    REDUCE_VOL = float(params.get("reduce_vol", 1.2))  # 减仓放量倍数

    rows = attach_prev_close(rows)
    positions = compute_positions(rows) if position_filter else {}
    pos = 0.0          # 总持仓（份，1份=5万）
    locked = 0.0       # 今日买入（T+1锁定，当日不可卖）；可卖 = pos - locked
    cost_total = 0.0   # 持仓成本金额（均价法，元）
    n_t0 = 0
    n_add = 0
    n_reduce = 0
    n_trades = 0
    t0_pnl = 0.0
    daily_ret: List[float] = []
    signals: List[Dict[str, Any]] = []
    min_covered = 0
    env_bad_days = 0
    clear_pending = 0.0  # T+1: 清仓日锁定的部分，次日开盘卖出
    cum_asset = INIT_CAPITAL  # 累计资产（元）

    for i in range(1, len(rows)):
        r = rows[i]
        pc = r["prev_close"]
        if pc <= 0:
            continue
        y = rows[i - 1]
        y_state = classify_daily_state(y)
        chg = (r["close"] - pc) / pc * 100.0
        day_ret = 0.0
        m5 = min5_by_day.get(r["day"], [])
        # T+1 解锁: 昨日买入今日可卖；昨日清仓锁定的部分今日开盘卖出
        locked = 0.0
        if clear_pending > 0:
            pos -= clear_pending
            cost_total = 0.0
            cum_asset *= (1.0 + chg / 100.0)
            signals.append({"day": r["day"], "action": "清仓(T+1次日)", "price": round(r["open"], 2), "type": "sell",
                            "shares": round(clear_pending, 2), "amount": round(clear_pending * UNIT_VALUE, 0),
                            "pnl": 0.0, "pnl_amount": 0.0, "hold_after": round(pos, 2),
                            "asset_after": round(cum_asset, 0)})
            clear_pending = 0.0

        if m5:
            min_covered += 1
            # ── 开盘3分钟定强弱（前3根5分K vs 昨收）──
            open_strong = len(m5) >= 3 and all(k["close"] > pc for k in m5[:3])
            # ── 建仓：昨日强势(日K收盘) + 开盘3分钟站稳 → 价=第3根5分K收盘 ──
            # ②位置过滤: 高位回踩不破≠低吸（原文误区2: 高位大涨后是出货陷阱，不建仓）
            # ③环境过滤: 大盘跌破昨收日禁止新开仓（原文: 系统性下跌时信号失效）
            pos_ok = True
            # ②位置过滤: 高位禁【弱转强低吸】(跌破收回=出货陷阱)；强势延续建仓不禁(强者恒强)
            # ③环境过滤: 大盘跌破昨收日禁止新开仓
            if env_series and env_series.get(r["day"], 1) < 0:
                env_bad_days += 1
                pos_ok = False
            if y_state == "强势" and pos <= 0 and open_strong and pos_ok:
                buy_p = m5[2]["close"]
                pos = 1.0
                locked += 1.0            # T+1: 今日建仓当日锁定
                cost_total = buy_p * 1.0
                n_trades += 1
                signals.append({"day": r["day"], "action": "建仓", "price": round(buy_p, 2), "type": "buy",
                                "shares": 1.0, "amount": round(1.0 * UNIT_VALUE, 0),
                                "pnl": 0.0, "pnl_amount": 0.0, "hold_after": round(pos, 2),
                                "asset_after": round(cum_asset, 0)})

            if pos > 0:
                day_ret += pos * chg   # 底仓收益（realtime 曾漏算，已修）
                # ── 持仓：逐根推进找有效破位（连续3根5分K收<昨收=15分钟有效）──
                below_streak = 0
                broke = None
                live_stop = None   # ⭐ 2026-08-13 盘中止损: 浮亏≥5% 且 连续3根5分K收<昨收 → 立即止损
                for k in m5:
                    if k["close"] < pc:
                        below_streak += 1
                        if below_streak >= HOLD_MIN:
                            broke = k
                            break
                        # 盘中止损(同步 auto_trader/_tick_stock): 浮亏≥5% + 已连续3根跌破昨收
                        if below_streak >= 3:
                            avg_cost_c = cost_total / pos if pos > 0 else pc
                            if avg_cost_c > 0 and (k["close"] - avg_cost_c) / avg_cost_c * 100.0 <= -5.0:
                                live_stop = k   # 盘中即止损, 不等 5根/尾盘9%
                                break
                    else:
                        below_streak = 0
                else:
                    below_streak = 0
                if live_stop:
                    broke = live_stop
                if broke:
                    # T+1: 清仓=卖出可卖部分(pos-locked)；锁定部分次日开盘卖
                    sellable = pos - locked
                    sell_p = broke["close"]
                    if sellable > 0:
                        avg_cost = cost_total / pos if pos > 0 else sell_p
                        pnl_pct = (sell_p - avg_cost) / avg_cost * 100.0 if avg_cost else 0.0
                        pos -= sellable
                        cost_total -= avg_cost * sellable
                        signals.append({"day": r["day"], "action": "清仓", "price": round(sell_p, 2), "type": "sell",
                                        "shares": round(sellable, 2), "amount": round(sellable * UNIT_VALUE, 0),
                                        "pnl": round(pnl_pct, 2),
                                        "pnl_amount": round(sellable * UNIT_VALUE * pnl_pct / 100.0, 0),
                                        "hold_after": round(pos, 2), "asset_after": round(cum_asset, 0)})
                    if pos > 0:
                        clear_pending = pos
                        pos = 0.0
                else:
                    # ── 未破位 → T+0（5分K实时轨迹；T+1: 卖只卖底仓，买的部分当日锁定）──
                    max_high = max(k["high"] for k in m5)
                    min_low = min(k["low"] for k in m5)
                    amp = (max_high - min_low) / pc * 100.0
                    first = m5[0]
                    gap = (first["open"] - pc) / pc * 100.0
                    t0_ret = 0.0
                    sellable = pos - locked
                    avg_cost = cost_total / pos if pos > 0 else 0.0
                    # 先卖后买：高开>2% 且 冲高回落超一半 且 尾盘收在昨收上（卖底仓0.3份，尾盘接回锁定）
                    if amp >= T0_AMP and gap > T0_GAP and m5[-1]["close"] > pc and sellable >= 0.3:
                        rise = (max_high - first["open"]) / pc * 100.0
                        drop = (max_high - m5[-1]["close"]) / pc * 100.0
                        if rise > 0 and drop >= rise * T0_DROP:
                            sell_p = max_high * 0.998
                            buy_p = m5[-1]["close"]
                            t0_ret = (sell_p - buy_p) / pc * 100.0 * 0.3
                            n_t0 += 1
                            pos -= 0.3
                            cost_total -= avg_cost * 0.3
                            pos += 0.3
                            locked += 0.3
                            cost_total += buy_p * 0.3
                            signals.append({"day": r["day"], "action": "T0卖(高抛)", "price": round(sell_p, 2), "type": "sell",
                                            "shares": 0.3, "amount": round(0.3 * UNIT_VALUE, 0),
                                            "pnl": round((sell_p - avg_cost) / avg_cost * 100.0, 2) if avg_cost else 0.0,
                                            "pnl_amount": round(0.3 * UNIT_VALUE * (sell_p - avg_cost) / avg_cost, 0) if avg_cost else 0.0,
                                            "hold_after": round(pos, 2), "asset_after": round(cum_asset, 0)})
                    # 先买后卖：5分K低点不破昨收 且 收阳（买0.3锁定，卖等量底仓0.3——T+1合规）
                    elif amp >= T0_AMP and min_low >= pc * 0.998 and m5[-1]["close"] > m5[0]["open"] and sellable >= 0.3:
                        low_k = min(m5, key=lambda k: k["low"])
                        buy_p = low_k["low"] * 1.002
                        sell_p = max_high * 0.998
                        t0_ret = (sell_p - buy_p) / pc * 100.0 * 0.3
                        n_t0 += 1
                        pos += 0.3
                        locked += 0.3
                        cost_total += buy_p * 0.3
                        pos -= 0.3
                        cost_total -= avg_cost * 0.3
                        signals.append({"day": r["day"], "action": "T0买(低吸)", "price": round(buy_p, 2), "type": "buy",
                                        "shares": 0.3, "amount": round(0.3 * UNIT_VALUE, 0),
                                        "pnl": round((sell_p - buy_p) / buy_p * 100.0, 2),
                                        "pnl_amount": round(0.3 * UNIT_VALUE * (sell_p - buy_p) / buy_p, 0),
                                        "hold_after": round(pos, 2), "asset_after": round(cum_asset, 0)})
                    t0_pnl += t0_ret
                    day_ret += t0_ret
                    # 加仓：回踩不破 + 5分K放量；⚠️ T+1: 加仓量≤可卖底仓1/2，加仓部分当日锁定
                    vols = [k["volume"] for k in m5]
                    sellable = pos - locked
                    if min_low >= pc * 0.998 and len(vols) >= 6 and vma_ok(vols, ADD_VOL) and sellable >= 0.4:
                        add_qty = min(0.5, sellable * 0.5)
                        pos += add_qty
                        locked += add_qty
                        cost_total += m5[-1]["close"] * add_qty
                        n_add += 1
                        signals.append({"day": r["day"], "action": "加仓", "price": round(m5[-1]["close"], 2), "type": "add",
                                        "shares": round(add_qty, 2), "amount": round(add_qty * UNIT_VALUE, 0),
                                        "pnl": 0.0, "pnl_amount": 0.0, "hold_after": round(pos, 2),
                                        "asset_after": round(cum_asset, 0)})
                    # 减仓：5分K放量长上影；⚠️ T+1: 只减可卖底仓，减仓量≤底仓1/2
                    last_k = m5[-1]
                    upper = (last_k["high"] - max(last_k["open"], last_k["close"])) / pc * 100.0
                    sellable = pos - locked
                    if upper >= 1.5 and len(vols) >= 6 and vma_ok(vols, REDUCE_VOL) and sellable >= 0.35:
                        reduce_qty = min(0.3, sellable * 0.5)
                        pos -= reduce_qty
                        cost_total -= avg_cost * reduce_qty
                        n_reduce += 1
                        signals.append({"day": r["day"], "action": "减仓", "price": round(last_k["high"] * 0.998, 2), "type": "reduce",
                                        "shares": round(reduce_qty, 2), "amount": round(reduce_qty * UNIT_VALUE, 0),
                                        "pnl": round((last_k["high"] * 0.998 - avg_cost) / avg_cost * 100.0, 2) if avg_cost else 0.0,
                                        "pnl_amount": round(reduce_qty * UNIT_VALUE * (last_k["high"] * 0.998 - avg_cost) / avg_cost, 0) if avg_cost else 0.0,
                                        "hold_after": round(pos, 2), "asset_after": round(cum_asset, 0)})
            else:
                # ── 持币：弱转强低吸（当日曾跌破昨收 → 连续3根5分K收回站稳）──
                below_seen = False
                above_streak = 0
                pos_ok = True
                if position_filter and positions.get(r["day"]) == "高位":
                    pos_ok = False
                if env_series and env_series.get(r["day"], 1) < 0:
                    pos_ok = False
                for j, k in enumerate(m5):
                    if k["close"] < pc:
                        below_seen = True
                        above_streak = 0
                    else:
                        above_streak += 1
                        if above_streak >= HOLD_MIN and below_seen and pos_ok:
                            buy_p = k["close"]
                            pos = 1.0
                            locked += 1.0            # T+1: 当日锁定
                            cost_total = buy_p * 1.0
                            n_trades += 1
                            signals.append({"day": r["day"], "action": "弱转强低吸", "price": round(buy_p, 2), "type": "buy",
                                            "shares": 1.0, "amount": round(1.0 * UNIT_VALUE, 0),
                                            "pnl": 0.0, "pnl_amount": 0.0, "hold_after": round(pos, 2),
                                            "asset_after": round(cum_asset, 0)})
                            break
        else:
            # ── 无分钟数据日 → 日K近似兜底 ──
            amp = (r["high"] - r["low"]) / pc * 100.0
            gap = (r["open"] - pc) / pc * 100.0
            rise = (r["high"] - r["open"]) / pc * 100.0
            drop = (r["high"] - r["close"]) / pc * 100.0
            t0_ret = 0.0
            if y_state == "强势" and pos <= 0:
                buy_p = r["open"]
                pos = 1.0
                locked += 1.0
                cost_total = buy_p * 1.0
                n_trades += 1
                signals.append({"day": r["day"], "action": "建仓(兜底)", "price": round(buy_p, 2), "type": "buy",
                                "shares": 1.0, "amount": round(1.0 * UNIT_VALUE, 0),
                                "pnl": 0.0, "pnl_amount": 0.0, "hold_after": round(pos, 2),
                                "asset_after": round(cum_asset, 0)})
            if pos > 0:
                day_ret += pos * chg
                if amp >= 3.0 and gap > 2.0 and rise > 0 and drop >= rise * 0.5 and r["close"] > pc:
                    t0_ret = (r["high"] * 0.995 - r["close"] * 0.995) / pc * 100.0 * 0.3
                    n_t0 += 1
                elif amp >= 3.0 and r["low"] >= pc * 0.998 and r["close"] > r["open"]:
                    t0_ret = (r["high"] * 0.995 - r["low"] * 1.005) / pc * 100.0 * 0.3
                    n_t0 += 1
                t0_pnl += t0_ret
                day_ret += t0_ret
                vma = _vol_ma5(rows, i)
                if r["low"] >= pc * 0.998 and vma > 0 and r["volume"] > vma * 1.5 and pos < 1.4:
                    pos += 0.5
                    n_add += 1
                upper = (r["high"] - max(r["open"], r["close"])) / pc * 100.0
                body = abs(r["close"] - r["open"]) / pc * 100.0
                if upper >= 1.5 and upper >= body and vma > 0 and r["volume"] > vma * 1.2 and pos > 0.3:
                    pos -= 0.3
                    n_reduce += 1
                if r["close"] < pc:
                    avg_cost = cost_total / pos if pos > 0 else r["close"]
                    pnl_pct = (r["close"] - avg_cost) / avg_cost * 100.0 if avg_cost else 0.0
                    qty = pos
                    pos = 0.0
                    cost_total = 0.0
                    signals.append({"day": r["day"], "action": "清仓", "price": round(r["close"], 2), "type": "sell",
                                    "shares": round(qty, 2), "amount": round(qty * UNIT_VALUE, 0),
                                    "pnl": round(pnl_pct, 2),
                                    "pnl_amount": round(qty * UNIT_VALUE * pnl_pct / 100.0, 0),
                                    "hold_after": 0.0, "asset_after": round(cum_asset, 0)})

        daily_ret.append(day_ret)

    equity = [1.0]
    for ret in daily_ret:
        equity.append(equity[-1] * (1 + ret / 100.0))
    wins = sum(1 for x in daily_ret if x > 0)
    total = (equity[-1] - 1.0) * 100.0

    base = backtest_prevclose(rows, code)
    base_b = base["口径b_隔夜T+1合规"]

    return {
        "code": code,
        "daily_ret": daily_ret,
        "signals": signals,
        "完整战法(实时5分)": {
            "总收益%(复合)": round(total, 2),
            "日胜率%": round(wins / len(daily_ret) * 100, 1) if daily_ret else 0.0,
            "最大回撤%": round(_max_drawdown(equity) * 100, 2),
            "做T次数": n_t0,
            "做T累计收益%": round(t0_pnl, 2),
            "加仓次数": n_add,
            "减仓次数": n_reduce,
            "持仓周期数": n_trades,
            "年化%(近似)": round((total / (len(rows) / 250)) if len(rows) else 0, 2),
            "分钟覆盖天数": min_covered,
            "初始资金": round(INIT_CAPITAL, 0),
            "期末资产": round(INIT_CAPITAL * (1 + total / 100.0), 0),
            "收益金额": round(INIT_CAPITAL * total / 100.0, 0),
        },
        "对照_纯四态口径b": {
            "总收益%(复合)": base_b.get("总收益%(复合)"),
            "胜率%": base_b.get("胜率%"),
            "笔数": base_b.get("笔数"),
        },
        "诚实声明": "实时5分回测：5分钟K逐根判定(开盘3分钟/15分钟有效/弱转强/T+0实时轨迹)，无未来函数；T+1合规(当日买入锁定次日可卖)；加减仓≤底仓1/2；1份=5万(初始资金10万)；5min覆盖约1.75年，超出走日K兜底",
    }


def backtest_full_minute(rows: List[Dict[str, Any]], min15_by_day: Dict[str, List[Dict[str, Any]]],
                          code: str, clear_below_bars: int = 1) -> Dict[str, Any]:
    """分钟级严格回测（老陈 2026-08-07: 用15分钟K严格判断，回测才真实）。

    与 backtest_full_tactics 相同的仓位/收益模型，但信号判定全部用当日15分钟K：
      - 建仓: 昨日强势 + 首根15分K收>昨收 → 建仓价=首根15分K收盘（同确认时点，避免偷看）
      - 清仓: 当日15分K收盘<昨收（15分钟有效跌破）→ 该根收清仓
      - T+0先卖后买: 首根高开>2% 且 从最高回落超一半 → 卖=冲高根high×0.998, 接回=尾盘close
      - T+0先买后卖: 15分K低点≥昨收 且 收阳 → 买=低点根low×1.002, 卖=冲高根high×0.998
      - 加仓: 回踩不破 + 15分K放量(量>前5根均量×1.5) → +0.5份
      - 减仓: 15分K放量长上影(≥1.5%) → -0.3份
    无分钟数据日 → 日K近似兜底（min15 覆盖1.5年）。
    收益: 底仓=当日收盘涨跌×份数；做T=真实分钟成交差价×0.3份；复合、含费近似。
    """
    rows = attach_prev_close(rows)
    # ⭐ P1-2a(2026-09-13): 离场容忍根数——原实现"任一根15分K收盘<昨收 → 清仓"过于敏感
    #   (300319 实测: 46 天覆盖内 106 笔, 大量"今天买、次日清")。连续 N 根收<昨收才算有效跌破。
    #   默认 1 = 保持原行为（须 A/B 验证后才考虑改默认；由调用方传参，保持函数向后兼容）。
    CLEAR_BARS_MIN = max(1, int(clear_below_bars or 1))
    pos = 0.0                 # 总持仓（份数）
    locked_today = 0.0        # 今日买入份数（A股 T+1：当日不可卖）
    clear_pending = 0.0       # 已判清仓但受 T+1 锁定，待次日开盘执行的份数
    n_t0 = 0
    n_add = 0
    n_reduce = 0
    n_trades = 0
    t0_pnl = 0.0
    daily_ret: List[float] = []
    signals: List[Dict[str, Any]] = []
    min_covered = 0

    for i in range(1, len(rows)):
        r = rows[i]
        pc = r["prev_close"]
        if pc <= 0:
            continue
        # ── T+1 解锁：昨日买入份数今日可卖；昨日挂起的清仓在今日开盘执行 ──
        locked_today = 0.0
        if clear_pending > 0:
            pos = max(0.0, pos - clear_pending)
            signals.append({"day": r["day"], "action": "清仓(T+1次日)", "price": round(r["open"], 2),
                            "type": "sell", "note": "T+1：前一日判清仓但当日锁定，次日开盘卖出"})
            clear_pending = 0.0
        y = rows[i - 1]
        y_state = classify_daily_state(y)
        chg = (r["close"] - pc) / pc * 100.0
        day_ret = 0.0
        m15 = min15_by_day.get(r["day"], [])

        # 建仓：昨日强势态 且 空仓（首根15分K收>昨收 才建；无分钟数据用日K兜底）
        if y_state == "强势" and pos <= 0:
            ok = True
            price = r["open"]
            if m15:
                if m15[0]["close"] > pc:
                    # ⚠️ 确认条件用首根15分K收盘 → 成交价必须同一时点(首根收盘)；
                    #    原实现按该根【开盘价】成交 = 用未知信息定价（偷看），已修
                    price = m15[0]["close"]
                else:
                    ok = False
            if ok:
                pos = 1.0
                locked_today += 1.0        # T+1：当日买入锁定
                n_trades += 1
                signals.append({"day": r["day"], "action": "建仓", "price": round(price, 2), "type": "buy"})

        if pos > 0:
            day_ret += pos * chg
            if m15:
                min_covered += 1
                min_low = min(k["low"] for k in m15)
                max_high = max(k["high"] for k in m15)
                amp = (max_high - min_low) / pc * 100.0
                # 清仓：15分钟有效跌破（当日任一根15分K收盘<昨收）
                # P1-2a: 连续 CLEAR_BARS_MIN 根收<昨收才算有效跌破（默认1=原行为）
                broke, _bs = None, 0
                for _k in m15:
                    if _k["close"] < pc:
                        _bs += 1
                        if _bs >= CLEAR_BARS_MIN:
                            broke = _k
                            break
                    else:
                        _bs = 0
                if broke:
                    sellable = max(0.0, pos - locked_today)      # T+1：只可卖昨日及更早份数
                    if sellable > 0:
                        signals.append({"day": r["day"], "action": "清仓", "price": round(broke["close"], 2),
                                        "type": "sell"})
                    if locked_today > 0:
                        clear_pending = locked_today             # 当日新买部分次日开盘卖
                    pos = pos - sellable                          # 被锁定份数过夜，由次日开盘执行
                else:
                    first = m15[0]
                    gap = (first["open"] - pc) / pc * 100.0
                    t0_ret = 0.0
                    # T+0先卖后买：首根高开>2% 且 冲高回落超一半 且 尾盘收在昨收上
                    if amp >= 3.0 and gap > 2.0 and m15[-1]["close"] > pc and (pos - locked_today) >= 0.3:
                        rise = (max_high - first["open"]) / pc * 100.0
                        drop = (max_high - m15[-1]["close"]) / pc * 100.0
                        if rise > 0 and drop >= rise * 0.5:
                            sell_p = max_high * 0.998
                            buy_p = m15[-1]["close"]
                            t0_ret = (sell_p - buy_p) / pc * 100.0 * 0.3
                            n_t0 += 1
                            signals.append({"day": r["day"], "action": "T0卖(高抛)", "price": round(sell_p, 2), "type": "sell"})
                    # T+0先买后卖：15分低点不破昨收 且 收阳
                    elif amp >= 3.0 and min_low >= pc * 0.998 and m15[-1]["close"] > m15[0]["open"]:
                        low_k = min(m15, key=lambda k: k["low"])
                        buy_p = low_k["low"] * 1.002
                        sell_p = max_high * 0.998
                        t0_ret = (sell_p - buy_p) / pc * 100.0 * 0.3
                        n_t0 += 1
                        signals.append({"day": r["day"], "action": "T0买(低吸)", "price": round(buy_p, 2), "type": "buy"})
                    t0_pnl += t0_ret
                    day_ret += t0_ret
                    # 加仓：回踩不破 + 15分放量（最后根量>前5根均量×1.5）
                    vols = [k["volume"] for k in m15]
                    if min_low >= pc * 0.998 and len(vols) >= 6 and vma_ok(vols, 1.5) and pos < 1.4:
                        pos += 0.5
                        n_add += 1
                        signals.append({"day": r["day"], "action": "加仓", "price": round(m15[-1]["close"], 2), "type": "add"})
                    # 减仓：15分放量长上影
                    last_k = m15[-1]
                    upper = (last_k["high"] - max(last_k["open"], last_k["close"])) / pc * 100.0
                    if upper >= 1.5 and len(vols) >= 6 and vma_ok(vols, 1.2) and (pos - locked_today) > 0.3:
                        pos -= 0.3
                        n_reduce += 1
                        signals.append({"day": r["day"], "action": "减仓", "price": round(last_k["high"] * 0.998, 2), "type": "reduce"})
            else:
                # 无分钟数据日 → 日K近似兜底（同 backtest_full_tactics 逻辑）
                amp = (r["high"] - r["low"]) / pc * 100.0
                gap = (r["open"] - pc) / pc * 100.0
                rise = (r["high"] - r["open"]) / pc * 100.0
                drop = (r["high"] - r["close"]) / pc * 100.0
                t0_ret = 0.0
                if amp >= 3.0 and gap > 2.0 and rise > 0 and drop >= rise * 0.5 and r["close"] > pc:
                    t0_ret = (r["high"] * 0.995 - r["close"] * 0.995) / pc * 100.0 * 0.3
                    n_t0 += 1
                elif amp >= 3.0 and r["low"] >= pc * 0.998 and r["close"] > r["open"]:
                    t0_ret = (r["high"] * 0.995 - r["low"] * 1.005) / pc * 100.0 * 0.3
                    n_t0 += 1
                t0_pnl += t0_ret
                day_ret += t0_ret
                vma = _vol_ma5(rows, i)
                if r["low"] >= pc * 0.998 and vma > 0 and r["volume"] > vma * 1.5 and pos < 1.4:
                    pos += 0.5
                    n_add += 1
                    signals.append({"day": r["day"], "action": "加仓", "price": round(r["close"], 2), "type": "add"})
                upper = (r["high"] - max(r["open"], r["close"])) / pc * 100.0
                body = abs(r["close"] - r["open"]) / pc * 100.0
                if upper >= 1.5 and upper >= body and vma > 0 and r["volume"] > vma * 1.2 and (pos - locked_today) > 0.3:
                    pos -= 0.3
                    n_reduce += 1
                if r["close"] < pc:
                    sellable = max(0.0, pos - locked_today)
                    if sellable > 0:
                        signals.append({"day": r["day"], "action": "清仓", "price": round(r["close"], 2), "type": "sell"})
                    if locked_today > 0:
                        clear_pending = locked_today
                    pos = pos - sellable

        daily_ret.append(day_ret)

    equity = [1.0]
    for ret in daily_ret:
        equity.append(equity[-1] * (1 + ret / 100.0))
    wins = sum(1 for x in daily_ret if x > 0)
    total = (equity[-1] - 1.0) * 100.0

    base = backtest_prevclose(rows, code)
    base_b = base["口径b_隔夜T+1合规"]

    return {
        "code": code,
        "daily_ret": daily_ret,
        "signals": signals,
        "完整战法(分钟级严格)": {
            "总收益%(复合)": round(total, 2),
            "日胜率%": round(wins / len(daily_ret) * 100, 1) if daily_ret else 0.0,
            "最大回撤%": round(_max_drawdown(equity) * 100, 2),
            "做T次数": n_t0,
            "做T累计收益%": round(t0_pnl, 2),
            "加仓次数": n_add,
            "减仓次数": n_reduce,
            "持仓周期数": n_trades,
            "年化%(近似)": round((total / (len(rows) / 250)) if len(rows) else 0, 2),
            "分钟覆盖天数": min_covered,
        },
        "对照_纯四态口径b": {
            "总收益%(复合)": base_b.get("总收益%(复合)"),
            "胜率%": base_b.get("胜率%"),
            "笔数": base_b.get("笔数"),
        },
        "诚实声明": "分钟级严格回测：15分K判定破位/做T/买卖点（覆盖约1.5年）；无分钟数据日走日K近似兜底",
    }


INIT_CAPITAL = 100000.0   # 初始资金 10万（老陈 2026-08-08）
UNIT_VALUE = 50000.0      # 1份 = 5万（建仓1份≈50%资金）


def trend_state_by_day(rows: List[Dict[str, Any]]) -> Dict[str, str]:
    """日K趋势状态机（老陈 2026-08-09: 战法缺短期趋势维度）。

    ⚠️ 比 MA20/60 快：用 MA10/MA20 + 收盘位置判定，避免 MA20/60 滞后
    （300319 2026-03 大跌被误判 up / 2026-07 大涨被误判 down 的教训）。

    状态:
      up    = 昨日收盘 > MA10 且 MA10 > MA20（多头排列, 上升）
      down  = 昨日收盘 < MA10 且 MA10 < MA20（空头排列, 下降）
      range = 其它（围绕均线穿越, 震荡）

    ⚠️ 无未来函数：判定用【昨日】收盘 vs 【截止昨日】的 MA10/MA20——
    今日开盘 3 分钟决策时点只知道昨日数据（老陈 2026-08-08 核心原则: 实时价 vs 已知价）。
    返回 {day_str: state}，前 21 根不足均线 → range。
    """
    closes = [r["close"] for r in rows]
    states: Dict[str, str] = {}
    for i in range(1, len(rows)):
        d = rows[i]["day"]
        if i < 21:
            states[d] = "range"
            continue
        # 昨日时点: 昨日收盘 + 截止昨日的均线（今日决策时已知）
        px_prev = closes[i-1]
        ma10 = sum(closes[i-11:i-1]) / 10
        ma20 = sum(closes[i-21:i-1]) / 20
        if px_prev > ma10 and ma10 > ma20:
            states[d] = "up"
        elif px_prev < ma10 and ma10 < ma20:
            states[d] = "down"
        else:
            states[d] = "range"
    return states


def _trend_target_amount(state: str, base: float = 50000.0) -> float:
    """趋势分层仓位（老陈 2026-08-09 指令: 下降≤3成/震荡5成/上升7-8成）。
    基于 UNIT_VALUE=5万(50%资金): up=8成(80000) / range=5成(50000) / down=3成(30000)。
    """
    if state == "up":
        return base * 1.6   # 8成
    if state == "down":
        return base * 0.6   # 3成
    return base             # 5成


def _lots(price: float, target_amount: float) -> int:
    """按目标金额买股，取整到1手(100股)。返回股数。"""
    if price <= 0:
        return 0
    return int(target_amount / price / 100) * 100


def backtest_full_pro(rows: List[Dict[str, Any]], min5_by_day: Dict[str, List[Dict[str, Any]]],
                      code: str, params: Optional[Dict[str, Any]] = None,
                      env_series: Optional[Dict[str, int]] = None,
                      position_filter: bool = False,
                      index_drop: Optional[Dict[str, float]] = None,
                      env_use_pos: bool = False) -> Dict[str, Any]:
    """专业股数资金模型回测（老陈 2026-08-08 专业版）。

    ⚠️ A股真实交易规则：
      - 初始资金 10 万；1手=100股，**交易量必须是100股整数倍**（取整到手）
      - 建仓 ≈ 5万（50%资金）；加仓/减仓 ≤ 底仓 1/2（手数取整）
      - T+1: 当日买入（建仓/加仓/T0买）锁定不可卖；卖只卖前日底仓；清仓锁定部分次日开盘卖
      - 每日收益 = 市值口径（cash + 持仓×收盘价），含手续费（佣金万2.5+印花税万5）
      - 信号记录: 手数/股数/价格/金额/盈亏(%+元)/持仓/资产——专业交易记录

    判定逻辑同 backtest_full_realtime（5分钟K逐根，无未来函数）：
      开盘3分钟/15分钟有效(连续3根5分K)/弱转强低吸/T+0实时轨迹/加减仓。

    ⭐ 2026-08-10 全天候监控融入（实盘机制回测可验证）:
      - index_drop: {day -> 上证指数当日跌幅%} 市场护栏——当日跌幅<-1% 禁止新开仓(guard_blocks)
      - 闪崩: 持仓连续3根5分K累计跌>5% → 立即清仓(flash_exits)
      - 板块走弱代理: 累计跌3~5% → 减半仓(sector_half)
      - 闭环反馈: 完整持仓按建仓特征(站稳昨收/突破/其他)统计胜率(feature_stats)
    """
    params = params or {}
    # ⭐ P0-3 修复(2026-08-21 审计): 默认参数对齐 BEST_PARAMS（stop9.0/hold5/关减仓/趋势分层开）——
    #   原默认 stop_single_pct=0(无止损)/hold_min=3/reduce_upper=1.5(减仓开)/trend_layers=False,
    #   与实盘引擎不一致, 缺参调用(组合回测)在无止损下跑=回测失真
    HOLD_MIN = int(params.get("hold_min", 5))
    # ⭐ 清仓分级（老陈 2026-08-09 A/B）: 上升趋势破位容忍根数（>0 启用, 默认0=不放松保持原行为）
    CLEAR_RELAX_UP = int(params.get("clear_relax_up", 0))
    # ⭐ 清仓环境分级（老陈 2026-08-09 优化16b）: up+大盘强 → 破位容忍 +CLEAR_ENV_RELAX 根（洗盘不跑）
    CLEAR_ENV_RELAX = int(params.get("clear_env_relax", 2))
    T0_GAP = float(params.get("t0_gap_pct", 2.0))
    # ⭐ 自适应 T0 阈值（老陈 2026-08-09 优化16b）: 妖股振幅大→低阈值滚动多/慢牛→高阈值防磨损
    # 用前20日均振幅 × mult 动态调 gap（mult>0 启用; 300319 均振幅~3%→gap≈3.6% 保持高质量）
    T0_GAP_ATR_MULT = float(params.get("t0_gap_atr_mult", 0.0))
    T0_AMP = float(params.get("t0_amp_pct", 3.0))
    T0_DROP = float(params.get("t0_drop_ratio", 0.5))
    ADD_VOL = float(params.get("add_vol", 1.5))
    REDUCE_VOL = float(params.get("reduce_vol", 1.2))
    # ⭐ 优化7: 加减仓规则（老陈 2026-08-08: 加减仓须优化）
    # 参数扫描(5只): 加仓②(连续3根站稳昨收+放量)开=+4.9pp核心收益; 减仓逐根扫描(原只看尾盘K=减仓0次), 阈值1.5最优
    REDUCE_UPPER = float(params.get("reduce_upper", 999.0))  # 减仓长上影阈值%（P0-3: 默认关, 对齐 BEST_PARAMS 999）
    ADD_BREAK = bool(params.get("add_break", True))         # 加仓②: 连续3根站稳昨收+放量也加仓
    # ⭐ 优化1: 重进时机（修复001267清仓后空仓错过反弹）
    # 参数实测(5只验证): hold5/cd3 最优（站稳25分钟+冷却3天）— hold3/cd1 太激进(002594回撤31%)
    RE_ENTRY = bool(params.get("re_entry", True))            # 重进开关
    RE_ENTRY_HOLD = int(params.get("re_entry_hold", 5))      # 重进需连续N根5分K站稳昨收(25分钟)
    RE_ENTRY_CD = int(params.get("re_entry_cd", 3))          # 清仓后冷却N个交易日才可重进
    # ⭐ P0-2(2026-09-13 明细审计): 下跌趋势禁重进（300319 近2年 07-14~07-31 出现 7 次"清仓→重进→清仓"被夹）。
    #   历史 A/B(002594) 显示 down 禁重进把 +14%→-35% → **默认 False 保持原行为**，参数开关 + 逐票 A/B 决定。
    RE_ENTRY_REQ_TREND = bool(params.get("re_entry_require_trend", False))
    # ⭐ 2026-08-09 优化（老陈流水审计 P0/P1/P2）:
    # P0-1 T0加仓联动: 当日已T0高抛 → 尾盘加仓价须低于高抛价（否则=卖低买高白做T）
    # 默认 False（保守不改旧行为），BEST_PARAMS 显式启用
    T0_ADD_MUTEX = bool(params.get("t0_add_mutex", False))
    # P0-2 兜底建仓收紧: 无分钟数据日K兜底建仓需"今开≥昨收"（原无条件 open 买 = 9笔T+1次日全亏主因）
    FALLBACK_BUY_GTE_PC = bool(params.get("fallback_buy_gte_pc", False))
    # P1-1 加仓时机盘中确认: 加仓买入价用触发K收盘而非尾盘价（原 m5[-1] = 全部15:00加仓）
    ADD_INTRADAY = bool(params.get("add_intraday", False))
    # P2 单笔止损: 持仓浮亏达 STOP_SINGLE_PCT% → 尾盘清仓（技能库教训: 单只≥8-10%, 勿用3%/5%）; 0=关
    # ⭐ P0-3 修复(2026-08-21 审计): 默认 9.0 对齐实盘 STOP_SINGLE_PCT(原默认0=缺参调用无止损)
    STOP_SINGLE_PCT = float(params.get("stop_single_pct", 9.0))
    # ⭐ P0-1(2026-09-13 明细审计): 盘中止损"即时触发"——原口径要求【连续3根收<昨收 且 浮亏≥5%】,
    #   急跌/跳空日明显穿透(实测 300319 08-03 记 -9.38%, 触发口径本应 -5%)。
    #   开启后：任一5分K收盘对成本浮亏 ≤ -STOP_SINGLE_PCT 立即止损(不等3根)。默认 False=原行为。
    STOP_IMMEDIATE = bool(params.get("stop_immediate", False))
    # ⭐ 2026-08-12 A股规则核对: 涨停买不进——当日开盘即一字/近涨停(start≥limit)实盘买不进,
    #   回测若不跳过会高估收益(已知诚实声明偏差). 可选用 SKIP_LIMIT_OPEN=1 提升真实性; 默认0=保持历史基准可比
    SKIP_LIMIT_OPEN = bool(params.get("skip_limit_open", False))
    # ⭐ 2026-08-12 老陈讨论: 趋势行情移动止损/止盈——上升趋势持有中用 ATR 追踪止损替代/互补"昨收止损",
    #   让趋势利润跑得更充分(昨收止损=线性慢移会过早止盈). 可选用; 0=关(默认保持历史基准)
    #   ATR_TRAIL_K: 上升趋势中 收盘 < 建仓后最高收盘 - K×ATR → 移动止损离场; 越大越宽松(跑趋势)
    ATR_TRAIL_K = float(params.get("atr_trail_k", 0.0))
    ATR_N = int(params.get("atr_n", 14))
    # ⭐ 2026-08-09 老陈核心批评: 战法缺短期趋势维度——上升过早卖出/下降过多买入/连续亏损
    # 趋势分层: 上升8成/震荡5成/下降3成仓位 + 上升趋势清仓需MA10确认（防过早卖）
    # ⭐ P0-3 修复(2026-08-21 审计): 默认 True 对齐实盘趋势分层(原默认 False=缺参调用无分层)
    TREND_LAYERS = bool(params.get("trend_layers", True))
    TREND_CLEAR_CONFIRM = bool(params.get("trend_clear_confirm", True))
    # ⭐ 底仓滚动精髓（老陈 2026-08-09）: T0滚动比例随趋势——up 40%/range 30%/down 15%
    T0_ROLL_TREND = bool(params.get("t0_roll_trend", False))
    T0_UP_RATIO = float(params.get("t0_up_ratio", 0.4))   # up 趋势 T0 滚动比例（可调 0.30-0.40）
    # ⭐ P1-2 低吸质量（老陈 2026-08-09）: 弱转强低吸仅 up 趋势（range 低吸 83% 亏损数据）
    ABSORB_UP_ONLY = bool(params.get("absorb_up_only", False))
    # ⭐ P1-2 低吸质量普适门禁: absorb_hold=低吸站稳根数(默认=HOLD_MIN=5 保持原行为, 可调) /
    #   absorb_vol=低吸需放量确认(跌破后收回站稳且当日量>5日均量)
    ABSORB_HOLD = int(params.get("absorb_hold", HOLD_MIN))
    ABSORB_VOL = bool(params.get("absorb_vol", False))
    # ⭐ 2026-08-10 全天候战法缺陷修复（老陈 441 条回测审计, 全部可选默认关保持原行为）:
    # 1) GUARD_LOSESTREAK_CD: 连亏熔断——连续2次建仓失败(3日内亏损清仓) → 冷却N个交易日不建仓
    # 2) GUARD_REENTRY_PROFIT: 重进需前笔盈利（防清仓亏损后接刀）
    # 3) GUARD_T0_DOWN_OFF: 弱势日(trend=down)禁止 T0 高抛（消除弱势磨损）
    # 4) HALF_THRESHOLD: 板块走弱减半阈值%（默认3.0=原行为, 2.5=提前减半）
    GUARD_LOSESTREAK_CD = int(params.get("guard_losestreak_cd", 0))
    GUARD_REENTRY_PROFIT = bool(params.get("guard_reentry_profit", False))
    GUARD_T0_DOWN_OFF = bool(params.get("guard_t0_down_off", False))
    HALF_THRESHOLD = float(params.get("half_threshold", 3.0))
    # ⭐ 缺陷修复1: 兜底建仓只允许上升趋势（range/down 放弃——8/8 兜底 5 亏教训）
    GUARD_FALLBACK_UP_ONLY = bool(params.get("guard_fallback_up_only", False))
    # ⭐ P1-量能确认（2026-08-10 老陈 P1 优化）: 建仓需开盘3根站稳 + 前3根量>前5日均量×倍率
    # 0=关(原行为); 1.0=需放量(≥日均); 1.2=强放量。治理"无量假强势"建仓
    ENTRY_VOL_CONFIRM = float(params.get("entry_vol_confirm", 0.0))
    # ⭐ P3-建仓趋势门禁（2026-08-10 老陈 P3 新）: 弱趋势禁/限建仓
    # 0=关(原行为: 按趋势分层仓位建); 1=down 禁建仓(up/range 可建); 2=仅 up 可建(range/down 禁)
    # 治"弱趋势建仓"——002594 类趋势坏票进池后仍按3成仓建, 连亏
    ENTRY_TREND_GATE = int(params.get("entry_trend_gate", 0))
    # ═══ 2026-08-22 多周期共振 A/B 参数（老陈 320笔300319复盘 → 6项计划, 全部默认关=现状）═══
    # A1(P0) 加仓只做低吸: 禁加仓②"全天强势+放量"(追高突破加仓), 只留加仓①"回踩不破+放量"
    #   —— 320笔记录 46次加仓中 26次追高(+1.8%), 06-11 高位加仓后闪崩 -9.43%
    ADD_DIP_ONLY = bool(params.get("add_dip_only", False))
    # A2(P0) 周线方向闸门(Elder三重滤网第1重): 截止昨日最新已完成周 收盘<前一周 → 禁建/重进/低吸/加仓/兜底
    #   (T0 降本保留) —— 治 2025-04 单月-11.3% 弱市仍高频进出
    WEEKLY_GATE = int(params.get("weekly_gate", 0))
    # A3(P1) 单票仓位上限 + 每日加仓次数上限 —— 治 06-02 一天11次加仓滚到满仓(06-11闪崩满仓挨打)
    MAX_POS_PCT = float(params.get("max_position_pct", 0.0))   # 0=关; 80=持仓市值≤总资产80%
    MAX_ADDS = int(params.get("max_adds_per_day", 0))          # 0=关; 2=每天最多2次加仓
    # A4(P1) T0 日内轮次上限 —— 治 2025-11-25 一天10次做T过度(注释说1轮但实现可无限轮)
    MAX_T0_ROUNDS = int(params.get("max_t0_rounds", 0))        # 0=关(现状); 3=每天最多3轮高抛
    # A5(P1) 上升趋势清仓确认用 MA5(更早止盈) 替代 MA10 —— 治 321,715峰值后回吐2.5%
    CLEAR_MA5 = bool(params.get("clear_ma5", False))
    # ═══ 2026-08-22 B1(P0) 买入择时: 所有买入(建仓/加仓/重进/低吸) 回调到位再成交 ═══
    #   老陈: "择时很重要, 交易记录追高太多, 买入应回调到位后再买"
    #   执行: 触发信号后不等触发价(开盘3分钟收盘/站稳K收盘=常追高), 扫描后续5分K——
    #     ① 回踩K: low ≤ 触发价×0.995 且 close≥昨收 → 以 min(low×1.001, 触发价×0.995) 成交(真低吸)
    #     ② 无回踩但尾盘 close ≤ 触发价×0.998(浮盈) → 尾盘成交
    #     ③ 尾盘仍 > 触发价(全天冲高) → 放弃该次买入(不追高, 宁缺毋滥)
    #   默认关=现状(确认即追); 1=回调成交+尾盘确认; 2=无回调直接放弃(更严)
    BUY_DIP = int(params.get("buy_dip", 0))

    rows = attach_prev_close(rows)
    positions = compute_positions(rows) if position_filter else {}
    # ⭐ 趋势状态机（每交易日一次, MA10/MA20快判定）
    trend_states = trend_state_by_day(rows) if TREND_LAYERS else {}
    INIT = 100000.0
    CASH_INIT = INIT
    COMM_RATE = 0.00025   # 佣金万2.5（双边）
    STAMP_RATE = 0.0005   # 印花税万5（卖出）
    # ⭐ P0-2 修复(2026-08-21 审计): 补滑点(与实盘 SLIPPAGE=千1 同口径)——原回测无滑点,
    #   单笔往返成本 0.10% vs 实盘 0.36%(3.6倍) → 回测收益系统性虚高
    SLIPPAGE = 0.001      # 滑点千1（买卖双边）

    cash = CASH_INIT
    position = 0          # 持仓股数（100整数倍）
    locked = 0            # 今日买入股数（T+1锁定）
    cost_total = 0.0      # 持仓成本金额（元）
    clear_pending = 0     # T+1: 清仓日锁定股数，次日开盘卖
    clear_cost = 0.0      # ⭐ 修复盈亏: 清仓日锁定部分成本，次日卖出算盈亏用
    prev_mv = CASH_INIT   # 昨日收盘市值
    n_t0 = 0
    n_add = 0
    n_reduce = 0
    n_trades = 0
    n_re_entry = 0
    t0_pnl = 0.0
    n_stop_single = 0  # ⭐ P2: 单笔止损触发次数
    # ⭐ 2026-08-12 A股规则: 涨停买不进跳过次数（SKIP_LIMIT_OPEN 开启时统计）
    limit_open_skip = 0
    # ⭐ 2026-08-12 老陈讨论: ATR移动止损状态（ATR_TRAIL_K>0 时启用）
    atr_trail_exits = 0     # ATR移动止损触发次数
    run_high = 0.0          # 当前持仓周期内的最高收盘（ATR追踪锚）
    # ⭐ 2026-08-10 全天候监控统计
    guard_blocks = 0    # 市场护栏拦截建仓次数（大盘跌幅<-1%）
    flash_exits = 0     # 闪崩立即清仓次数（3根5分K累计跌>5%）
    sector_half = 0     # 板块走弱减半次数（累计跌3~5%）
    cur_feat = ""       # 当前持仓建仓特征（闭环反馈）
    feature_stats: Dict[str, Dict[str, Any]] = {}  # 特征 -> {n, wins, sum_pnl}
    # ⭐ 2026-08-10 战法缺陷修复状态
    lose_streak = 0       # 连续建仓失败次数（3日内亏损清仓）
    cd_until = -999       # 连亏熔断冷却截止日索引（i < cd_until 禁建仓）
    losestreak_blocks = 0 # 熔断拦截建仓次数
    last_clear_pnl = 0.0  # 上次完整清仓盈亏%（重进盈利门）
    entry_idx = -999      # 当前持仓建仓日索引（连亏判定）
    daily_ret: List[float] = []
    signals: List[Dict[str, Any]] = []
    min_covered = 0
    env_bad_days = 0
    cum_asset = CASH_INIT
    last_clear_idx = -999  # ⭐ 重进: 上次清仓行索引（冷却期判定）

    def _sell(shares: int, price: float, action: str, note: str = "", mtime: str = ""):
        """卖股: 更新现金/持仓/成本/信号。mtime=触发分钟K时间(如 10:35)，用于T+0/加减仓精确复盘"""
        nonlocal cash, position, cost_total
        if shares <= 0 or position <= 0:
            return
        # ⭐ T+1 冻结强制（2026-08-10 老陈指出）: 任何卖出不可超过可卖部分(持仓-当日买入)
        # 原实现只 min(position)——若调用方误传含当日买入的股数会卖出冻结股（单点防御缺失）
        shares = min(shares, max(0, position - locked))
        if shares <= 0:
            return
        avg_cost = cost_total / position if position > 0 else price
        # ⭐ P0-2: 滑点后成交价(与实盘 _sell 同口径)
        sp = price * (1 - SLIPPAGE)
        amt = shares * sp
        fee = amt * COMM_RATE + amt * STAMP_RATE
        cash += amt - fee
        position -= shares
        cost_total -= avg_cost * shares
        pnl_pct = (sp - avg_cost) / avg_cost * 100.0 if avg_cost else 0.0
        pnl_amt = (sp - avg_cost) * shares - fee
        signals.append({"day": r["day"], "action": action, "price": round(sp, 2), "type": "sell",
                        "shares": shares, "hands": round(shares / 100, 1),
                        "amount": round(amt, 0), "pnl": round(pnl_pct, 2), "pnl_amount": round(pnl_amt, 0),
                        "hold_after": round(position / 100, 1),
                        "asset_after": round(cash + position * sp, 0),
                        "note": note, "time": mtime,
                        # ⭐ T+1 标注（2026-08-10 老陈要求）: 卖出后剩余可卖/冻结手数
                        "sellable": round(max(0, position - locked) / 100, 1),
                        "frozen": round(locked / 100, 1)})

    def _buy(shares: int, price: float, action: str, note: str = "", mtime: str = ""):
        """买股: 更新现金/持仓/成本/锁定/信号。mtime=触发分钟K时间(如 10:35)，用于T+0/加减仓精确复盘"""
        nonlocal cash, position, locked, cost_total
        if shares <= 0:
            return
        # ⭐ P0-2: 滑点后成交价(与实盘 _buy 同口径)
        bp = price * (1 + SLIPPAGE)
        amt = shares * bp
        fee = amt * COMM_RATE
        if amt + fee > cash:
            shares = int((cash - fee) / bp / 100) * 100
            if shares <= 0:
                return
            amt = shares * bp
            fee = amt * COMM_RATE
        cash -= amt + fee
        position += shares
        locked += shares
        cost_total += amt
        signals.append({"day": r["day"], "action": action, "price": round(bp, 2), "type": "buy",
                        "shares": shares, "hands": round(shares / 100, 1),
                        "amount": round(amt, 0), "pnl": 0.0, "pnl_amount": 0.0,
                        "hold_after": round(position / 100, 1),
                        "asset_after": round(cash + position * bp, 0),
                        "note": note, "time": mtime,
                        # ⭐ T+1 标注（2026-08-10 老陈要求）: 买入后冻结手数（当日不可卖）
                        "sellable": round(max(0, position - locked) / 100, 1),
                        "frozen": round(locked / 100, 1)})

    def _mt(k) -> str:
        """5分K day ('2026-08-07 10:35') → 时分 ('10:35')；无则空"""
        try:
            s = str(k.get("day", ""))
            return s[11:16] if len(s) >= 16 else ""
        except Exception:
            return ""

    # ⭐ 2026-08-22 B1 买入择时: 触发信号后回调到位再成交（返回 True=已处理成交/放弃; False=无条件直买）
    def _dip_buy(shares: int, trigger_px: float, action: str, note: str, m5bars: List[Dict[str, Any]], from_idx: int):
        """触发价 trigger_px 之后的 5分K 找回调:
        ① low≤trigger×0.995 且 close≥昨收 → 回调价成交(真低吸)
        ② 无回踩但尾盘 close≤trigger×0.998 → 尾盘浮盈确认
        ③ 尾盘仍>trigger(全天冲高) → BUY_DIP=2 放弃; =1 尾盘价成交(让步)
        """
        if shares <= 0 or BUY_DIP <= 0:
            _buy(shares, trigger_px, action, note, mtime="")
            return True
        # ⭐ 2026-08-22 B2: BUY_DIP=3 分级择时——仅"真追高"(触发价涨幅>3%)才等回调;
        #   温和上涨(≤3%)直接买(强者恒强, 等回调反而错过)
        if BUY_DIP == 3 and pc > 0 and (trigger_px / pc - 1) * 100 <= 3.0:
            _buy(shares, trigger_px, action, note, mtime="")
            return True
        for kk in m5bars[from_idx:]:
            if kk["close"] < pc:
                break  # 破位昨收, 不再等(放弃)
            if kk["low"] <= trigger_px * 0.995 and kk["close"] >= pc:
                bp = min(kk["low"] * 1.001, trigger_px * 0.995)
                _buy(shares, bp, action, note + "(回调择时)", mtime=_mt(kk))
                return True
        last_k = m5bars[-1] if m5bars else None
        if last_k is not None:
            if last_k["close"] <= trigger_px * 0.998:
                _buy(shares, last_k["close"], action, note + "(尾盘浮盈确认)", mtime=_mt(last_k))
                return True
            if BUY_DIP >= 2:
                return True  # 追高放弃
            _buy(shares, last_k["close"], action, note + "(尾盘让步)", mtime=_mt(last_k))
        return True

    for i in range(1, len(rows)):
        r = rows[i]
        pc = r["prev_close"]
        if pc <= 0:
            continue
        y = rows[i - 1]
        y_state = classify_daily_state(y)
        m5 = min5_by_day.get(r["day"], [])

        # T+1 解锁 + 清仓待卖（清仓日锁定部分保留在 position，次日开盘卖出）
        locked = 0
        # ⭐ 2026-08-22 A3/A4: 每日计数器重置（加仓次数 / T0轮次）
        adds_today = 0
        t0_rounds_today = 0
        # ⭐ 2026-08-22 A2 周线方向闸门(无未来函数, 提前到循环级定义供 m5/兜底两分支共用):
        #   截止昨日的5日(滚动周)净涨跌<0 = 周线转弱
        weekly_down = False
        if WEEKLY_GATE > 0 and i >= 6:
            weekly_down = float(rows[i - 1]["close"]) < float(rows[i - 6]["close"])
        if clear_pending > 0:
            shares = clear_pending
            amt = shares * r["open"]
            fee = amt * COMM_RATE + amt * STAMP_RATE
            cash += amt - fee
            position -= shares
            cost_total = 0.0
            # ⭐ 修复盈亏: 用清仓日保存的成本算真实盈亏（原版写死 pnl=0）
            avg_cost = clear_cost / shares if clear_cost > 0 and shares > 0 else r["open"]
            pnl_pct = (r["open"] - avg_cost) / avg_cost * 100.0 if avg_cost else 0.0
            pnl_amt = (r["open"] - avg_cost) * shares - fee
            signals.append({"day": r["day"], "action": "清仓(T+1次日)", "price": round(r["open"], 2), "type": "sell",
                            "shares": shares, "hands": round(shares / 100, 1), "amount": round(amt, 0),
                            "pnl": round(pnl_pct, 2), "pnl_amount": round(pnl_amt, 0),
                            "hold_after": round(position / 100, 1),
                            "asset_after": round(cash + position * r["close"], 0),
                            "note": "T+1锁定股次日开盘卖出", "time": "09:30",
                            "sellable": round(max(0, position - locked) / 100, 1),
                            "frozen": round(locked / 100, 1)})
            clear_pending = 0
            clear_cost = 0.0

        if m5:
            min_covered += 1
            open_strong = len(m5) >= 3 and all(k["close"] > pc for k in m5[:3])

            # 建仓: 昨日强势 + 开盘3分钟站稳 → 买≈5万(取整手)
            pos_ok = True
            # ⭐ 2026-08-10 P2: env_series 默认喂入(clear_env_relax 用), 大盘禁开仓仅 env_use_pos 开启
            if env_use_pos and env_series and env_series.get(r["day"], 1) < 0:
                env_bad_days += 1
                pos_ok = False
            # ⭐ 2026-08-10 P0 市场护栏: 大盘当日跌幅<-1% → 禁止新开仓（实盘监控同款）
            if index_drop:
                _drop = index_drop.get(r["day"], 0.0)
                if _drop <= -1.0:
                    guard_blocks += 1
                    pos_ok = False
            # ⭐ 2026-08-10 P1-量能确认: 开盘3根累计量 > 前5日日K均量×倍率（治"无量假强势"建仓）
            # ⭐ P1-1 修复(2026-08-11 审计实测): mootdx 5分K vol 单位=股(不×100), 日K fetch_daily_kline 已×100转股
            #   → 5分K vol3(股) 直接与 日K avg5(股) 比较, 不再×100。原实现两边都×100=数字虚高100倍。
            if ENTRY_VOL_CONFIRM > 0 and len(m5) >= 3 and i >= 6:
                vol3 = sum(float(k.get("volume") or 0) for k in m5[:3])
                vols_hist = [float(x.get("volume") or 0) for x in rows[max(0, i - 5):i]]
                avg5 = (sum(vols_hist) / len(vols_hist)) if vols_hist else 0.0
                if avg5 > 0 and vol3 <= avg5 * ENTRY_VOL_CONFIRM:
                    pos_ok = False
            if y_state == "强势" and position <= 0 and open_strong and pos_ok and i >= cd_until and (not weekly_down):
                buy_p = m5[2]["close"]
                # ⭐ 2026-08-12 A股规则: 涨停买不进——当日开盘即一字/近涨停(open≥limit)实盘买不进, 跳过建仓
                #   (可选用 SKIP_LIMIT_OPEN; 默认关=保持历史基准. 用开盘价判断: 开盘已封涨停→排队也极难成交)
                if SKIP_LIMIT_OPEN:
                    try:
                        _lp = limit_pct(code)
                        if _lp and r.get("open", 0) > 0 and pc > 0:
                            if (float(r["open"]) / pc - 1) * 100 >= _lp - 0.2:
                                limit_open_skip += 1
                                continue
                    except Exception:
                        pass
                # ⭐ 趋势分层仓位（老陈 2026-08-09）: up=8成 / range=5成 / down=3成
                tstate = trend_states.get(r["day"], "range") if TREND_LAYERS else "range"
                target_amt = _trend_target_amount(tstate) if TREND_LAYERS else 50000.0
                # ⭐ P3-建仓趋势门禁（2026-08-10）: down禁建/仅up建——治弱趋势建仓
                _gate_ok = True
                if TREND_LAYERS:
                    if ENTRY_TREND_GATE == 1 and tstate == "down":
                        _gate_ok = False
                    elif ENTRY_TREND_GATE == 2 and tstate != "up":
                        _gate_ok = False
                shares = _lots(buy_p, target_amt) if _gate_ok else 0
                if shares > 0:
                    _dip_buy(shares, buy_p, "建仓", "昨日强势+开盘3分钟站稳, 建仓≈%.0f万(趋势%s)" % (target_amt / 10000, tstate if TREND_LAYERS else "关"), m5, 3)
                    # ⭐ 闭环反馈: 回测建仓唯一逻辑=开盘3分钟站稳昨收 → 固定特征
                    cur_feat = "站稳昨收"
                    entry_idx = i  # ⭐ 连亏熔断: 记录建仓日
                    n_trades += 1

            if position > 0:
                # 破位: 连续N根5分K收<昨收 → 有效清仓（卖可卖，锁定次日）
                # ⭐ 趋势确认（老陈 2026-08-09）: 上升趋势中破位需"收盘<MA10"才清——
                # 否则日内假破位容忍（上升趋势过早卖出是 43 次清仓中 53% 后 5 日仍涨的根因）
                # ⭐ 清仓分级（老陈 2026-08-09 优化16b）: 趋势 + 当前环境(大盘) 双因素
                # 诊断(300319 70次清仓后20日): up+大盘强 +6.1%(丢预期最重→放宽) /
                #   range+大盘弱 -4.6%(保护成功→保持严格) / down +3.7%(清在低点→需反弹确认)
                hold_effective = HOLD_MIN
                if TREND_LAYERS:
                    tstate_cl = trend_states.get(r["day"], "range")
                    env_now = env_series.get(r["day"], 0) if env_series else 0
                    if CLEAR_RELAX_UP > 0 and tstate_cl == "up":
                        hold_effective = CLEAR_RELAX_UP  # 上升趋势放宽(默认0=不启用)
                    # ⭐ 环境加权: up+大盘强 → 容忍 +CLEAR_ENV_RELAX 根(洗盘不跑); down → 破位即清
                    if tstate_cl == "up" and env_now > 0 and CLEAR_ENV_RELAX > 0:
                        hold_effective = max(hold_effective, HOLD_MIN + CLEAR_ENV_RELAX)
                    elif tstate_cl == "down":
                        hold_effective = HOLD_MIN
                below_streak = 0
                broke = None
                intraday_stop = False
                for k in m5:
                    if k["close"] < pc:
                        below_streak += 1
                        # ⭐ P0-5 修复(2026-08-21 审计): 盘中止损(与实盘 _tick_stock 同口径)——
                        #   浮亏≥5% 且 连续3根收<昨收 → 立即止损, 不等 MA10 确认/尾盘9%
                        if position > 0:
                            _ac_i = cost_total / position if position > 0 else 0.0
                            # P0-1: 即时止损(可选)——单根浮亏触线即走, 不等3根
                            # 阈值与原口径一致(-5%), 区别只是不等 3 根 → 可公平 A/B
                            if STOP_IMMEDIATE and _ac_i > 0 and (k["close"] - _ac_i) / _ac_i * 100.0 <= -5.0:
                                intraday_stop = True
                                broke = k
                                break
                            if below_streak >= 3 and _ac_i > 0 and (k["close"] - _ac_i) / _ac_i * 100.0 <= -5.0:
                                intraday_stop = True
                                broke = k
                                break
                        if below_streak >= hold_effective:
                            broke = k
                            break
                    else:
                        below_streak = 0
                # 上升趋势清仓确认: 破位日收盘 < 昨日MA10（用昨日时点均线, 无未来函数）
                # ⭐ 2026-08-22 A5: clear_ma5=True 用 MA5 更早止盈（主升浪见顶后更快离场）
                trend_clear_ok = True
                if broke and TREND_LAYERS and TREND_CLEAR_CONFIRM:
                    tstate = trend_states.get(r["day"], "range")
                    if tstate == "up":
                        closes_hist = [x["close"] for x in rows]
                        idx_now = next((i for i, x in enumerate(rows) if x["day"] == r["day"]), None)
                        if idx_now is not None and idx_now >= 11:
                            if CLEAR_MA5:
                                ma_prev = sum(closes_hist[idx_now-6:idx_now-1]) / 5
                            else:
                                ma_prev = sum(closes_hist[idx_now-11:idx_now-1]) / 10
                            trend_clear_ok = r["close"] < ma_prev
                # ⭐ 2026-08-12 老陈讨论: ATR移动止损/止盈——趋势行情让利润跑(可选 atr_trail_k>0)
                #   上升趋势持有中, 收盘 < 建仓后最高收盘 - K×ATR → 移动止损离场(替代过早的昨收止损)
                #   ATR: 截止昨日N日真实波幅均值(无未来函数); run_high: 当前持仓周期最高收盘
                atr_trail = None  # (触发K, K价, 说明)
                if ATR_TRAIL_K > 0 and position > 0 and r.get("close", 0) > 0:
                    # 更新持仓周期最高收盘
                    if r["close"] > run_high:
                        run_high = r["close"]
                    # 只在上行趋势用ATR追踪(震荡用原破位, 避免被ATR宽带过早扫损)
                    _ts = trend_states.get(r["day"], "range")
                    if _ts == "up" and run_high > 0 and i >= ATR_N + 2:
                        try:
                            # 计算截止昨日ATR(无未来函数: 用i以前的数据)
                            _trs = []
                            for _j in range(i - ATR_N, i):
                                _hi = float(rows[_j].get("high") or rows[_j]["close"])
                                _lo = float(rows[_j].get("low") or rows[_j]["close"])
                                _pc = float(rows[_j].get("prev_close") or _lo)
                                _tr = max(_hi - _lo, abs(_hi - _pc), abs(_lo - _pc))
                                if _tr > 0:
                                    _trs.append(_tr)
                            if _trs:
                                _atr = sum(_trs) / len(_trs)
                                _trail_line = run_high - ATR_TRAIL_K * _atr
                                if r["close"] < _trail_line:
                                    atr_trail = (m5[-1] if m5 else r, _trail_line, "ATR追踪止损: 收%.2f<最高收%.2f-%.0f×ATR%.2f" % (r["close"], run_high, ATR_TRAIL_K, _atr))
                        except Exception:
                            pass
                # ⭐ 2026-08-10 闪崩/板块走弱检测（实盘监控同款: 连续3根5分K累计跌幅）
                flash_act = None  # ("flash"|"half", k, cum%)
                for ci in range(2, len(m5)):
                    seg = m5[ci - 2:ci + 1]
                    if seg and seg[0].get("open", 0) > 0:
                        cum = (float(seg[-1]["close"]) / float(seg[0]["open"]) - 1) * 100
                        if cum <= -5.0:
                            flash_act = ("flash", seg[-1], cum)
                            break
                        elif cum <= -HALF_THRESHOLD and flash_act is None:
                            flash_act = ("half", seg[-1], cum)
                if flash_act:
                    _act, _fk, _cum = flash_act
                    _sellable = position - locked
                    if _act == "flash" and _sellable > 0:
                        flash_exits += 1
                        _sell(_sellable, _fk["close"], "闪崩清仓",
                              "连续3根5分K累计跌%.1f%%(闪崩监控,立即离场)" % _cum, mtime=_mt(_fk))
                        # 闭环反馈: 完整持仓按建仓特征统计
                        _avg = cost_total / position if position > 0 else _fk["close"]
                        _pp = (_fk["close"] / _avg - 1) * 100 if _avg > 0 else 0.0
                        _fs = feature_stats.setdefault(cur_feat or "其他", {"n": 0, "wins": 0, "sum_pnl": 0.0})
                        _fs["n"] += 1
                        _fs["sum_pnl"] = round(_fs["sum_pnl"] + _pp, 2)
                        if _pp > 0:
                            _fs["wins"] += 1
                        # ⭐ 连亏熔断: 3日内亏损清仓 → streak+1; 盈利清零; ≥2次 → 冷却
                        if GUARD_LOSESTREAK_CD > 0:
                            if i - entry_idx <= 3 and _pp < 0:
                                lose_streak += 1
                            else:
                                lose_streak = 0
                            last_clear_pnl = _pp
                            if lose_streak >= 2:
                                cd_until = i + GUARD_LOSESTREAK_CD
                                losestreak_blocks += 1
                        if position > 0:
                            clear_pending = position
                            clear_cost = cost_total
                            cost_total = 0.0
                        cur_feat = ""
                        last_clear_idx = i
                    elif _act == "half" and _sellable >= 200:
                        sector_half += 1
                        half = int(_sellable * 0.5 / 100) * 100
                        if half >= 100:
                            _sell(half, _fk["close"], "减半",
                                  "板块走弱代理: 3根5分K累计跌%.1f%%(减半防扩散)" % _cum, mtime=_mt(_fk))
                # ⭐ 2026-08-12 ATR移动止损: 上升趋势用 ATR 追踪保护趋势利润(与破位并列, 先触发者离场)
                atr_trigger = atr_trail is not None
                # ⭐ P0-5: 盘中止损(intraday_stop)绕过 MA10 确认——实盘盘中止损不要求 MA10
                if (broke and (trend_clear_ok or intraday_stop)) or atr_trigger:
                    sellable = position - locked
                    _tk = atr_trail[0] if atr_trail else broke   # 触发K
                    if sellable > 0:
                        _tp = _tk["close"]
                        _note = ("盘中止损: 浮亏≥5%且3根跌破昨收" if intraday_stop
                                 else (atr_trail[2] if atr_trail else ("连续%d根5分K有效破位" % HOLD_MIN + ("+MA10确认" if not trend_clear_ok else ""))))
                        _sell(sellable, _tp, "清仓", _note, mtime=_mt(_tk))
                        if atr_trail:
                            atr_trail_exits += 1
                    if position > 0:
                        # T+1: 锁定部分保留在 position，次日开盘卖出（勿设0，否则价值丢失）
                        clear_pending = position
                        clear_cost = cost_total  # ⭐ 修复盈亏: 保存锁定部分成本
                        cost_total = 0.0
                    # ⭐ 闭环反馈: 清仓也统计完整持仓特征
                    _avg2 = clear_cost / clear_pending if clear_pending > 0 else 0.0
                    _tp2 = (atr_trail[0] if atr_trail else broke)["close"]
                    _pp2 = (_tp2 / _avg2 - 1) * 100 if _avg2 > 0 else 0.0
                    _fs2 = feature_stats.setdefault(cur_feat or "其他", {"n": 0, "wins": 0, "sum_pnl": 0.0})
                    _fs2["n"] += 1
                    _fs2["sum_pnl"] = round(_fs2["sum_pnl"] + _pp2, 2)
                    if _pp2 > 0:
                        _fs2["wins"] += 1
                    # ⭐ 连亏熔断: 3日内亏损清仓 → streak+1; 盈利清零; ≥2次 → 冷却
                    if GUARD_LOSESTREAK_CD > 0:
                        if i - entry_idx <= 3 and _pp2 < 0:
                            lose_streak += 1
                        else:
                            lose_streak = 0
                        last_clear_pnl = _pp2
                        if lose_streak >= 2:
                            cd_until = i + GUARD_LOSESTREAK_CD
                            losestreak_blocks += 1
                    cur_feat = ""
                    last_clear_idx = i  # ⭐ 重进: 记录清仓日
                else:
                    # ── T+0 实时轨迹：逐根5分K状态机（⭐优化8: 修复未来函数 + 支持多次回转）──
                    # ⚠️ 原版用全天 max_high/min_low 判定 = 收盘后才知道的"日K近似"（未来函数）
                    # 新版逐根推进：买卖都发生在触发当根K，无未来函数；一轮回转后可再开下一轮
                    sellable = position - locked
                    t0_pending = 0       # 已高抛卖出的底仓股数（>0 = 待接回）
                    t0_sell_ref = 0.0    # 先卖后买: 高抛卖出参考价（接回时算盈亏）
                    t0_sold_today = False  # ⭐ P0-1: 当日是否已发生T0高抛（尾盘加仓互斥）
                    # ⭐ 底仓滚动精髓（老陈 2026-08-09）: T0滚动比例随趋势调整——
                    # up 趋势滚动最赚钱(137次,+3.71%) → 40% 底仓积极滚;
                    # range 30%; down 最弱(30次,+0.41%) → 15% 少滚防连亏
                    if TREND_LAYERS and T0_ROLL_TREND:
                        tstate_t0 = trend_states.get(r["day"], "range")
                        if tstate_t0 == "up":
                            t0_ratio = T0_UP_RATIO
                        elif tstate_t0 == "down":
                            # ⭐ 2026-08-10 缺陷修复: 弱势日禁止 T0（消除 08-04 类磨损）
                            t0_ratio = 0.0 if GUARD_T0_DOWN_OFF else 0.15
                        else:
                            t0_ratio = 0.3
                    else:
                        t0_ratio = 0.3
                    t0_shares_base = int(max(sellable, 0) * t0_ratio / 100) * 100  # T0 单次用底仓(趋势调)
                    # ⭐ P1-1: 盘中加仓触发点记录（触发K收盘价；原用 m5[-1] 尾盘价 = 加仓全在15:00）
                    add_k = None
                    add_note_k = ""
                    for ti, tk in enumerate(m5):
                        tk_high = float(tk["high"])
                        tk_low = float(tk["low"])
                        tk_close = float(tk["close"])
                        tk_open = float(tk["open"])
                        is_last = ti == len(m5) - 1
                        # ⭐ P1-1: 记录"最后一根收盘>昨收"的K作为盘中加仓触发点（K线已确认强势）
                        # 用收盘>昨收而非苛刻的"低点≥昨收"（高波动票全天大多破过昨收 → 原条件记不到）
                        if tk_close > pc:
                            add_k = tk
                            add_note_k = "盘中站稳昨收"
                        # ── 已高抛 → 找接回点（⭐ 重新设计 老陈 2026-08-09: 接回价必须低于高抛价）──
                        #   回踩接回: 盘中K low ≤ 高抛价×0.998 且 收盘≥昨收 → 在 low 成交（真低吸）
                        #   尾盘接回: 仅当 收盘价 ≤ 高抛价×0.998（浮盈）才接回；浮亏=高抛成功不追回
                        #   ⚠️ 原逻辑: ①is_last 无条件尾盘接回 → 卖低买高(06-18卖24.58买27.76)
                        #             ②盘中接回用 tk_close 成交, K收盘可能已涨回 → 买价≥高抛价
                        if t0_pending > 0:
                            back_ok = False
                            buy_p = 0.0
                            if tk_low <= t0_sell_ref * 0.998 and tk_close >= pc:
                                back_ok = True
                                buy_p = min(tk_low * 1.001, t0_sell_ref * 0.998)  # 回踩低点成交(限≤高抛价)
                            elif is_last and tk_close <= t0_sell_ref * 0.998:
                                back_ok = True
                                buy_p = tk_close  # 尾盘浮盈接回用收盘价
                            if back_ok:
                                amt = t0_pending * buy_p
                                fee = amt * COMM_RATE
                                if amt + fee <= cash:
                                    cash -= amt + fee
                                    position += t0_pending
                                    locked += t0_pending
                                    cost_total += amt
                                    signals.append({"day": r["day"], "action": "T0买(接回)", "price": round(buy_p, 2), "type": "buy",
                                                    "shares": t0_pending, "hands": round(t0_pending / 100, 1), "amount": round(amt, 0),
                                                    "pnl": 0.0, "pnl_amount": 0.0, "hold_after": round(position / 100, 1),
                                                    "asset_after": round(cash + position * tk_close, 0),
                                                    "note": "T+1: 接回股当日锁定" + ("(尾盘浮盈接回)" if is_last else "(回踩低吸)"), "time": _mt(tk),
                                                    "sellable": round(max(0, position - locked) / 100, 1),
                                                    "frozen": round(locked / 100, 1)})
                                    # 先卖后买回转盈亏 = (卖出价 - 接回价) × 股数 × 30%权重
                                    t0_pnl += (t0_sell_ref - buy_p) / pc * 100.0 * 0.3 if t0_sell_ref > 0 else 0.0
                            if is_last:
                                t0_pending = 0  # 尾盘未接回 → 高抛成功降仓, 不追回
                            elif back_ok:
                                t0_pending = 0  # 盘中已接回
                            continue  # 本轮K已用于接回，不重复开T0
                        # ── 空T0仓 → 找信号 ──
                        if t0_shares_base < 100:
                            continue
                        sellable_now = position - locked
                        if sellable_now < t0_shares_base:
                            continue
                        # ⭐ 2026-08-22 A4: T0 日内轮次上限（现状=可无限轮, 2025-11-25 一天10次过度做T）
                        if MAX_T0_ROUNDS > 0 and t0_rounds_today >= MAX_T0_ROUNDS:
                            continue
                        # ⭐ T0 重新设计（老陈 2026-08-09: 原"先买后卖"87%占比重, 且同一根K内
                        # low买+high卖是K线内部理想化, 实盘做不到 → 改为【先卖后买】主导:
                        #   1. 冲高回落 → 先高抛（卖 tk_high×0.998）
                        #   2. 后续K回踩不破昨收 → 接回（买价 ≤ 高抛价×0.998, 否则不接）
                        #   3. 尾盘: 浮盈才接回, 浮亏=高抛成功不追回（防卖低买高亏手续费）
                        #   4. 每天最多 1 轮 T0（防高频磨损）
                        rise_pct = (tk_high - pc) / pc * 100.0
                        upper_shadow = (tk_high - max(tk_open, tk_close)) / pc * 100.0
                        # ⭐ 自适应 gap（优化16b）: 用前20日均振幅×mult 动态阈值（无 min5 日K兜底用固定值）
                        t0_gap_eff = T0_GAP
                        if T0_GAP_ATR_MULT > 0 and TREND_LAYERS:
                            idx_now2 = next((ii for ii, x in enumerate(rows) if x["day"] == r["day"]), None)
                            if idx_now2 is not None and idx_now2 >= 21:
                                amps = []
                                for x in rows[idx_now2-20:idx_now2]:
                                    if x.get("high") and x.get("low"):
                                        amps.append((float(x["high"]) - float(x["low"])) / float(x["low"]) * 100.0)
                                if amps:
                                    avg_amp = sum(amps) / len(amps)
                                    t0_gap_eff = max(2.0, round(avg_amp * T0_GAP_ATR_MULT, 1))
                        if rise_pct >= t0_gap_eff and upper_shadow >= 0.3:
                            sell_p = tk_high * 0.998
                            _sell(t0_shares_base, sell_p, "T0卖(高抛)", "冲高回落, 卖底仓%s手@%s" % (t0_shares_base / 100, _mt(tk)), mtime=_mt(tk))
                            t0_pending = t0_shares_base
                            t0_sell_ref = sell_p
                            t0_sold_today = True  # ⭐ P0-1: 当日已高抛 → 尾盘加仓互斥
                            n_t0 += 1
                            t0_rounds_today += 1
                            continue

                        # 加仓①: 回踩不破+放量；加仓②: 放量突破站稳昨收（连续3根5分K站上=有效，防假突破）≤底仓1/2
                        # ⚠️ 加仓②仅限强势态(当日全部收>昨收)，弱势票上禁止（防002594类过度加仓亏损）
                        # ⭐ P1-1: 盘中触发记录——用触发K收盘价买入（原 m5[-1] 尾盘价 = 加仓全在15:00）
                        vols = [k["volume"] for k in m5]
                        sellable = position - locked
                        day_min_low = min(k["low"] for k in m5)
                        day_all_above = len(m5) >= 3 and all(k2["close"] > pc for k2 in m5)
                        add_ok = False
                        add_note = ""
                        # ⭐ 趋势门禁（老陈 2026-08-09）: 下降趋势禁加仓（防下降过多买入连亏）
                        tstate_now = trend_states.get(r["day"], "range") if TREND_LAYERS else "range"
                        if TREND_LAYERS and tstate_now == "down":
                            add_ok, add_note = False, "下降趋势禁加仓"
                        if day_min_low >= pc * 0.998 and len(vols) >= 6 and vma_ok(vols, ADD_VOL * 1.2) and not (TREND_LAYERS and tstate_now == "down"):
                            add_ok, add_note = True, "回踩不破+放量"
                        elif ADD_BREAK and (not ADD_DIP_ONLY) and day_all_above and vma_ok(vols, ADD_VOL * 1.2) and not (TREND_LAYERS and tstate_now == "down"):
                            add_ok, add_note = True, "全天强势+放量"
                        # ⭐ P0-1: T0加仓联动——当日已高抛，若【最终加仓价】≥高抛价则禁止（卖低买高白做T）
                        # 盘中触发价 < 尾盘价时放行（真低吸）；只有尾盘追高（≥高抛价）才禁
                        add_price_final = None
                        add_time_final = ""
                        add_where_final = ""
                        if add_ok and ADD_INTRADAY and add_k is not None:
                            add_price_final = add_k["close"]
                            add_time_final = _mt(add_k)
                            add_where_final = "盘中触发"
                        elif add_ok:
                            add_price_final = m5[-1]["close"]
                            add_time_final = _mt(m5[-1])
                            add_where_final = "尾盘兜底"
                        if add_ok and T0_ADD_MUTEX and t0_sold_today and add_price_final is not None and add_price_final >= (t0_sell_ref if t0_sell_ref > 0 else 0):
                            add_ok, add_note = False, "已T0高抛, 加仓价不低于高抛价, 跳过"
                        # ⭐ 2026-08-22 A2: 周线转弱禁加仓（只做T降本+减仓）
                        if add_ok and WEEKLY_GATE > 0 and weekly_down:
                            add_ok, add_note = False, "周线转弱禁加仓"
                        # ⭐ 2026-08-22 A3: 单票仓位上限 + 每日加仓次数上限
                        if add_ok and MAX_ADDS > 0 and adds_today >= MAX_ADDS:
                            add_ok, add_note = False, f"每日加仓上限{MAX_ADDS}次"
                        if add_ok and MAX_POS_PCT > 0 and add_price_final is not None:
                            _mv_now = position * add_price_final
                            _tot = cash + _mv_now
                            if _tot > 0 and (_mv_now + int(sellable * 0.5 / 100) * 100 * add_price_final) / _tot * 100 > MAX_POS_PCT:
                                add_ok, add_note = False, f"仓位将超{MAX_POS_PCT:.0f}%上限"
                        if add_ok and sellable >= 200:
                            add_shares = int(sellable * 0.5 / 100) * 100
                            if add_shares >= 100:
                                # ⭐ P1-1: 盘中触发K（最后一根收盘>昨收）收盘价买入；无则尾盘价兜底
                                if ADD_INTRADAY and add_price_final is not None:
                                    add_price = add_price_final
                                    add_time = add_time_final
                                    add_where = add_where_final
                                else:
                                    add_price = m5[-1]["close"]
                                    add_time = _mt(m5[-1])
                                    add_where = "尾盘兜底"
                                _dip_buy(add_shares, add_price, "加仓", "%s(%s), ≤底仓1/2(%s手)" % (add_note, add_where, add_shares / 100), m5, ti + 1)
                                n_add += 1
                                adds_today += 1
                        # 减仓: 放量长上影（阈值1.0%）；⚠️逐根扫描全天（原只看尾盘K永远缩量→减仓0次）
                        # 找到第一根 长上影≥阈值 + 该根放量(>前5根均量×REDUCE_VOL) 的K → 在该K减仓
                        for ri in range(5, len(m5)):
                            rk = m5[ri]
                            rk_upper = (rk["high"] - max(rk["open"], rk["close"])) / pc * 100.0
                            prev5 = [m5[ri-5-x]["volume"] for x in range(5)]
                            avg5 = sum(prev5) / len(prev5) if prev5 else 0.0
                            rk_vol_ok = avg5 > 0 and rk["volume"] > avg5 * REDUCE_VOL
                            if rk_upper >= REDUCE_UPPER and rk_vol_ok:
                                sellable = position - locked
                                if sellable >= 200:
                                    red_shares = int(sellable * 0.5 / 100) * 100
                                    if red_shares >= 100:
                                        _sell(red_shares, rk["high"] * 0.998, "减仓", "放量长上影≥%.1f%%, ≤底仓1/2(%s手)" % (REDUCE_UPPER, red_shares / 100), mtime=_mt(rk))
                                        n_reduce += 1
                                break
            else:
                # 持币: 弱转强低吸（当日曾跌破 → 连续3根站稳）
                pos_ok = True
                if position_filter and positions.get(r["day"]) == "高位":
                    pos_ok = False
                if env_series and env_series.get(r["day"], 1) < 0:
                    pos_ok = False
                below_seen = False
                above_streak = 0
                # ⭐ 优化1: 重进时机——清仓冷却期后，若当日连续 RE_ENTRY_HOLD 根站稳昨收 → 重新进场
                # 修复001267: 清仓后空仓错过反弹（弱转强需要先跌破，重进不需要）
                re_entered = False
                # ⭐ 缺陷修复3: 重进冷却(连亏熔断) + 前笔盈利门（防清仓亏损后接刀）
                _re_tstate = trend_states.get(r["day"], "range") if TREND_LAYERS else "range"
                if RE_ENTRY and pos_ok and (i - last_clear_idx > RE_ENTRY_CD) \
                        and i >= cd_until \
                        and (not RE_ENTRY_REQ_TREND or _re_tstate != "down") \
                        and (not WEEKLY_GATE or not weekly_down) \
                        and (not GUARD_REENTRY_PROFIT or last_clear_pnl > 0):
                    entry_streak = 0
                    for ki, k in enumerate(m5):
                        if k["close"] > pc:
                            entry_streak += 1
                            if entry_streak >= RE_ENTRY_HOLD:
                                buy_p = k["close"]
                                # ⭐ 趋势分层仓位（老陈 2026-08-09）——重进不设 down 禁（验证:
                                # 002594 上 down 禁重进把 +14%→-35%, 弱票清仓后 down 期重进反而抓反弹）
                                tstate_re = trend_states.get(r["day"], "range") if TREND_LAYERS else "range"
                                target_amt = _trend_target_amount(tstate_re) if TREND_LAYERS else 50000.0
                                shares = _lots(buy_p, target_amt)
                                if shares > 0:
                                    _dip_buy(shares, buy_p, "重新进场", "清仓后连续%d根站稳昨收, 重进≈%.0f万(趋势%s)" % (RE_ENTRY_HOLD, target_amt / 10000, tstate_re if TREND_LAYERS else "关"), m5, ki + 1)
                                    n_trades += 1
                                    n_re_entry += 1
                                    entry_idx = i  # ⭐ 连亏熔断: 重进也记录建仓日
                                    re_entered = True
                                break
                        else:
                            entry_streak = 0
                if not re_entered:
                    for j, k in enumerate(m5):
                        if k["close"] < pc:
                            below_seen = True
                            above_streak = 0
                        else:
                            above_streak += 1
                            # ⭐ P1-2 低吸质量: 站稳根数可加严（ABSORB_HOLD 默认3=原HOLD_MIN, 5=防假反转）
                            if above_streak >= ABSORB_HOLD and below_seen and pos_ok and i >= cd_until and (not weekly_down):
                                buy_p = k["close"]
                                # ⭐ 趋势分层仓位 + 低吸趋势门禁（老陈 2026-08-09）
                                tstate_re = trend_states.get(r["day"], "range") if TREND_LAYERS else "range"
                                if TREND_LAYERS and ABSORB_UP_ONLY and tstate_re != "up":
                                    break  # 严格模式: 仅上升趋势弱转强低吸
                                if TREND_LAYERS and (not ABSORB_UP_ONLY) and tstate_re == "down":
                                    break  # 宽松模式: 仅禁下降趋势低吸
                                # ⭐ P1-2 低吸放量确认: 当日量 > 前5日均量（防无量假反转）
                                if ABSORB_VOL:
                                    vols_now = [x["volume"] for x in m5]
                                    if len(vols_now) >= 6:
                                        avg5v = sum(vols_now[-6:-1]) / 5
                                        if avg5v > 0 and sum(vols_now[-1:]) <= avg5v:
                                            break  # 无量收回站稳 → 假反转不低吸
                                target_amt = _trend_target_amount(tstate_re) if TREND_LAYERS else 50000.0
                                shares = _lots(buy_p, target_amt)
                                if shares > 0:
                                    _dip_buy(shares, buy_p, "弱转强低吸", "跌破后连续%d根站稳, 低吸≈%.0f万(趋势%s)" % (ABSORB_HOLD, target_amt / 10000, tstate_re if TREND_LAYERS else "关"), m5, j + 1)
                                    n_trades += 1
                                    entry_idx = i  # ⭐ 连亏熔断: 低吸也记录建仓日
                                    break
        else:
            # 无分钟数据日 → 日K兜底
            # ⭐ P0-2: 兜底建仓收紧——需"今开≥昨收"（原无条件 open 买 = 9笔T+1次日全亏主因:
            # 昨日强势但今日低开, 兜底开盘买在最高点, 次日破位清仓全锁定）
            if y_state == "强势" and position <= 0 and i >= cd_until and (not weekly_down):
                if (not FALLBACK_BUY_GTE_PC) or r["open"] >= pc:
                    buy_p = r["open"]
                    # ⭐ 趋势分层仓位（老陈 2026-08-09）: 下降趋势禁兜底建仓
                    tstate_fb = trend_states.get(r["day"], "range") if TREND_LAYERS else "range"
                    # ⭐ 缺陷修复1: 兜底只允许 up（range/down 放弃）
                    _fb_ok = not (TREND_LAYERS and tstate_fb == "down")
                    if GUARD_FALLBACK_UP_ONLY and TREND_LAYERS and tstate_fb != "up":
                        _fb_ok = False
                    if _fb_ok:
                        target_amt = _trend_target_amount(tstate_fb) if TREND_LAYERS else 50000.0
                        shares = _lots(buy_p, target_amt)
                        if shares > 0:
                            _buy(shares, buy_p, "建仓(兜底)", "无分钟数据日K兜底" + ("(今开≥昨收)" if r["open"] >= pc else "") + "(趋势%s)" % (tstate_fb if TREND_LAYERS else "关"))
                            n_trades += 1
                            entry_idx = i  # ⭐ 连亏熔断: 兜底也记录建仓日
            if position > 0:
                if r["close"] < pc:
                    sellable = position - locked
                    if sellable > 0:
                        _sell(sellable, r["close"], "清仓", "日K兜底破位")
                    if position > 0:
                        clear_pending = position
                        clear_cost = cost_total  # ⭐ 修复盈亏: 保存锁定部分成本
                        cost_total = 0.0

        # ⭐ P2: 单笔止损（2026-08-09 老陈流水审计）——持仓浮亏达 STOP_SINGLE_PCT% → 尾盘清仓
        # 技能库教训: 单只回测止损阈值应 ≥8-10%（3%/5% 对强势股日常波动太敏感, 已还原过）
        # 位置: 日末收盘后判定（用收盘价算浮亏, 避免盘中假信号）, 触发后卖可卖+锁定次日
        if position > 0 and STOP_SINGLE_PCT > 0:
            try:
                avg_cost_c = cost_total / position if position > 0 else 0.0
                if avg_cost_c > 0:
                    float_pct = (r["close"] - avg_cost_c) / avg_cost_c * 100.0
                    if float_pct <= -STOP_SINGLE_PCT:
                        sellable = position - locked
                        if sellable > 0:
                            _sell(sellable, r["close"], "止损清仓", "单笔浮亏%.1f%%达止损线%.0f%%" % (float_pct, STOP_SINGLE_PCT), mtime="15:00")
                        if position > 0:
                            clear_pending = position
                            clear_cost = cost_total
                            cost_total = 0.0
                        n_stop_single += 1
                        last_clear_idx = i
            except Exception:
                pass

        # 日末: 市值口径收益
        market_value = cash + position * r["close"]
        day_ret = (market_value - prev_mv) / prev_mv * 100.0 if prev_mv > 0 else 0.0
        prev_mv = market_value
        cum_asset = market_value
        daily_ret.append(day_ret)

    equity = [1.0]
    for ret in daily_ret:
        equity.append(equity[-1] * (1 + ret / 100.0))
    wins = sum(1 for x in daily_ret if x > 0)
    total = (equity[-1] - 1.0) * 100.0

    # ── 专业绩效指标（老陈 2026-08-08）──
    import math
    n = len(daily_ret)
    years = n / 252.0
    cagr = ((1 + total / 100.0) ** (1.0 / years) - 1.0) * 100.0 if years > 0 and total > -100.0 else 0.0
    mean = sum(daily_ret) / n if n else 0.0
    var = sum((x - mean) ** 2 for x in daily_ret) / (n - 1) if n > 1 else 0.0
    vol_ann = math.sqrt(var) * math.sqrt(252.0) if var > 0 else 0.0
    rf_daily = 0.02 / 252.0 * 100.0                     # 无风险利率 2%（日化）
    excess = [x - rf_daily for x in daily_ret]
    ex_mean = sum(excess) / n if n else 0.0
    ex_var = sum((x - ex_mean) ** 2 for x in excess) / (n - 1) if n > 1 else 0.0
    sharpe = ex_mean / math.sqrt(ex_var) * math.sqrt(252.0) if ex_var > 0 else 0.0
    mdd_pct = _max_drawdown(equity) * 100.0
    calmar = cagr / mdd_pct if mdd_pct > 0 else 0.0
    downside = [x for x in daily_ret if x < 0]
    down_var = sum(x * x for x in downside) / n if n else 0.0
    sortino = ex_mean / math.sqrt(down_var) * math.sqrt(252.0) if down_var > 0 else 0.0
    pos_ret = [x for x in daily_ret if x > 0]
    neg_ret = [x for x in daily_ret if x < 0]
    avg_win = sum(pos_ret) / len(pos_ret) if pos_ret else 0.0
    avg_loss = abs(sum(neg_ret) / len(neg_ret)) if neg_ret else 0.0
    pl_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0
    win_rate = len(pos_ret) / n * 100.0 if n else 0.0

    base = backtest_prevclose(rows, code, capital_model=True)
    base_b = base["口径b_隔夜T+1合规"]

    return {
        "code": code,
        "daily_ret": daily_ret,
        "signals": signals,
        "atr_trail_exits": atr_trail_exits,  # ⭐ A股规则讨论: ATR移动止损触发次数(0=未启用)
        "run_high_last": round(run_high, 2),
        "完整战法(专业股数)": {
            "总收益%(市值口径)": round(total, 2),
            "年化收益率(CAGR)%": round(cagr, 2),
            "最大回撤%": round(mdd_pct, 2),
            "年化波动率%": round(vol_ann, 2),
            "夏普比率": round(sharpe, 2),
            "卡玛比率": round(calmar, 2),
            "索提诺比率": round(sortino, 2),
            "日胜率%": round(win_rate, 1),
            "盈亏比": round(pl_ratio, 2),
            "做T次数": n_t0,
            "做T累计收益%(口径)": round(t0_pnl, 2),
            "加仓次数": n_add,
            "减仓次数": n_reduce,
            "单笔止损次数": n_stop_single,
            "重进次数": n_re_entry,
            "持仓周期数": n_trades,
            # ⭐ 2026-08-10 全天候监控指标
            "市场护栏拦截建仓": guard_blocks,
            "闪崩立即清仓": flash_exits,
            "板块走弱减半": sector_half,
            "连亏熔断拦截": losestreak_blocks,
            "年化%(近似)": round((total / (len(rows) / 250)) if len(rows) else 0, 2),
            "分钟覆盖天数": min_covered,
            "初始资金": round(INIT, 0),
            "期末资产": round(INIT * (1 + total / 100.0), 0),
            "收益金额": round(INIT * total / 100.0, 0),
            "交易规则": "1手=100股·100股整数倍·T+1锁定·加减仓≤底仓1/2·含佣金万2.5+印花税万5",
        },
        # ⭐ 2026-08-10 闭环反馈: 按建仓特征统计（站稳昨收/突破/其他 → 胜率与盈亏）
        "特征反馈": {k: {**v, "胜率%": round(v["wins"] / v["n"] * 100, 1) if v["n"] else 0.0}
                     for k, v in feature_stats.items()} if feature_stats else {},
        "全天候监控": {"市场护栏拦截": guard_blocks, "闪崩离场": flash_exits, "板块减半": sector_half},
        "对照_纯四态口径b": {
            "总收益%(复合)": base_b.get("总收益%(复合)"),
            "胜率%": base_b.get("胜率%"),
            "笔数": base_b.get("笔数"),
            "口径": "半仓50%+手续费(公平版，同资金约束)",
        },
        "诚实声明": "专业股数回测：1手=100股、100股整数倍、T+1锁定、加减仓≤底仓1/2、市值口径、含费；5分钟K逐根判定无未来函数；⭐含重进时机优化(清仓冷却3天后连续5根站稳昨收重新进场)；5min覆盖约1.75年；对照口径b为半仓公平版",
    }


def vma_ok(vols: List[float], ratio: float) -> bool:
    """最后根量 > 前5根均量×ratio。"""
    if len(vols) < 6:
        return False
    prev = vols[-6:-1]
    m = sum(prev) / len(prev)
    return m > 0 and vols[-1] > m * ratio
def backtest_full_portfolio(codes: List[str], count: int = 500, top_n: int = None) -> Dict[str, Any]:
    """完整战法 等权组合回测（多股共享资金池，每只 1/N 资金独立跑单只战法）。

    组合日收益 = 各股当日收益的等权平均（无持仓日算 0）。
    分散效果：单只大跌被其他只对冲；验证"选股池→组合"层面的战法效果。
    top_n: 只取单只收益排名前 N 做等权组合（评审修正3: 实盘聚焦5-8只，不撒网25只）。
    """
    from datafeed import fetch_daily_kline
    per_stock = []
    all_days = 0
    for code in codes:
        rows = fetch_daily_kline(code, count=count)
        if len(rows) < 60:
            print(f"  ⚠️ {code} K线不足({len(rows)}根)，跳过")
            continue
        r = backtest_full_tactics(rows, code)
        per_stock.append(r)
        all_days = max(all_days, len(r["daily_ret"]))
    if not per_stock:
        return {"error": "无有效股票"}
    if top_n:
        per_stock = sorted(per_stock, key=lambda r: -r["完整战法(底仓+做T+加减仓)"]["总收益%(复合)"])[:top_n]

    # 等权组合日收益（每日 = 有数据的各股平均）
    combo = []
    for d in range(all_days):
        day_rets = []
        for r in per_stock:
            dr = r["daily_ret"]
            if d < len(dr):
                day_rets.append(dr[d])
        combo.append(sum(day_rets) / len(day_rets) if day_rets else 0.0)

    equity = [1.0]
    for ret in combo:
        equity.append(equity[-1] * (1 + ret / 100.0))
    total = (equity[-1] - 1.0) * 100.0
    wins = sum(1 for x in combo if x > 0)

    contrib = []
    for r in per_stock:
        f = r["完整战法(底仓+做T+加减仓)"]
        contrib.append({
            "代码": r["code"],
            "总收益%": f["总收益%(复合)"],
            "做T次数": f["做T次数"],
            "做T收益%": f["做T累计收益%"],
            "加仓": f["加仓次数"],
            "减仓": f["减仓次数"],
            "持仓周期": f["持仓周期数"],
        })

    return {
        "组合(等权)": {
            "股票数": len(per_stock),
            "总收益%(复合)": round(total, 2),
            "年化%(近似)": round(total / (all_days / 250.0), 2) if all_days else 0.0,
            "日胜率%": round(wins / len(combo) * 100, 1) if combo else 0.0,
            "最大回撤%": round(_max_drawdown(equity) * 100, 2),
            "日均数": all_days,
        },
        "个股贡献": contrib,
        "诚实声明": "等权分仓、每只独立信号；组合降低单票风险但拉低弹性；T+0为日K级近似",
    }


def backtest_full_portfolio_pro(codes: List[str], count: int = 500,
                                top_n: int = None,
                                params: Optional[Dict[str, Any]] = None,
                                min5_loader: Optional[Callable] = None) -> Dict[str, Any]:
    """完整战法 等权组合回测（⭐优化9: 组合也用 pro 版 5分K逐根引擎，无未来函数）。

    与 backtest_full_portfolio 区别：后者用日K级 backtest_full_tactics（含未来函数），
    本函数每只用 backtest_full_pro（5分K逐根+重进+T+0状态机+加减仓优化），
    组合日收益 = 各股 pro 日收益等权平均（无持仓日算0）。
    min5_loader: 5分K加载函数（默认从 limitup_backtest._fetch_min5 复用），
                 组合场景建议外部批量预加载避免重复拉取。
    """
    from datafeed import fetch_daily_kline
    if min5_loader is None:
        try:
            from limitup_backtest import _fetch_min5 as _l
            min5_loader = _l
        except Exception:
            min5_loader = lambda code: {}
    params = params or {}
    per_stock = []
    all_days = 0
    for code in codes:
        rows = fetch_daily_kline(code, count=count)
        if len(rows) < 60:
            print(f"  ⚠️ {code} K线不足({len(rows)}根)，跳过")
            continue
        min5 = min5_loader(code)
        r = backtest_full_pro(rows, min5, code, params=params)
        if not r or "完整战法(专业股数)" not in r:
            print(f"  ⚠️ {code} pro回测失败，跳过")
            continue
        per_stock.append(r)
        all_days = max(all_days, len(r.get("daily_ret", [])))
    if not per_stock:
        return {"error": "无有效股票"}
    if top_n:
        per_stock = sorted(per_stock, key=lambda r: -r["完整战法(专业股数)"]["总收益%(市值口径)"])[:top_n]

    # 等权组合日收益（每日 = 有数据的各股平均）
    combo = []
    for d in range(all_days):
        day_rets = []
        for r in per_stock:
            dr = r.get("daily_ret", [])
            if d < len(dr):
                day_rets.append(dr[d])
        combo.append(sum(day_rets) / len(day_rets) if day_rets else 0.0)

    equity = [1.0]
    for ret in combo:
        equity.append(equity[-1] * (1 + ret / 100.0))
    total = (equity[-1] - 1.0) * 100.0
    wins = sum(1 for x in combo if x > 0)

    contrib = []
    for r in per_stock:
        f = r["完整战法(专业股数)"]
        contrib.append({
            "代码": r["code"],
            "总收益%": f["总收益%(市值口径)"],
            "做T次数": f["做T次数"],
            "做T收益%": f["做T累计收益%(口径)"],
            "加仓": f["加仓次数"],
            "减仓": f["减仓次数"],
            "重进": f.get("重进次数", 0),
            "持仓周期": f["持仓周期数"],
            "夏普": f["夏普比率"],
        })

    return {
        "组合(等权)": {
            "股票数": len(per_stock),
            "总收益%(复合)": round(total, 2),
            "年化%(近似)": round(total / (all_days / 250.0), 2) if all_days else 0.0,
            "日胜率%": round(wins / len(combo) * 100, 1) if combo else 0.0,
            "最大回撤%": round(_max_drawdown(equity) * 100, 2),
            "日均数": all_days,
            "引擎": "pro(5分K逐根·无未来函数)",
        },
        "个股贡献": contrib,
        "诚实声明": "等权分仓、每只独立信号；组合降低单票风险；⭐pro版引擎=5分K逐根+T+0状态机+重进+加减仓优化，无未来函数",
    }


def run_backtest(code: str, count: int = 400, min_score: int = 50) -> Dict[str, Any]:
    """汇总回测入口：打板隔日 + 昨收战法。"""
    rows = fetch_daily_kline(code, count=count)
    if len(rows) < 60:
        return {"code": code, "error": "K线数据不足（需要≥60根）"}
    return {
        "打板隔日回测": backtest_limitup(rows, code, min_score=min_score),
        "昨收战法回测": backtest_prevclose(rows, code),
    }
