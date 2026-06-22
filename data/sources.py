
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
        logger.warning(f"股票列表获取失败: {e}")
        return []

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
    except:
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
