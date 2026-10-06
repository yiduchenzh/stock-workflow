import json
import collections
import urllib.request

BASE = "http://127.0.0.1:8000"


def get(path, timeout=25):
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except Exception as e:
        return "ERR", "%s: %s" % (type(e).__name__, e)


st, body = get("/openapi.json")
print("openapi status =", st)
paths = list(json.loads(body)["paths"].keys())
print("总路由数 =", len(paths))

pref = collections.Counter()
for p in paths:
    parts = p.strip("/").split("/")
    key = "/".join(parts[:3]) if len(parts) >= 3 else p
    pref[key] += 1
print("\n=== 路由前缀分组 (>=2 条) ===")
for k, v in sorted(pref.items(), key=lambda x: -x[1]):
    if v >= 2:
        print("%-42s %d" % (k, v))

print("\n=== 引擎/关键状态接口 ===")
for p in ["/api/v1/auto-trade/status", "/api/v1/auto_trade/status", "/api/v1/prevclose15/status",
          "/api/v1/chan-trade/status", "/api/v1/chan/status", "/api/v1/wave/stats",
          "/api/v1/vol-signal/stats", "/api/v1/factor-v4/status"]:
    st, body = get(p)
    if st == 200:
        try:
            d = json.loads(body)
            brief = {k: d.get(k) for k in ("running", "cash", "day", "total_asset", "positions", "stats") if k in d}
            if isinstance(brief.get("positions"), (list, dict)):
                brief["positions_n"] = len(brief["positions"])
                brief.pop("positions", None)
            print("%-38s 200 %s" % (p, json.dumps(brief, ensure_ascii=False)[:180]))
        except Exception as e:
            print("%-38s 200 (非json) %s" % (p, body[:120]))
    else:
        print("%-38s %s" % (p, st))
