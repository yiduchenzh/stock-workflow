
"""三级联动选股 — 大盘→板块→个股"""
import logging
from data.sources import get_tencent_quotes, get_real_stock_list, get_sector_ranking
logger = logging.getLogger("aurora.screen")

def cascade_screen(cfg: dict) -> list:
    screen_cfg = cfg.get("screening", {})
    coarse = screen_cfg.get("coarse", {})
    # Get stock list and batch quotes
    codes = get_real_stock_list()
    if not codes:
        logger.warning("无法获取股票列表")
        return []
    # Batch query (limit to avoid API overload)
    batch = codes[:500]
    quotes = get_tencent_quotes(batch)
    candidates = []
    for code, q in quotes.items():
        pe = q.get("pe", 0); mcap = q.get("mcap", 0)
        turnover = q.get("turnover", 0); vr = q.get("vol_ratio", 0)
        name = q.get("name", "")
        # Coarse filter
        if pe <= coarse.get("min_pe", 0) or pe > coarse.get("max_pe", 200): continue
        if mcap < coarse.get("min_mcap_yi", 20) or mcap > coarse.get("max_mcap_yi", 1000): continue
        if turnover < coarse.get("min_turnover", 1.0): continue
        if vr < coarse.get("min_vol_ratio", 0.8): continue
        if coarse.get("exclude_st", True) and "ST" in name: continue
        candidates.append(q)
    # Sort by vol_ratio (liquidity proxy)
    candidates.sort(key=lambda x: x.get("vol_ratio", 0), reverse=True)
    logger.info(f"[选股] {len(candidates)}/{len(quotes)} 通过粗筛")
    return candidates[:20]
