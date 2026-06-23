import sys
c=open('data/sources.py').read()
nf='''

def get_kline_period(code, period="day", days=250):
    """”多周期K线: day/week/month — 真实数据自一免兵"""

    import requests
    pfx = _prefix(code)
    period_map = {"day": "day", "week": "week", "month": "month"}
    p = period_map.get(period, "day")
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=" + pfx + "," + p + ",,," + str(days) + ",qfq"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=10)
        data = r.json().get("data", {}).get(pfx, {})
        keys = {"day": "qfqday", "week": "qfqweek", "month": "qfqmonth"}
        raw = data.get(keys.get(p, "qfqday"), [])
        if not raw:
            raw = data.get(p, [])  # fallback
        if not raw:
            return pd.DataFrame()
        rows = []
        for d in raw:
            rows.append({"date": str(d[0]), "open": float(d[1]), "close": float(d[2]),
                "high": float(d[3]), "low": float(d[4]), "volume": float(d[5]) if len(d) > 5 else 0})
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception as e:
        logger.warning("K线获获失夝 %s %s: %s", code, period, e)
        return pd.DataFrame()

'''
marker='        return pd.DataFrame()\n'
p=c.rfind(marker)
if p<0:print('ERROR');sys.exit(1)
ip=p+len(marker)
nc=c[:ip]+nf+c[ip:]
open('data/sources.py','w').write(nc)
print('OK')
