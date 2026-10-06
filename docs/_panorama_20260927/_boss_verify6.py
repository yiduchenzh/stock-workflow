import json
import urllib.request

for p in ("/api/v1/vol-signal/stats", "/api/v1/wave/stats", "/api/v1/factor-v4/meta"):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000" + p, timeout=40) as r:
            d = json.loads(r.read().decode("utf-8", "ignore"))
        print("###", p)
        print(json.dumps(d, ensure_ascii=False)[:900])
        print()
    except Exception as e:
        print("###", p, "ERR", type(e).__name__, e)
