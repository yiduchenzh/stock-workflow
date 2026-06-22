
"""CAN SLIM 七要素选股 — 欧奈尔《笑傲股市》"""
import logging
logger = logging.getLogger("aurora.canslim")

def can_slim_filter(candidates: list, market_regime: str) -> list:
    """CAN SLIM筛选: C=当季EPS A=年度EPS N=新产品 S=供需 L=领涨 I=机构 M=市场"""
    if not candidates: return []
    results = []
    for c in candidates:
        score = 0
        details = {}
        # C: 当季EPS增长 (用PE和价格变化代理)
        pe = c.get("pe", 0)
        chg = c.get("change_pct", 0)
        if 20 <= pe <= 80 and chg > 0:
            score += 15; details["c"] = 15
        elif pe > 0:
            score += 8; details["c"] = 8
        # A: 年度EPS (用PE代理)
        if 15 <= pe <= 60:
            score += 15; details["a"] = 15
        elif pe > 0:
            score += 8; details["a"] = 8
        # N: 新东西 (用涨幅代理)
        if chg > 3: score += 12; details["n"] = 12
        elif chg > 1: score += 6; details["n"] = 6
        # S: 供需 (用换手率代理)
        turnover = c.get("turnover", 0)
        if 3 <= turnover <= 10: score += 15; details["s"] = 15
        elif 1 <= turnover < 3: score += 8; details["s"] = 8
        # L: 领涨 (用量比代理)
        vr = c.get("vol_ratio", 1)
        if vr >= 2.0: score += 15; details["l"] = 15
        elif vr >= 1.5: score += 10; details["l"] = 10
        elif vr >= 1.0: score += 5; details["l"] = 5
        # I: 机构 (用市值代理 - 中等市值更受机构青睐)
        mcap = c.get("mcap", 0)
        if 100 <= mcap <= 800: score += 10; details["i"] = 10
        elif 50 <= mcap <= 100: score += 5; details["i"] = 5
        # M: 市场方向
        if market_regime.startswith("bull"): score += 15; details["m"] = 15
        elif market_regime == "range": score += 8; details["m"] = 8
        else: details["m"] = 0
        c["can_slim"] = score
        c["cs_details"] = details
        c["cs_grade"] = "A" if score >= 70 else ("B" if score >= 50 else ("C" if score >= 30 else "D"))
        if score >= 30:  # 至少30分才纳入
            results.append(c)
    results.sort(key=lambda x: x.get("can_slim", 0), reverse=True)
    logger.info(f"[CAN SLIM] {len(results)}/{len(candidates)} 通过")
    return results
