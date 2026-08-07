"""强势股筛选 — 板块轮动+资金流向+RS排名+涨停基因"""
import numpy as np
import logging
from data.sources import get_tencent_quotes, get_sector_ranking
logger = logging.getLogger("aurora.strong")

def screen_strong_stocks(candidates: list, northbound=None, kline_cache=None, top_sectors=None, flow_stocks=None) -> list:
    """强势股=板块强+个股领涨+资金流入+涨停基因"""
    if not candidates: return []
    
    # 0. 板块龙头过滤: 仅保留板块涨幅TOP5候选股
    if top_sectors is not None and len(top_sectors) > 0:
        before = len(candidates)
        candidates = [c for c in candidates if c.get("industry", "") in top_sectors]
        logger.info(f"[Strong] Sector top5 filter: {len(candidates)}/{before} passed")
        if not candidates: return []
    
    # 0b. 资金净流入过滤: 仅保留主力净流入TOP200候选股
    if flow_stocks is not None and len(flow_stocks) > 0:
        before = len(candidates)
        candidates = [c for c in candidates if c.get("code", "") in flow_stocks]
        logger.info(f"[Strong] Capital flow top200 filter: {len(candidates)}/{before} passed")
        if not candidates: return []
    
    # 1. 板块轮动热度
    sectors = get_sector_ranking(100) or []
    sector_heat = {s["name"]: s.get("change_pct", 0) for s in sectors}
    # 板块涨幅排名(百分位)
    sector_names = list(sector_heat.keys())
    # v14.45: 板块数据缺失降级 — 无板块数据时不扣分(否则所有候选都被D级淘汰)
    sector_data_missing = len(sector_heat) == 0
    
    # 2. 对每只候选计算强势分
    scored = []
    for c in candidates:
        score = 50  # 基准
        
        # 板块热度 (25分): 板块涨幅排前-加分, 排后-降分
        ind = c.get("industry", "")
        heat = sector_heat.get(ind, 0)
        if sector_data_missing:
            score += 15  # 降级: 无板块数据给中性偏上分(不淘汰)
        elif heat >= 3: score += 20
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
        
        # 北向资金评分 (25分): 整体流入方向+重仓个股
        nb_score = 0
        if northbound and northbound.get("direction") in ("inflow", "strong_inflow"):
            nb_score += 15  # 北向整体流入加分
            # 北向重仓近似: 换手率>3%+市值>500亿 ≈ 北向重仓TOP100个股
            mcap = c.get("mcap", 50)
            if turnover > 3 and mcap > 500:
                nb_score += 10  # 北向重仓额外加分
        score += nb_score
        
        # 涨停基因+龙虎榜评分 (18分): 涨停记录+近期大涨
        if kline_cache:
            kline = kline_cache.get(c.get("code"))
            if kline is not None and len(kline) >= 20:
                close_vals = kline["close"].values; chg_history = np.diff(close_vals[-61:]) / close_vals[-61:-1] * 100
                # 涨停基因 (10分): 近期涨停记录
                limit_ups = sum(1 for ch in chg_history if ch >= 9.5)
                if limit_ups >= 3: score += 10
                elif limit_ups >= 1: score += 6
                # 龙虎榜评分 (8分): 最近一日涨停或涨幅>5%
                latest_chg = chg_history[-1] if len(chg_history) >= 1 else 0
                if latest_chg >= 9.5 or latest_chg > 5:
                    score += 8
        
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
        c["strong_grade"] = "A" if score >= 85 else ("B" if score >= 70 else ("C" if score >= 55 else "D"))
        scored.append(c)
    
    scored.sort(key=lambda x: x["strong_score"], reverse=True)
    logger.info(f"[Strong] {len(scored)} scored, grades: A={sum(1 for s in scored if s['strong_grade']=='A')} B={sum(1 for s in scored if s['strong_grade']=='B')} C={sum(1 for s in scored if s['strong_grade']=='C')} D={sum(1 for s in scored if s['strong_grade']=='D')}")
    # 仅返回A/B级强势股 (strong_score>=70, 宁缺毋滥)
    # v14.45: 板块数据缺失时门槛放宽到60(候选供昨收价信号二次筛选)
    min_score = 60 if sector_data_missing else 70
    quality = [s for s in scored if s["strong_score"] >= min_score]
    logger.info(f"[Strong] Quality filter: {len(quality)}/{len(scored)} passed (>=70)")
    return quality[:15]