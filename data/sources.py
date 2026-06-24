
"""数据源 — 歪枣网(主力) + 腾讯/东财(备用), 三级降级"""
import os as _os
_data_sources_tried_wz = False

def _try_wz_first(fn_name, *args, **kwargs):
    """尝试歪枣网优先, 失败则返回None"""
    global _data_sources_tried_wz
    try:
        if not _data_sources_tried_wz:
            import data.wz_sources as _wz
            _data_sources_tried_wz = True
        import data.wz_sources as _wz
        fn = getattr(_wz, fn_name, None)
        if fn:
            result = fn(*args, **kwargs)
            if result is not None and (hasattr(result, "__len__") and len(result) > 0) or (not hasattr(result, "__len__")):
                return result
    except Exception as e:
        pass
    return None

import urllib.request, json, time, logging
from pathlib import Path
import pandas as pd

logger = logging.getLogger("aurora.data")
UA = "Mozilla/5.0"

def _prefix(code):
    return f"sh{code}" if code.startswith(("6","9")) else f"sz{code}"

def get_tencent_quotes(codes: list) -> dict:
    """实时行情 — 优先歪枣网, 腾讯备用"""
    wz_q = _try_wz_first("get_quotes", codes)
    if wz_q and len(wz_q) > 0:
        return wz_q
    # Fallback to original tencent logic below
    """腾讯批量行情 — 不封IP, 主力数据源"""
    if not codes: return {}
    prefixed = [_prefix(c) for c in codes[:80]]
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        data = urllib.request.urlopen(req, timeout=10).read().decode("gbk", errors="replace")
    except Exception as e:
        logger.warning(f"腾讯行情失败: {e}")
        return {}
    result = {}
    for line in data.strip().split(";"):
        if "=" not in line or '"' not in line: continue
        key = line.split("=")[0].split("_")[-1]; vals = line.split('"')[1].split("~")
        if len(vals) < 53: continue
        code = key[2:]
        result[code] = {
            "code": code, "name": vals[1],
            "price": float(vals[3]) if vals[3] else 0,
            "change_pct": float(vals[32]) if vals[32] else 0,
            "pe": float(vals[39]) if vals[39] else 0,
            "mcap": float(vals[44]) if vals[44] else 0,
            "turnover": float(vals[38]) if vals[38] else 0,
            "vol_ratio": float(vals[49]) if vals[49] else 0,
            "pb": float(vals[46]) if vals[46] else 0,
        }
    return result

def _fallback_stock_list() -> list:
    return [
        "000001","000002","000333","000568","000625","000651","000725","000733","000768","000792",
        "000858","000938","000983","001979","002007","002049","002129","002230","002236","002241",
        "002304","002352","002371","002415","002459","002460","002466","002475","002493","002594",
        "002601","002709","002714","002812","002920","002938","300014","300015","300059","300124",
        "300274","300308","300413","300433","300450","300502","300661","300750","300751","300760",
        "300782","300999","600000","600010","600011","600016","600019","600025","600028","600030",
        "600031","600036","600048","600050","600085","600089","600104","600111","600115",
        "600150","600188","600196","600276","600309","600340","600346","600362","600406","600436",
        "600438","600482","600487","600519","600522","600536","600570","600585","600588","600690",
        "600703","600732","600745","600809","600886","600887","600893","600900","600919","600926",
        "600941","600958","600989","600999","601012","601066","601088","601111","601127","601138",
        "601166","601169","601186","601211","601216","601225","601229","601236","601288","601318",
        "601328","601336","601360","601377","601390","601398","601600","601601","601607","601615",
        "601618","601628","601633","601658","601669","601688","601689","601728","601766","601788",
        "601800","601818","601857","601872","601877","601878","601881","601888","601899","601901",
        "601919","601939","601958","601966","601985","601988","601989","601990","601992","601995",
        "603019","603195","603259","603288","603369","603392","603501","603659","603799","603986",
        "605117","688008","688009","688012","688036","688065","688111","688126","688169","688180",
        "688187","688200","688256","688303","688347","688363","688396","688469","688488","688516",
        "688520","688533","688536","688599","688660","688728","688766","688777","688819","688981",
    ]

