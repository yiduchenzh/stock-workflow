import json
import re
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"


def _fetch_openapi():
    last = None
    for i in range(6):
        try:
            with urllib.request.urlopen(BASE + "/openapi.json", timeout=20) as r:
                return json.loads(r.read().decode("utf-8", "ignore"))
        except Exception as e:      # 含 TimeoutError/ConnectionRefused
            last = e
            print("openapi 第 %d 次失败: %s" % (i + 1, type(e).__name__))
            time.sleep(3)
    raise SystemExit("无法获取 openapi.json: %r" % last)

SKIP_KW = ("scan", "build", "refresh", "backtest", "rebuild", "reload", "train",
           "sync", "prewarm", "run", "generate", "rebuild", "fill", "backfill")
SUB = {"code": "600519", "symbol": "600519", "date": "2026-09-24", "day": "2026-09-24",
       "secid": "1.600519", "name": "x", "key": "boll_breakout", "type": "daily",
       "period": "daily", "limit": "2", "count": "2", "n": "2", "top": "2",
       "days": "2", "board": "all", "market": "sh"}


def get(path, timeout=8):
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            return r.status, len(r.read())
    except urllib.error.HTTPError as e:
        return e.code, 0
    except Exception as e:
        return "ERR:" + type(e).__name__, 0


paths = _fetch_openapi()["paths"]
gets = [(p, list(v.keys())) for p, v in paths.items() if "get" in v]
print("GET 路由总数 =", len(gets))

bad, skipped, ok = [], [], 0
for p, methods in gets:
    if any(k in p.lower() for k in SKIP_KW):
        skipped.append(p)
        continue
    has_param = re.search(r"\{(\w+)\}", p)
    if has_param:
        params = re.findall(r"\{(\w+)\}", p)
        if any(par not in SUB for par in params):
            skipped.append(p + "  (参数未知: %s)" % ",".join(params))
            continue
        url = p
        for par in params:
            url = url.replace("{%s}" % par, SUB[par])
    else:
        url = p
    st, n = get(url)
    if st != 200:
        bad.append((p, st))
        print("  ❌ %-52s %s" % (p, st))
    else:
        ok += 1

print("\n结果：200=%d  非200=%d  跳过(重活/参数未知)=%d" % (ok, len(bad), len(skipped)))
print("\n非 200 清单：")
for p, st in bad:
    print("  %-56s %s" % (p, st))
print("\n跳过清单（前 25）：")
for p in skipped[:25]:
    print("  ", p)
