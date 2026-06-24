"""板块轮动策略 v1.0 — 行业板块排名+领涨股选择
与所有个股技术策略零相关(完全不看个股K线形态)
理论依据: 约翰·墨菲多时间框架的板块优先原则 + 欧奈尔CAN SLIM的L(领涨)"""
import logging
import numpy as np
logger = logging.getLogger("aurora.sector")


def check_sector_rotation(kline_dict: dict, sector_data: list = None) -> dict:
    """板块轮动检测

    思路: 先找TOP3板块 → 再找板块内最强的股票

    条件:
    1. 板块排名前5 (涨幅/资金流向)
    2. 个股在板块内是领涨股(leader)或RS居前
    3. 个股趋势向上(MA20 > MA50)
    4. 个股成交量活跃(换手>1%)

    Args:
        kline_dict: {code: kline_df} 需要外部提供K线数据
        sector_data: get_sector_ranking()的输出

    Returns:
        {"signal": bool, "score": 0-100, "detail": str,
         "sector": str, "sector_rank": int}
    """
    result = {"signal": False, "score": 0, "detail": "",
              "sector": "", "sector_rank": 99}

    if not kline_dict:
        return result

    # 获取板块数据
    if sector_data is None:
        try:
            from data.sources import get_sector_ranking
            sector_data = get_sector_ranking(10)
        except Exception:
            return result

    if not sector_data:
        result["detail"] = "无板块数据"
        return result

    # 检查各板块及其领涨股
    best_sector = None
    best_sector_rank = 99
    best_code = None
    best_score = 0

    for rank, s in enumerate(sector_data[:5], 1):  # 只看前5板块
        sector_name = s.get("name", "")
        sector_pct = s.get("change_pct", 0)
        leader = s.get("leader", "")

        # 领涨股有在kline_dict中吗？
        if leader and leader in kline_dict:
            code = leader
        else:
            # 没领涨股数据时尝试检查所有候选股
            continue

        kline = kline_dict.get(code)
        if kline is None or len(kline) < 30:
            continue

        close = kline["close"].values.astype(np.float64)
        vol = kline["volume"].values.astype(np.float64)

        # 个股趋势检查
        ma20 = np.mean(close[-20:])
        if len(close) >= 50:
            ma50 = np.mean(close[-50:])
        else:
            ma50 = ma20 * 0.99
        if ma20 < ma50:
            continue  # 个股趋势向下，跳过

        # 成交量活跃
        turnover = vol[-1] / (np.mean(vol[-20:]) if np.mean(vol[-20:]) > 0 else 1)
        if turnover < 1.0:
            continue

        # 计算综合得分
        # 板块排名分: 排名越靠前分越高
        rank_score = max(0, (6 - rank) * 12)  # 第1名60分, 第5名12分

        # 板块涨幅分
        pct_score = min(20, max(0, sector_pct * 2))

        # 个股趋势分
        trend_pct = (ma20 / ma50 - 1) * 100
        trend_score = min(10, max(0, trend_pct * 5))

        # 量能分
        vol_score = min(10, max(0, (turnover - 1.0) * 10))

        total = rank_score + pct_score + trend_score + vol_score

        if total > best_score:
            best_score = total
            best_sector = sector_name
            best_sector_rank = rank
            best_code = code

    if best_sector and best_score >= 50:
        result.update({
            "signal": True,
            "score": min(100, int(best_score)),
            "detail": f"板块轮动: {best_sector}(#{best_sector_rank}) 领涨{best_code}",
            "sector": best_sector,
            "sector_rank": best_sector_rank,
            "code": best_code,
        })

    return result