def _sina_stock_list() -> list:
    import requests as req
    codes = []
    nodes = {'sh_a': '6', 'sz_a': '0', 'cyb': '3'}
    for node, _ in nodes.items():
        for pn in range(1, 5):
            try:
                url = 'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData'
                r = req.get(url, params={'page': pn, 'num': 100, 'sort': 'code', 'asc': '1', 'node': node}, timeout=10)
                items = r.json() if isinstance(r.json(), list) else []
                chunk = [it['code'] for it in items if isinstance(it, dict) and len(it.get('code','')) == 6]
                codes.extend(chunk)
                if len(items) < 100: break
            except Exception: break
    logger.info(f'[Sina] {len(codes)} codes fallback')
    return codes if codes else _fallback_stock_list()

def get_real_stock_list() -> list:
    wz_list = _try_wz_first("get_stock_list")
    if wz_list and len(wz_list) > 100:
        return wz_list
    import requests as req
    import json as _j
    # Check cache
    try:
        if STOCK_CACHE.exists():
            data = _j.loads(STOCK_CACHE.read_text())
            if __import__("time").time() - data.get("time", 0) < STOCK_CACHE_TTL:
                logger.info(f"[Cache] {len(data.get('codes',[]))} stocks ({(STOCK_CACHE_TTL - (__import__("time").time() - data['time'])):.0f}s TTL)")
                return data["codes"]
    except Exception:
        pass
    
    codes = []
    for fs in ['m:0+t:6,m:0+t:80', 'm:1+t:2,m:1+t:23']:
        for pn in range(1, 6):
            try:
                url = 'https://push2.eastmoney.com/api/qt/clist/get'
                r = req.get(url, params={'pn': pn, 'pz': 100, 'po': 1, 'np': 1, 'fltt': 2, 'invt': 2, 'fs': fs, 'fields': 'f12'},
                           headers={'User-Agent': UA, 'Referer': 'https://quote.eastmoney.com/'}, timeout=10)
                items = r.json().get('data', {}).get('diff', []) or []
                chunk = [it['f12'] for it in items if len(str(it.get('f12',''))) == 6]
                codes.extend(chunk)
                if len(items) < 100: break
            except Exception as e:
                logger.warning(f'EM p{pn} fail({e}), retry once')
                __import__("time").sleep(2.0)
                try:
                    r2 = req.get(url, params={'pn': pn, 'pz': 100, 'po': 1, 'np': 1, 'fltt': 2, 'invt': 2, 'fs': fs, 'fields': 'f12'},
                               headers={'User-Agent': UA, 'Referer': 'https://quote.eastmoney.com/'}, timeout=10)
                    items2 = r2.json().get('data', {}).get('diff', []) or []
                    chunk = [it['f12'] for it in items2 if len(str(it.get('f12',''))) == 6]
                    if chunk:
                        codes.extend(chunk)
                        if len(items2) < 100: break
                        continue
                except Exception:
                    pass
                logger.warning(f'EM p{pn} retry also failed')
                break
    if codes:
        result = list(dict.fromkeys(codes))
        logger.info(f'[EM] {len(result)} stocks')
        # Save to cache
        try:
            STOCK_CACHE.write_text(_j.dumps({"time": __import__("time").time(), "codes": result}))
        except Exception:
            pass
        return result
    logger.warning('EM fail, try Sina')
    codes = _sina_stock_list()
    if codes:
        try:
            STOCK_CACHE.write_text(_j.dumps({"time": __import__("time").time(), "codes": codes}))
        except Exception:
            pass
    return codes


def get_kline_period(code: str, period: str = "day", days: int = 250) -> pd.DataFrame:
    """多周期K线: day/week/month — 真实数据来自腾讯"""
    import requests as req
    pfx = _prefix(code)
    period_map = {"day": "day", "week": "week", "month": "month"}
    p = period_map.get(period, "day")
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={pfx},{p},,,{days},qfq"
    try:
        r = req.get(url, headers={"User-Agent": UA}, timeout=10)
        data = r.json().get("data", {}).get(pfx, {})
        keys = {"day": "qfqday", "week": "qfqweek", "month": "qfqmonth"}
        raw = data.get(keys.get(p, "qfqday"), [])
        if not raw: raw = data.get(p, [])
        if not raw: return __import__("pandas").DataFrame()
        rows = []
        for d in raw:
            rows.append({"date": str(d[0]), "open": float(d[1]), "close": float(d[2]),
                        "high": float(d[3]), "low": float(d[4]), "volume": float(d[5]) if len(d)>5 else 0})
        df = __import__("pandas").DataFrame(rows)
        df["date"] = __import__("pandas").to_datetime(df["date"])
        return df
    except Exception as e:
        logger.warning(f"K线获取失败 {code} {period}: {e}")
        return __import__("pandas").DataFrame()


