import json
import urllib.request

BASE = "http://127.0.0.1:8000"
for p in ("/api/v1/health", "/api/v1/auto-trade/trades?limit=1", "/api/v1/prevclose15/status"):
    try:
        with urllib.request.urlopen(BASE + p, timeout=45) as r:
            d = json.loads(r.read().decode("utf-8", "ignore"))
        if "trades" in p:
            print("%-38s 200  stats=%s" % (p, json.dumps(d.get("stats"), ensure_ascii=False)))
        elif "prevclose15" in p:
            print("%-38s 200  stats=%s" % (p, json.dumps(d.get("stats"), ensure_ascii=False)))
        else:
            print("%-38s 200  %s" % (p, json.dumps(d, ensure_ascii=False)[:90]))
    except Exception as e:
        print("%-38s ERR %s" % (p, type(e).__name__))
