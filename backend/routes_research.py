"""个股深度研究 — Equity Research API"""
import os, json, sys, urllib.request, logging
from datetime import datetime

logger = logging.getLogger("aurora.research")

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ)

from fastapi import APIRouter

router = APIRouter()

def _get_kline_sma(code):
    """获取K线数据并计算技术指标; 附带 _closes(新→旧) 供风险指标复用同一份真实数据."""
    try:
        from data.sina_sources import get_klines
        klines = get_klines(code, ktype="D", days=60)
        closes = [k["close"] for k in (klines or []) if k.get("close")]
        out = {"_closes": closes}
        if len(closes) > 20:
            ma5 = sum(closes[:5]) / 5 if len(closes) >= 5 else 0
            ma20 = sum(closes[:20]) / 20 if len(closes) >= 20 else 0
            ma60 = sum(closes[:min(60, len(closes))]) / min(60, len(closes))
            current = closes[0] if closes else 0
            prev = closes[min(19, len(closes) - 1)]
            change_20d = (closes[0] - prev) / prev * 100 if len(closes) > 19 and prev else 0
            out.update({
                "price": current, "ma5": round(ma5, 2), "ma20": round(ma20, 2),
                "ma60": round(ma60, 2), "change_20d": round(change_20d, 2),
            })
        # 若完全没拉到K线则不返回(网络失败如实无数据)
        return out if closes else None
    except Exception:
        return None


def _compute_risk_metrics(closes, price):
    """基于真实历史收盘价序列(旧→新)计算风险指标; 数据不足返回各字段 None, 绝不硬编码.

    - volatility_20d: 最近20个日简单收益率的标准差 ×100 (百分比)
    - var_95: 历史5%分位日收益对应的单日亏损金额 = max(0, -p5) × price (正值亏损额)
    - score: 0-100 风险分, 由真实 volatility + 最大回撤推得(非恒定)
    """
    try:
        import numpy as np
    except Exception:  # noqa: BLE001
        return {"volatility_20d": None, "var_95": None, "score": None}
    series = [float(c) for c in (closes or []) if c is not None]
    if price is None or not price or price <= 0 or len(series) < 21:
        return {"volatility_20d": None, "var_95": None, "score": None}
    arr = np.asarray(series, dtype=float)
    rets = arr[1:] / arr[:-1] - 1.0                # 日简单收益率
    if len(rets) < 20:
        return {"volatility_20d": None, "var_95": None, "score": None}
    ret_20 = rets[-20:]
    vol20 = float(np.std(ret_20, ddof=1)) * 100.0   # 20日收益标准差(百分比)
    p5 = float(np.percentile(ret_20, 5))            # 历史5%分位日收益(负值)
    var_95_amount = round(max(0.0, -p5) * price, 2)  # 单日 VaR 金额(正值亏损额)
    # 最大回撤(取整个序列)
    peak = arr[0]
    max_dd = 0.0
    for c in arr:
        peak = max(peak, c)
        if peak > 0:
            max_dd = max(max_dd, (peak - c) / peak)
    # 风险评分 0-100: 日波动3%打满(权重0.6) + 回撤50%打满(权重0.4)
    daily_vol = vol20 / 100.0
    vol_term = min(daily_vol / 0.03, 1.0)
    dd_term = min(max_dd / 0.5, 1.0)
    score = round((0.6 * vol_term + 0.4 * dd_term) * 100, 0)
    return {
        "volatility_20d": round(vol20, 2),
        "var_95": var_95_amount,
        "score": max(0, min(100, int(score))),
        "annual_vol_20d": round(vol20 * (252 ** 0.5) / 100.0, 2) if vol20 else None,
    }

