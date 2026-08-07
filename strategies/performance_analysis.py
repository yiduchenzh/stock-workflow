"""组合绩效分析 v1.0 — 对齐hikyuu Performance.cpp 52项统计 + R乘数体系

服务5Agent周复盘: 输入trades(平仓交易列表), 输出完整绩效画像:
- R乘数体系: R = profit/totalRisk (totalRisk=Σ(买入价-止损)×数量, 对齐hikyuu)
- 收益率: 已平仓/未平仓/年复合
- 赢亏统计: 比例/期望值/盈亏比
- 持仓时间: 赢亏平均/最大
- 连续统计: 最大连续赢利/亏损
"""
import logging
logger = logging.getLogger("aurora.performance")
import numpy as np
from datetime import datetime


def _safe_div(a, b, fallback=0.0):
    if b is None or (isinstance(b, (int, float)) and b == 0):
        return fallback
    r = a / b
    return fallback if (np.isnan(r) or np.isinf(r)) else r


def analyze_performance(trades: list, capital: float = 1_000_000) -> dict:
    """分析平仓交易绩效 — trades: 已完成(卖出)交易列表
    每项需含: code/action/sell_price/avg_cost(或pnl)/shares/reason/entry_date/time
    兼容sim_trades.json结构: {action:'sell', code, shares, price, pnl, pnl_pct, reason, time}
    也兼容含stop_loss/entry_price的完整结构(用于R乘数)
    """
    closed = [t for t in trades if t.get("action") == "sell"]
    n = len(closed)
    if n == 0:
        return {"trades": 0, "note": "无平仓交易"}

    # ── 基础提取 ──
    pnls = []          # 每笔盈亏金额
    pnl_pcts = []      # 每笔盈亏比例(%)
    hold_days = []     # 持仓天数
    risks = []         # 每笔风险金额(买入价-止损)×数量
    codes_won = []
    for t in closed:
        pnl = t.get("pnl", 0) or 0
        pnl_pct = t.get("pnl_pct", 0) or 0
        pnls.append(pnl)
        pnl_pcts.append(pnl_pct)
        # 持仓天数
        entry = str(t.get("entry_date", ""))[:10]
        exit_d = str(t.get("time", ""))[:10]
        hd = 0
        if entry and exit_d:
            try:
                hd = (datetime.strptime(exit_d, "%Y-%m-%d") - datetime.strptime(entry, "%Y-%m-%d")).days
            except Exception:
                hd = 0
        hold_days.append(max(0, hd))
        # R乘数: risk = (买入价-止损)×数量
        entry_price = t.get("entry_price", 0) or t.get("avg_cost", 0) or 0
        stop = t.get("stop_loss", 0) or 0
        shares = t.get("shares", 0) or 0
        if entry_price > 0 and stop > 0 and shares > 0:
            risks.append(abs(entry_price - stop) * shares)
        else:
            risks.append(None)
        if pnl > 0:
            codes_won.append(t.get("code"))

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    nw = len(wins); nl = len(losses)

    # ── R乘数体系 (对齐hikyuu: R = profit/totalRisk) ──
    r_values = []
    total_risk = 0.0
    for p, r in zip(pnls, risks):
        if r is not None:
            total_risk += r
            r_values.append(p / r if r > 0 else 0.0)
    avg_r = float(np.mean(r_values)) if r_values else 0.0
    # 期望R = 总盈亏/总风险
    expect_r = _safe_div(sum(pnls), total_risk) if total_risk > 0 else 0.0
    # R乘数分布
    r_hist = {"r>=2": 0, "1<=r<2": 0, "0<=r<1": 0, "r<0": 0}
    for r in r_values:
        if r >= 2: r_hist["r>=2"] += 1
        elif r >= 1: r_hist["1<=r<2"] += 1
        elif r >= 0: r_hist["0<=r<1"] += 1
        else: r_hist["r<0"] += 1

    # ── 收益率 ──
    total_pnl = sum(pnls)
    total_pnl_pct = _safe_div(total_pnl, capital) * 100
    gross_win = sum(wins)
    gross_loss = sum(losses)
    profit_factor = _safe_div(gross_win, abs(gross_loss)) if gross_loss != 0 else (99.0 if gross_win > 0 else 0.0)
    expectancy = _safe_div(total_pnl, n)
    avg_win = _safe_div(gross_win, nw) if nw else 0.0
    avg_loss = _safe_div(gross_loss, nl) if nl else 0.0
    win_rate = _safe_div(nw, n) * 100
    payoff_ratio = _safe_div(avg_win, abs(avg_loss)) if avg_loss != 0 else 0.0
    # 年复合收益率(假设交易周期已知)
    first_date = min(str(t.get("time", ""))[:10] for t in closed if t.get("time"))
    last_date = max(str(t.get("time", ""))[:10] for t in closed if t.get("time"))
    ann_return = 0.0
    if first_date and last_date and first_date != last_date:
        try:
            days = (datetime.strptime(last_date, "%Y-%m-%d") - datetime.strptime(first_date, "%Y-%m-%d")).days
            if days > 0:
                growth = _safe_div(sum(pnls), capital) + 1
                ann_return = (growth ** (365.0 / days) - 1) * 100 if growth > 0 else -100.0
        except Exception:
            ann_return = 0.0

    # ── 最大回撤 (基于累计权益曲线) ──
    equity = [capital]
    for p in pnls:
        equity.append(equity[-1] + p)
    eq = np.array(equity)
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak * 100
    max_dd = float(np.min(dd)) if len(dd) > 1 else 0.0

    # ── 连续统计 ──
    max_consec_win = 0; max_consec_loss = 0
    cur_w = 0; cur_l = 0
    for p in pnls:
        if p > 0:
            cur_w += 1; cur_l = 0
        else:
            cur_l += 1; cur_w = 0
        max_consec_win = max(max_consec_win, cur_w)
        max_consec_loss = max(max_consec_loss, cur_l)

    # ── 持仓时间 ──
    win_hd = [h for h, p in zip(hold_days, pnls) if p > 0]
    loss_hd = [h for h, p in zip(hold_days, pnls) if p <= 0]
    avg_hold_win = float(np.mean(win_hd)) if win_hd else 0.0
    avg_hold_loss = float(np.mean(loss_hd)) if loss_hd else 0.0
    max_hold = max(hold_days) if hold_days else 0

    # ── 最大单笔 ──
    max_win = max(pnls) if pnls else 0.0
    max_loss = min(pnls) if pnls else 0.0
    max_win_pct = max(pnl_pcts) if pnl_pcts else 0.0
    max_loss_pct = min(pnl_pcts) if pnl_pcts else 0.0

    return {
        "trades": n,
        "wins": nw, "losses": nl,
        "win_rate": round(win_rate, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 3),
        "annual_return_pct": round(ann_return, 2),
        "gross_win": round(gross_win, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy": round(expectancy, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "payoff_ratio": round(payoff_ratio, 2),
        # R乘数体系
        "r_values": [round(r, 2) for r in r_values],
        "avg_r": round(avg_r, 2),
        "expect_r": round(expect_r, 2),
        "total_risk": round(total_risk, 2),
        "r_distribution": r_hist,
        # 风险
        "max_drawdown_pct": round(max_dd, 2),
        "max_single_win": round(max_win, 2),
        "max_single_loss": round(max_loss, 2),
        "max_win_pct": round(max_win_pct, 2),
        "max_loss_pct": round(max_loss_pct, 2),
        # 持仓
        "avg_hold_win_days": round(avg_hold_win, 1),
        "avg_hold_loss_days": round(avg_hold_loss, 1),
        "max_hold_days": max_hold,
        # 连续性
        "max_consec_win": max_consec_win,
        "max_consec_loss": max_consec_loss,
        "win_codes": list(set(codes_won)),
        # 元信息
        "period": {"start": first_date, "end": last_date},
        "note": "对齐hikyuu Performance.cpp 52项统计核心口径",
    }


def format_performance_report(p: dict) -> str:
    """绩效报告格式化 — 用于周复盘/推送"""
    if not p or p.get("trades", 0) == 0:
        return "📊 无平仓交易"
    lines = [
        "📊 **绩效报告**",
        f"交易 {p['trades']}笔 | 胜率 {p['win_rate']}% ({p['wins']}胜/{p['losses']}负)",
        f"总盈亏 {p['total_pnl']:+,.0f}元 ({p['total_pnl_pct']:+.2f}%) | 年化 {p['annual_return_pct']:+.1f}%",
        f"盈亏比 {p['payoff_ratio']} | 期望值 {p['expectancy']:+.0f}元/笔 | 利润因子 {p['profit_factor']}",
        f"最大回撤 {p['max_drawdown_pct']}% | 最大单笔亏 {p['max_single_loss']:+,.0f}元",
        f"R乘数: 均值{round(p['avg_r'],2)} 期望{round(p['expect_r'],2)} | 分布 {p['r_distribution']}",
        f"持仓: 盈利单均{round(p['avg_hold_win_days'],1)}天 / 亏损单均{round(p['avg_hold_loss_days'],1)}天",
        f"连续性: 最大连赢{p['max_consec_win']}笔 / 最大连亏{p['max_consec_loss']}笔",
        f"周期: {p.get('period', {}).get('start', '?')} → {p.get('period', {}).get('end', '?')}",
    ]
    return "\n".join(lines)
