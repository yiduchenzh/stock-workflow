
"""数据源 — 腾讯财经(主力) + 东财(辅助), 三级降级"""
import urllib.request, json, time, logging
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

def get_real_stock_list() -> list:
    """东财获取实际A股列表(缓存30分钟)"""
    try:
        import requests
        codes = []
        for fs in ["m:0+t:6,m:0+t:80", "m:1+t:2,m:1+t:23"]:
            url = "https://push2.eastmoney.com/api/qt/clist/get"
            params = {"pn":"1","pz":"6000","po":"1","np":"1","fltt":"2","invt":"2","fs":fs,"fields":"f12"}
            headers = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}
            time.sleep(1.2)
            r = requests.get(url, params=params, headers=headers, timeout=15)
            items = r.json().get("data",{}).get("diff",[]) or []
            for it in items:
                c = it.get("f12","")
                if len(c) == 6: codes.append(c)
        return list(dict.fromkeys(codes))
    except Exception as e:
        logger.warning(f"股票列表获取失败({e}), use fallback list")
        return _fallback_stock_list()

def get_top_flow_stocks(top_n: int = 200) -> list:
    """资金净流入TOP N股票列表(东财主力净流入f62排序)"""
    import requests
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {"pn":"1","pz":str(top_n),"po":"1","np":"1","fltt":"2","invt":"2",
                  "fs":"m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                  "fields":"f12,f62","fid":"f62"}
        r = requests.get(url, params=params, 
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}, 
            timeout=15)
        items = r.json().get("data",{}).get("diff",[]) or []
        # f62 = 主力净流入, 返回含代码+净流入额
        result = {}
        for it in items:
            c = str(it.get("f12",""))
            if len(c) == 6:
                result[c] = it.get("f62", 0)
        logger.info(f"[Flow] {len(result)} stocks with capital inflow data")
        return result
    except Exception as e:
        logger.warning(f"资金流向获取失败: {e}")
        return {}

def get_top_sectors(top_n: int = 5) -> list:
    """板块涨幅TOP N名称列表"""
    sectors = get_sector_ranking(100)
    if not sectors:
        return []
    sectors.sort(key=lambda s: s.get("change_pct", 0), reverse=True)
    top = [s["name"] for s in sectors[:top_n] if s.get("name")]
    logger.info(f"[Sector] Top {top_n}: {top}")
    return top


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

def get_sector_ranking(top_n: int = 50) -> list:
    """东财行业板块排名"""
    import requests
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {"pn":"1","pz":str(top_n),"po":"1","np":"1","fltt":"2","invt":"2","fs":"m:90+t:2","fields":"f2,f3,f4,f12,f14,f104,f105,f128"}
        time.sleep(1.2)
        r = requests.get(url, params=params, headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}, timeout=15)
        items = r.json().get("data",{}).get("diff",[]) or []
        return [{"name": it.get("f14",""), "code": it.get("f12",""), "change_pct": it.get("f3",0), "up": it.get("f104",0), "down": it.get("f105",0), "leader": it.get("f128","")} for it in items]
    except Exception as e:
        logger.warning(f"板块数据失败: {e}")
        return []
