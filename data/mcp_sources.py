"""
MCP 数据源适配器 — 行业板块数据补充
=====================================
东财 push2 板块排名API被WAF阻断(2026-07起持续),
启用同花顺热点API作为替代数据源.

数据链:
  1. 同花顺热点题材归因(零鉴权,73ms) → 自动归纳热门板块
  2. 同花顺热点个股 → 板块涨跌感知
  3. 缓存 → 静态默认

quanters-akshare MCP服务器安装后可备选(但东财WAF同样阻断Node.js).
"""
import logging, time
logger = logging.getLogger("aurora.mcp")


def get_sectors_via_mcp(top_n: int = 20) -> list:
    """
    获取行业板块排名 — 基于同花顺热点题材归纳.

    同花顺热点返回当日强势股+题材标签(reason tags),
    按题材归类统计出热门板块, 比东财纯涨跌幅排名更有信息量.

    Returns:
        [{name: 板块名, change_pct: 0(无涨跌幅), count: 关联个股数, hot: 最高涨幅,
          stocks: [{code, name, zhangfu}], source: "ths_hot"}]
    """
    try:
        from data.fallback_sources import get_hot_sectors
        hot = get_hot_sectors()
        if not hot:
            logger.warning("[MCP Sector] 同花顺热点为空")
            return _use_cache_or_default(top_n)

        sectors = []
        for h in hot[:top_n]:
            sectors.append({
                "name": h.get("tag", ""),
                "change_pct": 0,  # 同花顺热点不提供板块涨跌幅
                "count": h.get("count", 0),
                "hot": max((s.get("zhangfu", 0) for s in h.get("stocks", [])), default=0),
                "stocks": h.get("stocks", [])[:3],
                "source": "ths_hot",
            })

        logger.info(f"[MCP Sector] {len(sectors)} sectors from 同花顺热点")
        return sectors

    except Exception as e:
        logger.warning(f"[MCP Sector] 同花顺失败: {e}")
        return _use_cache_or_default(top_n)


def _use_cache_or_default(top_n: int = 20) -> list:
    """缓存或默认降级"""
    try:
        from data.sources import _load_sector_cache
        cached = _load_sector_cache()
        if cached:
            logger.info(f"[MCP Sector] Using cached ({len(cached)} sectors)")
            return cached[:top_n]
    except:
        pass
    logger.warning("[MCP Sector] 所有源失败,用静态默认")
    from data.sources import DEFAULT_SECTORS
    return DEFAULT_SECTORS[:top_n]


def get_sector_ranking_mcp(top_n: int = 50) -> list:
    """
    统一入口 — 替代东财HTTP直连的版块排名.
    返回格式兼容 sources.get_sector_ranking().
    """
    hot_sectors = get_sectors_via_mcp(top_n)
    if hot_sectors and hot_sectors[0].get("source") == "ths_hot":
        return hot_sectors
    return _use_cache_or_default(top_n)


# 兼容旧名
get_sectors = get_sector_ranking_mcp
