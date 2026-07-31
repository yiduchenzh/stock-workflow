"""
A股备用数据源 — 来自技能库 a-stock-data v3.2.2
==============================================
替换已弃用的WZ/东方财富API, 零鉴权HTTP直连
集成: 同花顺北向资金 + 东财行业板块 + 同花顺热点强势股

使用方式:
    from data.fallback_sources import get_northbound_minute, get_sectors_fallback, get_hot_stocks
"""
import requests, logging, time, json
from pathlib import Path

logger = logging.getLogger("aurora.fallback")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36"

# ── 东财限流: 串行+间隔≥1s ──
_EM_LAST = [0.0]
_EM_SESSION = requests.Session()
_EM_SESSION.headers.update({"User-Agent": UA})

def _em_get(url, params=None, headers=None, timeout=15):
    """东财统一限流请求"""
    wait = 1.0 - (time.time() - _EM_LAST[0])
    if wait > 0:
        time.sleep(wait + 0.2)
    try:
        return _EM_SESSION.get(url, params=params, headers=headers or {"User-Agent": UA}, timeout=timeout)
    finally:
        _EM_LAST[0] = time.time()

# ═══════════════════════════════════════════
# 1. 同花顺北向资金 — 替代WZ北向
# ═══════════════════════════════════════════

HSGT_HEADERS = {
    "User-Agent": UA,
    "Host": "data.hexin.cn",
    "Referer": "https://data.hexin.cn/",
}

def get_northbound_minute() -> dict:
    """
    沪深股通实时分钟流向(同花顺,零鉴权)
    
    Returns:
        {hgt_yi: float(沪股通累计), sgt_yi: float(深股通累计), 
         total_yi: float(合计), direction: str(strong_inflow/inflow/neutral/outflow),
         points: int(数据点数量), complete: bool(数据是否完整)}
    """
    try:
        url = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
        r = requests.get(url, headers=HSGT_HEADERS, timeout=10)
        d = r.json()
        times = d.get("time", [])
        hgt = d.get("hgt", [])
        sgt = d.get("sgt", [])
        if not times:
            return {"total_yi": 0, "direction": "neutral", "points": 0, "complete": False}
        
        n = len(times)
        # 数据完整性: 深股通(sgt)同花顺接口只返回部分点(35/262), 用末值即可(当日累计)
        sgt_points = len(sgt) if sgt else 0
        complete = sgt_points >= 50  # <50个数据点视为不完整
        hgt_last = float(hgt[-1]) if hgt and len(hgt) > 0 else 0
        sgt_last = float(sgt[-1]) if sgt and len(sgt) > 0 else 0
        total = hgt_last + sgt_last
        
        if total > 50: direction = "strong_inflow"
        elif total > 10: direction = "inflow"
        elif total < -50: direction = "strong_outflow"
        elif total < -10: direction = "outflow"
        else: direction = "neutral"

        if not complete:
            logger.debug(f"[北向] 同花顺深股通数据点偏少: hgt={n} sgt={sgt_points}")
        
        return {"hgt_yi": hgt_last, "sgt_yi": sgt_last, "total_yi": total,
                "direction": direction, "points": n, "complete": complete}
    except Exception as e:
        logger.debug(f"[北向] 同花顺失败: {e}")
        return {"total_yi": 0, "direction": "neutral", "points": 0, "complete": False}


def get_northbound_score() -> int:
    """北向评分0-100 (替代engine._calc_northbound_score中的WZ)"""
    nb = get_northbound_minute()
    d = nb.get("direction", "neutral")
    score = 50
    if d == "strong_inflow": score += 30
    elif d == "inflow": score += 15
    elif d == "outflow": score -= 10
    elif d == "strong_outflow": score -= 25
    return max(0, min(100, score))


# ═══════════════════════════════════════════
# 2. 东财行业板块排名 — 替代get_sector_ranking
# ═══════════════════════════════════════════

SECTOR_CACHE_FILE = Path(__file__).resolve().parent.parent / "data" / "sector_cache.json"
SECTOR_CACHE_TTL = 300  # 5分钟


