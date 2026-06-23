
"""数据源 — 腾讯财经(主力) + 东财(辅助), 三级降级"""
import urllib.request, json, time, logging
from pathlib import Path
import pandas as pd

logger = logging.getLogger("aurora.data")
UA = "Mozilla/5.0"

def _prefix(code):
    return f"sh{code}" if code.startswith(("6","9")) else f"sz{code}"

def get_tencent_quotes(codes: list) -> dict:
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
    import requests as req
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
                import time as _t
                _t.sleep(2.0)
                try:
                    r2 = req.get(url, params={'pn': pn, 'pz': 100, 'po': 1, 'np': 1, 'fltt': 2, 'invt': 2, 'fs': fs, 'fields': 'f12'},
                               headers={'User-Agent': UA, 'Referer': 'https://quote.eastmoney.com/'}, timeout=10)
                    items2 = r2.json().get('data', {}).get('diff', []) or []
                    chunk = [it['f12'] for it in items2 if len(str(it.get('f12',''))) == 6]
                    if chunk:
                        codes.extend(chunk)
                        if len(items2) < 100: break
                        continue
                except: pass
                logger.warning(f'EM p{pn} retry also failed')
                break
    if codes:
        result = list(dict.fromkeys(codes))
        logger.info(f'[EM] {len(result)} stocks')
        return result
    logger.warning('EM fail, try Sina')
    return _sina_stock_list()

def get_index_snapshot(codes: list) -> dict:
    """获取指数快照"""
    return get_tencent_quotes(codes)

def get_market_breadth() -> dict:
    """市场广度: 涨跌比"""
    try:
        quotes = get_tencent_quotes(get_real_stock_list()[:200])
        if not quotes: return {"ad_score": 0, "up_count": 0, "down_count": 0}
        changes = [q.get("change_pct", 0) for q in quotes.values()]
        up = sum(1 for c in changes if c > 0)
        down = sum(1 for c in changes if c < 0)
        total = up + down
        ratio = up / total if total > 0 else 0.5
        return {"ad_score": int(min(max((ratio - 0.3) / 0.4 * 60, 0), 60)), "up_count": up, "down_count": down}
    except Exception:
        return {"ad_score": 0, "up_count": 0, "down_count": 0}

def get_kline(code: str, days: int = 250) -> pd.DataFrame:
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

def _save_sector_cache(sectors):
    try:
        SECTOR_CACHE.parent.mkdir(parents=True, exist_ok=True)
        import json as _j
        _j.dump({"sectors": sectors[:30]}, open(SECTOR_CACHE, "w", encoding="utf-8"))
    except Exception:
        pass

def _load_sector_cache():
    try:
        if SECTOR_CACHE.exists():
            import json as _j
            return _j.load(open(SECTOR_CACHE, encoding="utf-8")).get("sectors", [])
    except Exception:
        pass
    return []

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
        logger.info(f'[Flow] {len(result)} stocks with inflow data')
        return result
    except Exception as e:
        logger.warning(f'Flow fail: {e}')
        return {}

def get_top_sectors(top_n=5):
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
