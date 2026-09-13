"""强势股筛选 — 板块轮动+资金流向+RS排名+涨停基因"""
import numpy as np
import logging
from data.sources import get_tencent_quotes, get_sector_ranking
logger = logging.getLogger("aurora.strong")


def score_strong_kline(closes, price=None, limit_lookback=60):
    """K线唯一年化强势分（供回测单标的判定, 不依赖实时板块/资金/北向, 无未来函数）。

    实盘的强势池护栏在 runner.py:166-174 用 `strong_grade∈{A,B} 或 strong_score≥70`
    拦昨收买点B。回测侧没有实时板块/资金快照（硬拉会造成未来函数 + 无网络即崩），
    故这里用"K线可观测因子"给出自洽的强势分，判定口径与实盘护栏对齐：
      strong = grade in ("A","B") 或 score >= 70。

    只取日K能算的因子（价格位置 + 动量 + 涨停基因 + 稳定性）：
      市值/换手/量比/板块热度 等实时因子不回测, 用 K 线动量代理。
    Returns:
        {"score": int, "grade": str, "strong": bool}
    """
    if closes is None or len(closes) < 30:
        return {"score": 0, "grade": "D", "strong": False}
    closes = [float(c) for c in closes]
    price = float(price) if price else float(closes[-1])

    score = 0

    # ① 趋势位置 (35): 价格在 MA20 上方 + 近20日正收益 —— 强势股的基本面
    ma20 = sum(closes[-20:]) / 20.0
    if price > ma20:
        score += 20
    elif price > ma20 * 0.98:
        score += 8

    # ② 动量 (35): 近20日累计涨幅（领涨性, 与 strong_stock 的 RS/change 同向）
    if len(closes) >= 21:
        chg20 = (closes[-1] / closes[-21] - 1.0) * 100.0
        if chg20 > 8.0:
            score += 22
        elif chg20 > 3.0:
            score += 15
        elif chg20 > 0.0:
            score += 8
        elif chg20 > -3.0:
            score += 2
        # 强下跌 → 不加分, 天然偏弱

    # ③ 涨停基因 (20): 近 lookback 日内涨停记录(≥9.5% 单日涨幅)
    look = min(limit_lookback, len(closes))
    chg_hist = np.diff(closes[-look:]) / np.maximum(closes[-look:-1], 1e-9) * 100.0
    limit_ups = int(np.sum(chg_hist >= 9.5))
    if limit_ups >= 3:
        score += 20
    elif limit_ups >= 1:
        score += 12

    # ④ 短期强度 (10): 最近5日显著上涨（昨日/今日领涨基因）
    if len(closes) >= 6:
        chg5 = (closes[-1] / closes[-6] - 1.0) * 100.0
        if chg5 > 4.0:
            score += 10
        elif chg5 > 1.0:
            score += 5

    score = int(min(max(score, 0), 100))
    grade = "A" if score >= 85 else ("B" if score >= 70 else ("C" if score >= 55 else "D"))
    strong = grade in ("A", "B") or score >= 70
    return {"score": score, "grade": grade, "strong": strong}


def screen_strong_stocks(candidates: list, northbound=None, kline_cache=None, top_sectors=None, flow_stocks=None) -> list:
    """强势股=板块强+个股领涨+资金流入+涨停基因"""
    if not candidates: return []
    
    # 0. 板块龙头过滤: 仅保留强势板块候选股
    #    ⭐ v14.49(2026-09-11): 判据必须是【东财行业名】(与候选 industry 同命名空间);
    #    修复前引擎传的是同花顺概念名(光伏玻璃/AI算力…)→ 与行业名永不交集, 实测 70/70 次 0 通过。
    #    另: 候选无行业归属数据时 fail-open 跳过(不误杀), 只告警——
    #    (根治在 data/sources.get_industry_map: 用东财 f100 给候选补 industry)
    if top_sectors is not None and len(top_sectors) > 0:
        before = len(candidates)
        with_ind = [c for c in candidates if c.get("industry")]
        if not with_ind:
            logger.warning(f"[Strong] 候选无行业归属数据({before}只) → 板块过滤 fail-open 跳过")
        else:
            hit = [c for c in with_ind if c.get("industry", "") in top_sectors]
            logger.info(f"[Strong] Sector filter: {len(hit)}/{before} passed "
                        f"(有归属{len(with_ind)}只 · 强势板块{len(top_sectors)}个)")
            if not hit:
                logger.warning("[Strong] 板块过滤 0 通过 → 返回空, 交引擎降级(资金流/裸选)")
                return []
            candidates = hit
    
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
        # ⭐ 2026-08-21 P4-B 涨停梯队扩散度 (与 hunter-v2 三链路同规则):
        #   甜点区强题材(当日涨停3~9只+有2板)内个股 +8 分; 主线过热(涨停≥10)内 -6 分
        #   实证(60交易日4806涨停): 3-9只甜点区+2.54%胜64.6% vs 10+只过热-0.33%胜48.5%
        try:
            import sys as _sys
            _h2 = r"D:\Hermes Agent CN Desktop\hunter-v2\backend"
            if _h2 not in _sys.path:
                _sys.path.insert(0, _h2)
            from news_sense import get_theme_escalation as _gte
            _es = _gte()
            _code = c.get("code", "")
            for _th, _a in _es.items():
                if _code in _a.get("codes", []):
                    if _a.get("strong"):
                        score += 8
                        c["theme_strong"] = True
                        c["theme_label"] = f"🔥强题材:{_th[:12]}"
                    elif _a.get("overheat"):
                        score -= 6
                        c["theme_strong"] = False
                        c["theme_label"] = f"⚠️主线过热:{_th[:12]}"
                    break
            else:
                c["theme_strong"] = False
            c["strong_score"] = min(score, 100)
            c["strong_grade"] = "A" if score >= 85 else ("B" if score >= 70 else ("C" if score >= 55 else "D"))
        except Exception:
            c["theme_strong"] = False
        scored.append(c)
    
    scored.sort(key=lambda x: x["strong_score"], reverse=True)
    logger.info(f"[Strong] {len(scored)} scored, grades: A={sum(1 for s in scored if s['strong_grade']=='A')} B={sum(1 for s in scored if s['strong_grade']=='B')} C={sum(1 for s in scored if s['strong_grade']=='C')} D={sum(1 for s in scored if s['strong_grade']=='D')}")
    # 仅返回A/B级强势股 (strong_score>=70, 宁缺毋滥)
    # v14.45: 板块数据缺失时门槛放宽到60(候选供昨收价信号二次筛选)
    min_score = 60 if sector_data_missing else 70
    quality = [s for s in scored if s["strong_score"] >= min_score]
    logger.info(f"[Strong] Quality filter: {len(quality)}/{len(scored)} passed (>=70)")
    return quality[:15]