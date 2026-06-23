"""歪枣网数据源 — 主数据源，东财/Sina为备用"""
import os, json, logging, pandas as pd, numpy as np
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("aurora.wz")

TOKEN = os.environ.get("WZ_TOKEN", "")
if not TOKEN:
    logger.warning("WZ_TOKEN not set, WZ sources disabled")

def _parse(r):
    """Parse WZ JSON to DataFrame"""
    try:
        d = json.loads(r) if isinstance(r, str) else r
        if not d.get("data"): return pd.DataFrame()
        en = d.get("en", [])
        return pd.DataFrame(d["data"], columns=en) if en and d["data"] else pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def _call(fn, **kw):
    """Call WZ API"""
    try:
        if not TOKEN: return pd.DataFrame()
        import waizao.api.stock_api as wz
        kw.setdefault("token", TOKEN)
        kw.setdefault("fields", "all")
        kw.setdefault("export", 5)
        kw.setdefault("filter", "")
        r = getattr(wz, fn)(**kw)
        return _parse(r)
    except Exception as e:
        logger.warning(f"[WZ] {fn} fail: {e}")
        return pd.DataFrame()

def get_klines(code, days=120):
    """日K线"""
    s = (datetime.now() - timedelta(days=days*2)).strftime("%Y-%m-%d")
    e = datetime.now().strftime("%Y-%m-%d")
    df = _call("getStockHSADayKLine", code=code, ktype=101, fq=0, startDate=s, endDate=e)
    if df.empty: return df
    m = {"tdate":"date","open":"open","close":"close","high":"high","low":"low","cjl":"volume"}
    df = df.rename(columns={k:m[k] for k in m if k in df.columns})
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df.tail(days)

def get_kline_period(code, period="day", days=52):
    """多周期K线"""
    kt = {"day":101, "week":102, "month":103}.get(period, 101)
    s = (datetime.now() - timedelta(days=days*3)).strftime("%Y-%m-%d")
    e = datetime.now().strftime("%Y-%m-%d")
    df = _call("getStockHSADayKLine", code=code, ktype=kt, fq=0, startDate=s, endDate=e)
    if df.empty: return df
    m = {"tdate":"date","open":"open","close":"close","high":"high","low":"low"}
    df = df.rename(columns={k:m[k] for k in m if k in df.columns})
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)

def get_quotes(codes):
    """实时行情"""
    if not codes: return {}
    e = datetime.now().strftime("%Y-%m-%d")
    df = _call("getStockHSADailyMarket", code=",".join(codes[:50]), startDate=e, endDate=e)
    if df.empty: return {}
    r = {}
    for _, row in df.iterrows():
        c = str(row.get("code",""))
        if not c or len(c) != 6: continue
        r[c] = {"code":c, "name":str(row.get("name","")),
                "price":float(row.get("close",0)), "change_pct":float(row.get("zdfd",0)),
                "turnover":float(row.get("hsl",0)), "volume":float(row.get("cjl",0))}
    return r

def get_sector_ranking(top_n=50):
    """行业板块排行"""
    e = datetime.now().strftime("%Y-%m-%d")
    df = _call("getStockHYADailyMarket", code="all", startDate=e, endDate=e)
    if df.empty: return []
    r = []
    for _, row in df.iterrows():
        r.append({"code":str(row.get("code","")),"name":str(row.get("name","")),
                "change_pct":float(row.get("zdfd",0)),
                "up_count":int(row.get("zCount",0)),"down_count":int(row.get("dCount",0))})
    r.sort(key=lambda x: -x["change_pct"])
    return r[:top_n]

def get_market_breadth():
    """市场广度"""
    e = datetime.now().strftime("%Y-%m-%d")
    df = _call("getDailyMarket", type=1, code="all", startDate=e, endDate=e)
    if df.empty: return {"ad_score":0,"up_count":0,"down_count":0}
    up = int(df["zCount"].sum()) if "zCount" in df.columns else 0
    down = int(df["dCount"].sum()) if "dCount" in df.columns else 0
    t = up + down
    return {"ad_score": up/t*100 if t>0 else 50, "up_count": up, "down_count": down}

def get_northbound_flow():
    """北向资金"""
    e = datetime.now().strftime("%Y-%m-%d")
    s = (datetime.now()-timedelta(days=5)).strftime("%Y-%m-%d")
    df = _call("getHSGTMoney", mtype=1, ktype=1, startDate=s, endDate=e)
    if df.empty: return {"signal":"unknown","score":50}
    flow = float(df.iloc[-1].get("jlr",0)) if len(df)>0 else 0
    d = "inflow" if flow>0 else "outflow"
    return {"signal":d, "score":50, "net_flow_yi":flow, "direction":d}

def get_stock_list():
    """A股列表"""
    df = _call("getStockHSABaseInfo", code="all")
    if df.empty: return []
    return [str(c) for c in df["code"].tolist() if len(str(c))==6]

def get_top_sectors(top_n=5):
    """涨幅TOP N板块"""
    s = get_sector_ranking(100)
    if not s: return []
    return [x["name"] for x in s[:top_n]]