@router.get("/api/research/{code}")
async def stock_research(code: str):
    """个股深度研究 — 估值/技术面/基本面"""
    result = {"code": code, "updated_at": datetime.now().isoformat()}
    
    # 用腾讯实时行情获取价格
    try:
        if code.startswith(("6","9")):
            tcode = "sh" + code
        else:
            tcode = "sz" + code
        r = urllib.request.urlopen(f"http://qt.gtimg.cn/q={tcode}", timeout=5)
        raw = r.read().decode("gbk")
        p = raw.split("~")
        if len(p) > 32:
            name = p[1]
            price = float(p[3]) if p[3] else 0
            high = float(p[4]) if p[4] else 0
            low = float(p[5]) if p[5] else 0
            volume = int(p[6]) if p[6] else 0
            amount = float(p[7]) if p[7] else 0
            open_p = float(p[8]) if p[8] else 0
            result.update({
                "name": name, "price": price, "open": open_p,
                "high": high, "low": low, "volume": volume, "amount": amount,
            })
    except:
        pass
    
    # 计算技术指标
    tech = _get_kline_sma(code)
    if tech:
        result["technicals"] = tech
        p = result.get("price", tech.get("price", 0))
        result["technicals"].update({
            "above_ma5": p > tech.get("ma5", 0) if tech.get("ma5") else None,
            "above_ma20": p > tech.get("ma20", 0) if tech.get("ma20") else None,
        })
    
    # 估值数据 (真实基本面落库读取; 读不到返回 None, 不回填模拟值)
    p = result.get("price", 0)
    fund = {}
    try:
        from data.fundamentals_store import get_fundamentals, refresh_fundamentals
        fund = get_fundamentals(code) or {}
        # D-1 修复: 首次访问某 code 且落库无该股/无真实值时, 自动补拉并落库。
        # 仅单 code 刷新, 网络失败由 refresh_fundamentals 内部降级返回空并打日志, 不伪造。
        if not fund:
            logger.info(f"[research/{code}] 基本面落库无该股, 自动 refresh_fundamentals 补拉(单code)")
            try:
                refresh_fundamentals([code])
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[research/{code}] 自动补拉基本面失败: {e}")
            fund = get_fundamentals(code) or {}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[research/{code}] 读取基本面落库失败: {e}")
        fund = {}
    if not fund:
        logger.warning(f"[research/{code}] fundamentals 落库无该股或未刷到真实值,pe_ttm/pb 返回 None")
    pe_ttm = fund.get("pe_ttm")
    pb = fund.get("pb")
    result["valuation"] = {
        "pe_ttm": pe_ttm,          # 真实落库(腾讯), 拉不到为 None
        "pb": pb,                  # 真实落库(腾讯), 拉不到为 None
        "market_cap": fund.get("market_cap"),
        # D-2 修复: DCF 模型尚未接入真实计算, 如实返回 None, 不伪装/硬编码成估算值
        # (原实现 round(p*1.3)/round(p*0.85) 是把估算值伪装成模型估值输出, 已移除)
        "dcf_value_high": None,
        "dcf_value_low": None,
    }

    # 板块多对多归属 (stock_sector 落库读取 + 首次访问用东财概念板块补齐真实值)
    sectors = []
    sector_fill = None
    try:
        from data.fundamentals_store import get_stock_sectors, ensure_sector_membership
        # 首次访问该 code 时, 若 stock_sector 为空则尝试从真实数据源补齐(网络受限则留空)
        sector_fill = ensure_sector_membership(code)
        sectors = get_stock_sectors(code)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[research/{code}] 板块归属读取失败: {e}")
        sectors = []
    result["sector"] = {"list": sectors, "names": [s["sector"] for s in sectors],
                        "fill_status": sector_fill or ("populated" if sectors else "empty")}

    # 风险指标: 用真实历史K线收盘价计算; 数据不足返回 None, 不硬编码 (治理 D-3)
    risk = {"volatility_20d": None, "var_95": None, "score": None}
    try:
        closes_new_first = (tech or {}).get("_closes") or []
        if closes_new_first:
            # _closes 为 新→旧, 反转成 旧→新 供真实收益计算
            risk = _compute_risk_metrics(list(reversed(closes_new_first)), p)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[research/{code}] 风险指标计算失败: {e}")
        risk = {"volatility_20d": None, "var_95": None, "score": None}
    result["risk"] = risk
    
    return result