def get_index_snapshot(codes):
    """获取指数快照"""
    idx_map = {"000001":"sh000001","399001":"sz399001","399006":"sz399006","000688":"sh000688","000300":"sh000300"}
    mapped = [idx_map.get(c,_prefix(c)+c) for c in codes]
    if not mapped: return {}
    import urllib.request
    url = "https://qt.gtimg.cn/q=" + ",".join(mapped)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        data = urllib.request.urlopen(req, timeout=10).read().decode("gbk","replace")
    except Exception as e:
        logger.warning(f"Index fail: {e}")
        return {}
    result = {}
    for line in data.strip().split(";"):
        if "=" not in line: continue
        parts = line.split("=")
        key = parts[0].split("_")[-1]
        if '"' not in parts[1]: continue
        vals = parts[1].split('"')[1].split("~")
        if len(vals) < 3: continue
        c2 = key[2:] if key[:2] in ("sh","sz") else key
        result[c2] = {"code":c2,"name":vals[1],"price":float(vals[3]) if vals[3] else 0,"change_pct":float(vals[32]) if len(vals)>32 and vals[32] else 0}
    return result


def get_market_breadth() -> dict:
    """市场广度: 涨跌比 — 歪枣网为主, 腾讯备用"""
    wz_mb = _try_wz_first("get_market_breadth")
    if wz_mb and wz_mb.get("up_count",0) + wz_mb.get("down_count",0) > 0:
        return wz_mb
    try:
        quotes = get_tencent_quotes(get_real_stock_list()[:100])
        if not quotes: return {"ad_score": 0, "up_count": 0, "down_count": 0}
        changes = [q.get("change_pct", 0) for q in quotes.values()]
        up = sum(1 for c in changes if c > 0)
        down = sum(1 for c in changes if c < 0)
        total = up + down
        ratio = up / total if total > 0 else 0.5
        return {"ad_score": int(min(max((ratio - 0.3) / 0.4 * 60, 0), 60)), "up_count": up, "down_count": down}
    except Exception:
        return {"ad_score": 0, "up_count": 0, "down_count": 0}

def _original_get_kline(code: str, days: int = 250) -> pd.DataFrame:
    """获取历史K线(腾讯日K)"""
    import requests
    pfx = _prefix(code)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={pfx},day,,,{days},qfq"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=10)
        data = r.json().get("data", {}).get(pfx, {}).get("qfqday", []) or r.json().get("data", {}).get(pfx, {}).get("day", [])
        if not data: return pd.DataFrame()
        rows = []
        for d in data:
            rows.append({"date": d[0], "open": float(d[1]), "close": float(d[2]), "high": float(d[3]), "low": float(d[4]), "volume": float(d[5])})
        return pd.DataFrame(rows)
    except Exception as e:
        logger.warning(f"K线获取失败 {code}: {e}")
        return pd.DataFrame()

SECTOR_CACHE = Path(__file__).resolve().parent.parent / "data" / "sector_cache.json"
STOCK_CACHE = Path(__file__).resolve().parent.parent / "data" / "stock_cache.json"
STOCK_CACHE_TTL = 300  # 5 minutes
FLOW_CACHE_FILE = Path(__file__).resolve().parent.parent / "data" / "flow_cache.json"

def _save_sector_cache(sectors):
    try:
        SECTOR_CACHE.parent.mkdir(parents=True, exist_ok=True)
        import json as _j
        _j.dump({"sectors": sectors[:30]}, open(SECTOR_CACHE, "w", encoding="utf-8"))
    except Exception:
        pass

def _load_sector_cache() -> list:
    try:
        if SECTOR_CACHE.exists():
            import json as _j
            return _j.load(open(SECTOR_CACHE, encoding="utf-8")).get("sectors", [])
    except Exception:
        pass
    return []

def _save_flow_cache(data):
    """Save flow data to local cache file"""
    try:
        FLOW_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        import json as _j
        _j.dump(data, open(FLOW_CACHE_FILE, "w", encoding="utf-8"))
    except Exception:
        pass

