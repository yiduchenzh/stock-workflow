"""
价值投资者专属 — 基本面评分(F-Score) + 入场战法判断
基于 data/strategy_value.md 第2章(基本面评分)和第3章(入场战法)

核心差异: 替代Aurora技术评分体系, 使用基本面评分决策
"""
import logging
logger = logging.getLogger("aurora.value_battle")


def calc_fscore(code: str, fundamentals: dict = None) -> dict:
    """
    基本面评分 F-Score Value Edition (0-100分)
    3维度 × 11指标

    参数:
        fundamentals: 包含以下key的字典
            pe_percentile, pb_percentile, dividend_yield, peg,
            roe_3y_avg, debt_ratio, ocf_to_revenue, gross_margin_std,
            drop_52w_pct, discount_to_fair, buyback_score
            或预留为None/0表示数据不可用

    返回:
        {"total": int, "quality": int, "value": int, "safety": int,
         "grade": str, "detail": dict}
    """
    f = fundamentals or {}

    # ── 第一维度: 估值安全性 (40分) ──
    # ① PE分位(15分)
    pe_pct = f.get("pe_percentile", 50)
    if pe_pct < 10:
        s_pe = 15
    elif pe_pct < 20:
        s_pe = 12
    elif pe_pct < 30:
        s_pe = 8
    elif pe_pct < 50:
        s_pe = 3
    else:
        s_pe = 0

    # ② PB分位(10分)
    pb_pct = f.get("pb_percentile", 50)
    if pb_pct < 10:
        s_pb = 10
    elif pb_pct < 20:
        s_pb = 8
    elif pb_pct < 30:
        s_pb = 5
    elif pb_pct < 50:
        s_pb = 2
    else:
        s_pb = 0

    # ③ 股息率(8分)
    div_yield = f.get("dividend_yield", 0)  # 百分比
    hs300_avg_div = f.get("hs300_avg_dividend_yield", 2.0)  # 沪深300平均股息率
    div_ratio = div_yield / hs300_avg_div if hs300_avg_div > 0 else 0
    if div_ratio >= 2.0:
        s_div = 8
    elif div_ratio >= 1.5:
        s_div = 6
    elif div_ratio >= 1.0:
        s_div = 4
    elif div_ratio >= 0.5:
        s_div = 2
    else:
        s_div = 0

    # ④ PEG(7分)
    peg = f.get("peg", 99)
    if peg < 0:  # 净利润增长率为负
        s_peg = 0
    elif peg < 0.5:
        s_peg = 7
    elif peg < 0.8:
        s_peg = 5
    elif peg < 1.2:
        s_peg = 3
    else:
        s_peg = 0

    value_score = s_pe + s_pb + s_div + s_peg

    # ── 第二维度: 公司质量 (35分) ──
    # ⑤ ROE均值(10分)
    roe = f.get("roe_3y_avg", 0)  # 百分比
    if roe > 20:
        s_roe = 10
    elif roe > 15:
        s_roe = 7
    elif roe > 10:
        s_roe = 4
    elif roe > 5:
        s_roe = 1
    else:
        s_roe = 0

    # ⑥ 资产负债率(8分)
    debt = f.get("debt_ratio", 50)  # 百分比
    industry_adj = f.get("industry", "") in ("金融", "房地产", "银行")
    if industry_adj:
        debt -= 20  # 金融/地产负债率上浮20pct
    if debt < 30:
        s_debt = 8
    elif debt < 45:
        s_debt = 6
    elif debt < 60:
        s_debt = 4
    elif debt < 70:
        s_debt = 1
    else:
        s_debt = 0

    # ⑦ 经营现金流/营收(8分)
    ocf_ratio = f.get("ocf_to_revenue", 0)  # 百分比
    if ocf_ratio > 20:
        s_ocf = 8
    elif ocf_ratio > 15:
        s_ocf = 6
    elif ocf_ratio > 10:
        s_ocf = 4
    elif ocf_ratio > 5:
        s_ocf = 1
    else:
        s_ocf = 0

    # ⑧ 毛利率稳定性(9分)
    gm_std = f.get("gross_margin_std", 99)  # 百分比标准差
    if gm_std < 3:
        s_gm = 9
    elif gm_std < 5:
        s_gm = 6
    elif gm_std < 8:
        s_gm = 3
    else:
        s_gm = 0

    quality_score = s_roe + s_debt + s_ocf + s_gm

    # ── 第三维度: 安全边际 (25分) ──
    # ⑨ 距52周高点跌幅(8分)
    drop = f.get("drop_52w_pct", 0)  # 正数表示跌幅
    if drop > 40:
        s_drop = 8
    elif drop > 30:
        s_drop = 6
    elif drop > 20:
        s_drop = 4
    elif drop > 10:
        s_drop = 2
    else:
        s_drop = 0

    # ⑩ 较合理估值折价(10分, 简化DCF/PE估值法)
    discount = f.get("discount_to_fair", 0)  # 正数表示折价百分比
    if discount > 40:
        s_disc = 10
    elif discount > 30:
        s_disc = 7
    elif discount > 20:
        s_disc = 4
    elif discount > 10:
        s_disc = 1
    else:
        s_disc = 0

    # ⑪ 股东增持/回购(7分, 过去6个月)
    buyback = f.get("buyback_score", 0)
    # buyback_score: 1=大股东增持>1%股本, 2=回购>2%股本,
    #                3=增持0.5-1%, 0=无, -1=大股东减持
    if buyback == 1:
        s_bb = 7
    elif buyback == 2:
        s_bb = 5
    elif buyback == 3:
        s_bb = 3
    elif buyback == 0:
        s_bb = 0
    elif buyback == -1:
        s_bb = -5  # 负面信号
    else:
        s_bb = 0

    safety_score = s_drop + s_disc + s_bb

    # ── 总分与分级 ──
    total = value_score + quality_score + safety_score
    total = max(0, min(100, total))

    if total >= 80:
        grade = "A"
    elif total >= 65:
        grade = "B"
    elif total >= 50:
        grade = "C"
    elif total >= 30:
        grade = "D"
    else:
        grade = "E"

    return {
        "total": total,
        "quality": quality_score,
        "value": value_score,
        "safety": safety_score,
        "grade": grade,
        "detail": {
            "pe_percentile_score": s_pe,
            "pb_percentile_score": s_pb,
            "dividend_score": s_div,
            "peg_score": s_peg,
            "roe_score": s_roe,
            "debt_score": s_debt,
            "ocf_score": s_ocf,
            "gross_margin_score": s_gm,
            "drop_52w_score": s_drop,
            "discount_score": s_disc,
            "buyback_score": s_bb,
        },
    }