def get_sectors_fallback(top_n: int = 50) -> list:
    """
    东财行业板块排名(push2,零鉴权)
    
    Returns:
        [{name, code, change_pct, up_count, down_count, leader}]
    """
    # 先读缓存
    try:
        if SECTOR_CACHE_FILE.exists():
            data = json.loads(SECTOR_CACHE_FILE.read_text())
            if time.time() - data.get("ts", 0) < SECTOR_CACHE_TTL:
                return data.get("sectors", [])[:top_n]
    except: pass
    
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {"pn": "1", "pz": "100", "po": "1", "np": "1",
                  "fltt": "2", "invt": "2", "fs": "m:90+t:2",
                  "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140"}
        r = _em_get(url, params=params, timeout=15)
        d = r.json()
        items = d.get("data", {}).get("diff", [])
        if not items:
            return _load_sector_cache()[:top_n]
        
        sectors = []
        for it in items:
            sectors.append({
                "name": it.get("f14", ""),
                "code": it.get("f12", ""),
                "change_pct": it.get("f3", 0),
                "up_count": it.get("f104", 0),
                "down_count": it.get("f105", 0),
                "leader": it.get("f140", ""),
            })
        # 写缓存
        try:
            SECTOR_CACHE_FILE.write_text(json.dumps({"ts": time.time(), "sectors": sectors}))
        except: pass
        return sectors[:top_n]
    except Exception as e:
        logger.warning(f"[板块] 东财失败: {e}")
        return _load_sector_cache()[:top_n]


def _load_sector_cache() -> list:
    """读缓存"""
    try:
        if SECTOR_CACHE_FILE.exists():
            return json.loads(SECTOR_CACHE_FILE.read_text()).get("sectors", [])
    except: pass
    return []


# ═══════════════════════════════════════════
# 3. 同花顺热点强势股 — 日内强势股+题材归因
# ═══════════════════════════════════════════

def get_hot_stocks(date: str = None) -> list:
    """
    同花顺当日强势股(含题材归因), 零鉴权73ms
    
    Returns:
        [{code, name, reason(题材归因), zhangfu(涨幅%), huanshou(换手%), 
          chengjiaoe(成交额), dde(大单净量)}]
    """
    from datetime import date as _date
    if date is None:
        date = _date.today().strftime("%Y-%m-%d")
    
    try:
        url = f"http://zx.10jqka.com.cn/event/api/getharden/date/{date}/orderby/date/orderway/desc/charset/GBK/"
        r = requests.get(url, headers={"User-Agent": UA}, timeout=10)
        d = r.json()
        if d.get("errocode", 0) != 0:
            logger.warning(f"[热点] 同花顺错误: {d.get('errormsg','')}")
            return []
        
        rows = d.get("data") or []
        result = []
        for item in rows:
            result.append({
                "code": item.get("code", ""),
                "name": item.get("name", ""),
                "reason": item.get("reason", ""),
                "zhangfu": item.get("zhangfu", 0),
                "huanshou": item.get("huanshou", 0),
                "chengjiaoe": item.get("chengjiaoe", 0),
                "dde": item.get("ddejingliang", 0),
                "close": item.get("close", 0),
            })
        logger.info(f"[热点] 同花顺强势股: {len(result)}只")
        return result
    except Exception as e:
        logger.debug(f"[热点] 同花顺失败: {e}")
        return []


def get_hot_sectors() -> list:
    """
    从热点股自动归纳今日热门板块
    
    Returns:
        [{tag, count, stocks: [{code, name, zhangfu}]}]
    """
    hot = get_hot_stocks()
    if not hot:
        return []
    
    from collections import Counter
    tag_stocks = {}
    for s in hot:
        reason = s.get("reason", "")
        if not reason:
            continue
        tags = [t.strip() for t in reason.split("+") if t.strip()]
        for tag in tags:
            if tag not in tag_stocks:
                tag_stocks[tag] = []
            tag_stocks[tag].append({"code": s["code"], "name": s["name"], "zhangfu": s["zhangfu"]})
    
    result = []
    for tag, stocks in sorted(tag_stocks.items(), key=lambda x: -len(x[1])):
        result.append({"tag": tag, "count": len(stocks), "stocks": stocks[:5]})
    return result[:20]