def _load_flow_cache():
    """Load flow data from local cache file, return {} if not available"""
    try:
        if FLOW_CACHE_FILE.exists():
            import json as _j
            return _j.load(open(FLOW_CACHE_FILE, encoding="utf-8"))
    except Exception:
        pass
    return {}

def get_sector_ranking(top_n: int = 50) -> list:
    """东财行业板块排名"""
    import requests
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {"pn":"1","pz":str(top_n),"po":"1","np":"1","fltt":"2","invt":"2","fs":"m:90+t:2","fields":"f2,f3,f4,f12,f14,f104,f105,f128"}
        time.sleep(1.2)
        r = requests.get(url, params=params, headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}, timeout=15)
        items = r.json().get("data",{}).get("diff",[]) or []
        result = [{"name": it.get("f14",""), "code": it.get("f12",""), "change_pct": it.get("f3",0), "up": it.get("f104",0), "down": it.get("f105",0), "leader": it.get("f128","")} for it in items]
        if result:
            _save_sector_cache(result)
            return result
        cached = _load_sector_cache()
        if cached:
            logger.info(f"[Sector] Using cached ({len(cached)} sectors)")
            return cached
    except Exception as e:
        logger.warning(f"板块数据失败: {e}")
        cached = _load_sector_cache()
        if cached:
            logger.info(f"[Sector] Using cached ({len(cached)} sectors)")
            return cached
        return []
def get_top_flow_stocks(top_n=200):
    """获取资金流向排名（东财主力）, 含缓存降级 + Sina量比近似降级"""
    import requests as req
    try:
        url = 'https://push2.eastmoney.com/api/qt/clist/get'
        params = {'pn':1, 'pz':top_n, 'po':1, 'np':1, 'fltt':2, 'invt':2, 'fs':'m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23', 'fields':'f12,f62', 'fid':'f62'}
        r = req.get(url, params=params, headers={'User-Agent':UA, 'Referer':'https://quote.eastmoney.com/'}, timeout=15)
        items = r.json().get('data',{}).get('diff',[]) or []
        result = {}
        for it in items:
            c_code = str(it.get('f12',''))
            if len(c_code) == 6:
                result[c_code] = it.get('f62', 0)
        if result:
            _save_flow_cache(result)
            logger.info(f'[Flow] {len(result)} stocks with inflow data')
            return result
        cached = _load_flow_cache()
        if cached:
            logger.info(f'[Flow] Cache hit: {len(cached)} stocks (Eastmoney returned empty)')
            return cached
    except Exception as e:
        logger.warning(f'Flow Eastmoney fail: {e}')
        cached = _load_flow_cache()
        if cached:
            logger.info(f'[Flow] Cache hit: {len(cached)} stocks')
            return cached
    # Sina-based fallback: approximate active money flow via vol_ratio > 2.0
    try:
        logger.info('[Flow] Trying Sina vol_ratio fallback')
        stock_list = None
        try:
            stock_list = get_real_stock_list()
        except Exception:
            pass
        if not stock_list:
            stock_list = _fallback_stock_list()
        quotes = get_tencent_quotes(stock_list[:200])
        if quotes:
            result = {}
            for code, q in quotes.items():
                vol_ratio = q.get('vol_ratio', 0)
                if vol_ratio > 2.0:
                    result[code] = vol_ratio * 1000000
            if result:
                result = dict(sorted(result.items(), key=lambda x: x[1], reverse=True)[:top_n])
                logger.info(f'[Flow] Sina fallback: {len(result)} stocks with vol_ratio>2.0')
                return result
    except Exception as e2:
        logger.warning(f'Flow Sina fallback also failed: {e2}')
    return {}

def get_top_sectors(top_n=5):
    wz_ts = _try_wz_first("get_top_sectors", top_n)
    if wz_ts and len(wz_ts) > 0:
        return wz_ts
    sectors = get_sector_ranking(100)
    if not sectors:
        fb = ["化学制药","生物制品","医疗服务","医药生物","中药II",
              "半导体","分立器件","集成电路设计","芯片",
              "软件服务","IT服务","人工智能","大数据",
              "汽车整车","汽车零部件","新能源汽车",
              "银行","证券","保险",
              "食品饮料","白酒","家电",
              "国防军工","航空航天装备",
              "电力设备","光伏设备","储能"]
        top = fb[:top_n]
        logger.info(f"[Sector] Hardcoded fallback top {top_n}: {top}")
        return top
    sectors.sort(key=lambda s: s.get('change_pct', 0), reverse=True)
    top = [s['name'] for s in sectors[:top_n] if s.get('name')]
    logger.info(f'[Sector] Top {top_n}: {top}')
    return top
