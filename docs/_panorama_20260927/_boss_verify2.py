import json
import urllib.request

BASE = "http://127.0.0.1:8000"


def get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")[:300]
    except Exception as e:
        return "ERR", "%s: %s" % (type(e).__name__, e)


print("=== 核验子审计员的三条关键结论 ===")
for p in ["/api/v1/auto-trade/trades", "/api/v1/prevclose15/trades", "/api/v1/chan-trade/trades"]:
    st, body = get(p)
    print("%-34s -> HTTP %s  %s" % (p, st, body[:140].replace("\n", " ")))

for name, p in [("auto-trade", "/api/v1/auto-trade/status"),
                ("prevclose15", "/api/v1/prevclose15/status"),
                ("chan-trade", "/api/v1/chan-trade/status")]:
    st, body = get(p)
    if st == 200:
        d = json.loads(body)
        keys = [k for k in d.keys()]
        print("\n[%s] status keys=%s" % (name, keys))
        for k in ("last_tick", "day", "started_at", "running", "cash", "total_asset"):
            if k in d:
                print("   %-12s = %s" % (k, d[k]))
    else:
        print("[%s] %s %s" % (name, st, body[:120]))
