"""
三级联动选股 — 大盘→板块→个股
集成 AI Berkshire 质量预筛 (v3.1)
集成基本面数据源 (financial_sources v1.0)
v2.0: cascade_screen 增加 phase 参数, 晨扫放宽换手率/量比过滤 (2026-07-03)
"""
import logging
from data.sources import get_tencent_quotes, get_real_stock_list, get_sector_ranking
from screening.berkshire_filter import berkshire_full_filter
from data.financial_sources import enrich_batch

logger = logging.getLogger("aurora.screen")


def cascade_screen(cfg: dict, phase: str = "monitor") -> list:
    """三级联动选股 — 大盘→板块→个股
    Args:
        cfg: 配置字典
        phase: 运行阶段 ('morning'/'monitor'/'auction'/etc)
              晨扫(09:35)开盘刚成交, 换手率/量比数据不充分, 放宽过滤
    """
    screen_cfg = cfg.get("screening", {})
    coarse = screen_cfg.get("coarse", {})
    berkshire_cfg = screen_cfg.get("berkshire", {})

    # Get stock list and batch quotes
    codes = get_real_stock_list()
    if not codes:
        logger.warning("无法获取股票列表")
        return []

    # Batch query (limit to avoid API overload)
    batch = codes[:6000]  # 沪深京全市场
    quotes = get_tencent_quotes(batch)
    candidates = []
    for code, q in quotes.items():
        pe = q.get("pe", 0)
        mcap = q.get("mcap", 0)
        turnover = q.get("turnover", 0)
        vr = q.get("vol_ratio", 0)
        name = q.get("name", "")

        # Coarse filter: PE
        if pe <= coarse.get("min_pe", 0) or pe > coarse.get("max_pe", 200):
            continue
        # Coarse filter: 市值
        if mcap < coarse.get("min_mcap_yi", 20) or mcap > coarse.get("max_mcap_yi", 20000):
            continue
        # Coarse filter: 换手率 + 量比（晨扫阶段放宽）
        if phase == "morning":
            # 晨扫: 开盘刚5分钟, 换手率数据不充分, 使用宽松阈值
            min_t = coarse.get("morning_min_turnover", 0.05)
            min_v = coarse.get("morning_min_vol_ratio", 0.1)
            if turnover < min_t:
                continue
            if vr < min_v:
                continue
        else:
            min_t = coarse.get("min_turnover", 0.3)
            min_v = coarse.get("min_vol_ratio", 0.5)
            if turnover < min_t:
                continue
            if vr < min_v:
                continue
        # Coarse filter: ST
        if coarse.get("exclude_st", True) and "ST" in name:
            continue
        # Coarse filter: 价格上限
        max_p = coarse.get("max_price", 0)
        price = q.get("price", 0)
        if max_p > 0 and price > max_p:
            continue
        candidates.append(q)

    # Sort by vol_ratio (liquidity proxy)
    candidates.sort(key=lambda x: x.get("vol_ratio", 0), reverse=True)
    logger.info(f"[选股] {len(candidates)}/{len(quotes)} 通过粗筛 (phase={phase})")

    # 截取前300只最活跃的进入后续环节 (enrich_batch对数千只超时)
    candidates_before_berkshire = len(candidates)
    candidates_before_berkshire_cut = candidates[:]
    candidates = candidates[:300]

    # ── AI Berkshire 质量预筛 ──
    if berkshire_cfg.get("enabled", False):
        mode = berkshire_cfg.get("mode", "prefilter")
        if mode == "prefilter":
            # Step 1: Enrich with fundamental financial data
            logger.info(f"[Berkshire] 获取基本面数据 for {len(candidates)} candidates...")
            candidates = enrich_batch(candidates)
            with_fin = sum(1 for s in candidates if s.get("roe_10yr") is not None)
            logger.info(f"[Berkshire] 基本面数据: {with_fin}/{len(candidates)} 有数据")

            # Step 2: Run Berkshire quality filter
            candidates_before_filter = len(candidates)
            candidates, report = berkshire_full_filter(candidates, cfg)
            if not candidates and candidates_before_filter > 0:
                logger.warning(f"[Berkshire] 全部{candidates_before_filter}只被过滤,降级为原始候选(未过Berkshire)")
                candidates = candidates_before_berkshire_cut
            logger.info(
                f"[Berkshire] 质量预筛: {report['passed']} 通过 "
                f"(否决{report['vetoed']}, 质量淘汰{report['quality_failed']}) "
                f"A:{report['grade_distribution'].get('A',0)} "
                f"B:{report['grade_distribution'].get('B',0)} "
                f"C:{report['grade_distribution'].get('C',0)}"
            )

    return candidates[:50]