def get_limit_up_count():
    """获取今日涨停股票数量(近似),用于市场热度评分"""
    try:
        result = _try_wz_first("get_limit_up_count")
        if result is not None:
            return result
        # fallback: 用腾讯涨停板接口
        import urllib.request, json
        url = "https://push2.eastmoney.com/api/qt/clist/get?cb=&pn=1&pz=10&po=1&np=1&fields=f12,f14,f3&fid=f3&fs=m:90+t:3"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=5).read().decode("utf-8")
        # 简易解析: 提取股票数量
        import re
        matches = re.findall(r'"total":(\d+)', data)
        if matches:
            return int(matches[0])
        return 0
    except Exception:
        return 0


# ═══ 数据质量管理 ═══
import time as _time

_CACHE_TTL = 3600  # 缓存有效期1小时
_cache_timestamps = {}

def _check_cache_ttl(cache_key: str, ttl: int = _CACHE_TTL) -> bool:
    """检查缓存是否过期"""
    now = _time.time()
    last = _cache_timestamps.get(cache_key, 0)
    if now - last < ttl:
        return True  # 缓存有效
    return False

def _update_cache_ts(cache_key: str):
    """更新缓存时间戳"""
    _cache_timestamps[cache_key] = _time.time()

def validate_kline_data(df, code: str = "") -> dict:
    """K线数据质量检查"""
    import numpy as np
    issues = []
    if df is None:
        return {"valid": False, "issues": ["DataFrame is None"], "code": code}
    if df.empty:
        return {"valid": False, "issues": ["Empty DataFrame"], "code": code}

    close = df["close"].values if "close" in df.columns else None
    vol = df["volume"].values if "volume" in df.columns else None
    high = df["high"].values if "high" in df.columns else None
    low = df["low"].values if "low" in df.columns else None

    # 1. 缺失值检查
    if close is not None and np.any(np.isnan(close)):
        issues.append("close列含NaN")
    if vol is not None and np.any(np.isnan(vol)):
        issues.append("volume列含NaN")

    # 2. 价格合理性
    if close is not None:
        if np.any(close <= 0):
            issues.append("存在<=0的收盘价")
        if np.any(np.abs(np.diff(close) / close[:-1]) > 0.20):
            issues.append("存在单日涨跌幅>20%的异常数据")

    # 3. 高低价逻辑
    if high is not None and low is not None:
        if np.any(high < low):
            issues.append("high<low的数据行")
        if close is not None and np.any(close > high):
            issues.append("close>high的数据行")
        if close is not None and np.any(close < low):
            issues.append("close<low的数据行")

    # 4. 停牌检测: 连续多日价格不变
    if close is not None and len(close) >= 5:
        flat_days = sum(1 for i in range(1, len(close)) if abs(close[i] - close[i-1]) / max(close[i-1], 0.01) < 0.001)
        if flat_days > len(close) * 0.3:
            issues.append(f"疑似停牌: {flat_days}/{len(close)}日价格无变动")

    # 5. 成交量异常
    if vol is not None and len(vol) >= 5:
        if np.any(vol < 0):
            issues.append("存在负成交量")
        avg_vol = np.mean(vol[vol > 0]) if np.any(vol > 0) else 1
        if avg_vol == 0:
            issues.append("成交量全为0")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "code": code,
        "rows": len(df),
    }

def get_kline_with_validation(code: str, days: int = 120) -> pd.DataFrame:
    """获取K线并做数据质量检查"""
    df = _original_get_kline(code, days)
    if df is not None and not df.empty:
        qc = validate_kline_data(df, code)
        if not qc["valid"]:
            logger.warning(f"[DataQC] {code}: {qc['issues']}")
    return df

# 兼容层: 保持get_kline名称不变, 所有外部导入不受影响
def get_kline(code: str, days: int = 500) -> pd.DataFrame:
    """获取K线(带数据质量检查)"""
    return get_kline_with_validation(code, days)