def check_value_entry(code: str, score: dict, conditions: dict = None) -> dict:
    """
    价值投资者4种入场条件判断

    参数:
        score: calc_fscore() 的返回值
        conditions: 包含各战法所需额外数据的字典
            - pe_percentile, pb_percentile, pe, industry_avg_pe
            - dividend_yield, hs300_avg_dividend_yield, dividend_payout_ratio
            - roe, gross_margin, ocf_to_net_profit, market_share
            - net_cash_per_share, current_price
            - catalyst_type (催化剂类型)
            - sector_name, mcap

    返回:
        {"signal": bool, "strategy": str, "score": int, "reason": str}
    """
    c = conditions or {}
    total = score.get("total", 0)
    grade = score.get("grade", "E")
    quality = score.get("quality", 0)
    value_score = score.get("value", 0)

    strategies = []

    # ════════════════════════════════════════════
    # 战法1: 估值洼地+均值回归催化剂 (Value-Trough Catalyst)
    # ════════════════════════════════════════════
    vtc_ok = True
    # 前置: F-Score≥65, 估值安全性≥30/40, 沪深300+市值>200亿
    if total < 65:
        vtc_ok = False
    if value_score < 30:
        vtc_ok = False
    mcap = c.get("mcap", 0)
    if mcap > 0 and mcap < 200:
        vtc_ok = False

    if vtc_ok:
        # ① 估值确认
        pe_pct = c.get("pe_percentile", 99)
        pb_pct = c.get("pb_percentile", 99)
        pe = c.get("pe", 99)
        ind_avg_pe = c.get("industry_avg_pe", 99)
        div_yield = c.get("dividend_yield", 0)
        hs300_div = c.get("hs300_avg_dividend_yield", 2.0)

        valuation_ok = (
            pe_pct < 30
            and pb_pct < 30
            and (ind_avg_pe <= 0 or pe < ind_avg_pe * 0.7)
            and div_yield > hs300_div * 0.5
        )

        # ② 催化剂出现
        catalyst = c.get("catalyst_type", "")
        catalyst_ok = catalyst in (
            "earnings_turnaround", "policy_tailwind",
            "insider_buy", "buyback_plan", "sector_leader_beat",
        )

        # ③ 周线时机(加分项)
        weekly_signal = c.get("weekly_signal", False)

        if valuation_ok and catalyst_ok:
            base_score = 75 if weekly_signal else 65
            strategies.append({
                "name": "value_trough_catalyst",
                "signal": True,
                "score": base_score,
                "reason": f"估值洼地+催化剂触发 F-Score={total}"
                          + ("+周线时机确认" if weekly_signal else ""),
            })

    # ════════════════════════════════════════════
    # 战法2: 高股息+护城河防御 (Dividend Moat Buffer)
    # ════════════════════════════════════════════
    dmb_ok = True
    if quality < 25:
        dmb_ok = False
    if mcap > 0 and mcap < 500:
        dmb_ok = False
    div_history = c.get("dividend_years", 0)
    if div_history < 5:
        dmb_ok = False

    if dmb_ok:
        # ① 股息条件
        div_yield = c.get("dividend_yield", 0)
        bond_yield = c.get("bond_yield_10y", 3.0)
        payout_ratio = c.get("dividend_payout_ratio", 100)
        div_growing = c.get("dividend_growing_3y", False)

        div_ok = (div_yield >= 4.0 or div_yield > bond_yield * 1.5) and payout_ratio < 60 and div_growing

        # ② 护城河确认(任意2项)
        moat_score = 0
        if c.get("roe", 0) > 15:
            moat_score += 1
        if c.get("gross_margin", 0) > 30 and c.get("gross_margin_std", 99) < 5:
            moat_score += 1
        ocf_to_np = c.get("ocf_to_net_profit", 0)
        if ocf_to_np > 1.0:
            moat_score += 1
        if c.get("market_share_rank", 99) <= 3:
            moat_score += 1
        if c.get("moat_type", ""):
            moat_score += 1

        # ③ 估值条件(任意1项)
        valuation_ok2 = False
        if pe_pct < 30:
            valuation_ok2 = True
        if pb_pct < 20:
            valuation_ok2 = True
        npv = c.get("net_cash_per_share", 0)
        price = c.get("current_price", 0)
        if npv > 0 and price > 0 and price < npv:
            valuation_ok2 = True

        if div_ok and moat_score >= 2 and valuation_ok2:
            strategies.append({
                "name": "dividend_moat_buffer",
                "signal": True,
                "score": 70,
                "reason": f"高股息护城河触发 股息率{div_yield:.1f}% 护城河{moat_score}/5",
            })

    # ════════════════════════════════════════════
    # 战法3: 困境反转+资产负债表修复 (Turnaround)
    # ════════════════════════════════════════════
    if total >= 80 and c.get("not_st", True) and c.get("not_cyclical", True):
        distress_type = c.get("distress_type", "")
        acceptable = distress_type in (
            "industry_short_term", "one_time_charge",
            "management_change", "macro_downturn",
        )
        if acceptable:
            # ② 资产负债表修复信号(任意2项)
            repair_score = 0
            if c.get("debt_ratio_qoq_change", 0) < 0:
                repair_score += 1
            if c.get("ocf_turned_positive", False):
                repair_score += 1
            if c.get("ar_turnover_improving", False):
                repair_score += 1
            if c.get("inventory_decreasing", False):
                repair_score += 1
            if c.get("interest_bearing_debt_decreasing", False):
                repair_score += 1

            # ③ 估值极端底部
            pb = c.get("pb", 99)
            extreme_value = pb < 1.0 or pe_pct < 5 or c.get("market_cap_below_net_asset", False)

            if repair_score >= 2 and extreme_value:
                strategies.append({
                    "name": "turnaround",
                    "signal": True,
                    "score": 60,
                    "reason": f"困境反转触发 修复信号{repair_score}/5 F-Score={total}",
                })

    # ════════════════════════════════════════════
    # 战法4: 破净资产折扣+股东行动 (Net-Net)
    # ════════════════════════════════════════════
    if value_score >= 32 and (mcap <= 0 or mcap >= 200):
        # ① 资产折扣
        net_current_asset = c.get("net_current_asset_value", 0)
        total_liab = c.get("total_liabilities", 0)
        pb = c.get("pb", 99)
        cash_per_share = c.get("cash_per_share", 0)
        price = c.get("current_price", 0)

        discount_ok = False
        if net_current_asset > 0 and total_liab > 0:
            if mcap < net_current_asset - total_liab:
                discount_ok = True
        if not discount_ok and pb < 0.8:
            discount_ok = True
        if not discount_ok and cash_per_share > 0 and price > 0:
            if price < cash_per_share:
                discount_ok = True

        # ② 股东行动催化剂
        activist = c.get("activist_catalyst", "")
        catalyst_ok2 = activist in (
            "privatization", "large_buyback", "special_dividend",
            "management_buy", "strategic_investor", "asset_spin_off",
        )

        # ③ 业务稳定性
        biz_stable = (
            not c.get("net_loss", True)
            and c.get("ocf_positive", False)
            and not c.get("major_litigation", False)
        )

        if discount_ok and catalyst_ok2:
            strategies.append({
                "name": "net_net_activist",
                "signal": True,
                "score": 60,
                "reason": f"破净+股东行动触发 PB={pb:.2f}",
            })

    # ── 决策输出 ──
    if not strategies:
        return {"signal": False, "strategy": "none", "score": 0,
                "reason": f"F-Score={total}({grade}) 无可触发的入场战法"}

    best = max(strategies, key=lambda s: s["score"])
    return {
        "signal": True,
        "strategy": best["name"],
        "score": best["score"],
        "reason": best["reason"],
        "all_candidates": [s["name"] for s in strategies],
    }
