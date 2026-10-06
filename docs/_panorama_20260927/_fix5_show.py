import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8000/api/v1/auto-trade/trades?limit=3", timeout=25) as r:
    d = json.loads(r.read().decode("utf-8", "ignore"))
print("返回键:", list(d.keys()))
print("\nstats =", json.dumps(d.get("stats"), ensure_ascii=False, indent=2))
print("\ntrades 条数 =", len(d.get("trades") or []))
print("最后一条 =", json.dumps((d.get("trades") or [{}])[-1], ensure_ascii=False))
