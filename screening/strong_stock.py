"""强势股筛选 — 板块轮动+资金流向+RS排名+涨停基因"""
import numpy as np
import logging
from data.sources import get_tencent_quotes, get_sector_ranking
logger = logging.getLogger("aurora.strong")

def screen_strong_stocks(candidates: list, northbound=None, kline_cache=None) -> list:
    """强势股=板块强+个股领涨+资金流入+涨停基因"""
    if not candidates: return []
    
    # 1. 板块轮动热度
    sectors = get_sector_ranking(100) or []
    sector_heat = {s["name"]: s.get("change_pct", 0) for s in sectors}
    # 板块涨幅排名(百分位)
    sector_names = list(sector_heat.keys())
    
    # 2. 对每只候选计算强势分
    scored = []
    for c in candidates:
        score = 50  # 基准
        
        # 板块热度 (25分): 板块涨幅排前-加分, 排后-降分
        ind = c.get("industry", "")
        heat = sector_heat.get(ind, 0)
        if heat >= 3: score += 20
        elif heat >= 1.5: score += 12
        elif heat >= 0: score += 5
        elif heat > -1.5: score -= 5
        else: score -= 15
        
        # RS相对强度 (20分): 个股涨幅 vs 板块涨幅
        stock_chg = c.get("change_pct", 0)
        if stock_chg > heat and stock_chg > 0: score += 18  # 领涨
        elif stock_chg > 0: score += 10  # 跟涨
        elif stock_chg > -2: score += 3
        else: score -= 10
        
        # 量能活跃度 (20分): 换手率+量比
        turnover = c.get("turnover", 0); vr = c.get("vol_ratio", 1)
        if 3 <= turnover <= 10 and vr >= 2.0: score += 18
        elif 2 <= turnover <= 10 and vr >= 1.5: score += 12
        elif 1 <= turnover and vr >= 1.0: score += 6
        
        # 北向资金偏好 (15分)
        nb_score = 0
        if northbound and northbound.get("direction") in ("inflow", "strong_inflow"):
            # 北向流入时大盘股更受益
            mcap = c.get("mcap", 50)
            if mcap > 200: nb_score = 12
            elif mcap > 100: nb_score = 8
        score += nb_score
        
        # 涨停基因 (10分): 近期是否有涨停记录
        if kline_cache:
            kline = kline_cache.get(c.get("code"))
            if kline is not None and len(kline) >= 20:
                close_vals = kline["close"].values; chg_history = np.diff(close_vals[-61:]) / close_vals[-61:-1] * 100
                limit_ups = sum(1 for ch in chg_history if ch >= 9.5)
                if limit_ups >= 3: score += 10
                elif limit_ups >= 1: score += 6
        
        # 价格位置 (10分): 在MA20之上更健康
        if kline_cache:
            kline = kline_cache.get(c.get("code"))
            if kline is not None and len(kline) >= 20:
                price = c.get("price", 0)
                ma20 = np.mean(kline["close"].values[-20:])
                if price > ma20: score += 10
                elif price > ma20 * 0.95: score += 3
                else: score -= 5
        
        c["strong_score"] = min(score, 100)
        c["strong_grade"] = "A" if score >= 80 else ("B" if score >= 65 else ("C" if score >= 50 else "D"))
        scored.append(c)
    
    scored.sort(key=lambda x: x["strong_score"], reverse=True)
    logger.info(f"[Strong] {len(scored)} scored, grades: A={sum(1 for s in scored if s['strong_grade']=='A')} B={sum(1 for s in scored if s['strong_grade']=='B')}")
    return scored[:20]