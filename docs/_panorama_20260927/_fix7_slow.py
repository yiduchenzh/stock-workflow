import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
CASES = [
    "/api/v1/trade/decisions",
    "/api/v1/dip-rolling/signals",
    "/api/v1/limitup/strong-pool",
    "/api/v1/limitup/absorb-quality/600519",
    "/api/v1/market/sector-trend",
    "/api/v1/prevclose15/status",
]
for p in CASES:
    t0 = time.time()
    try:
        with urllib.request.urlopen(BASE + p, timeout=45) as r:
            n = len(r.read())
            print("%-42s 200  %6.2fs  %d bytes" % (p, time.time() - t0, n))
    except urllib.error.HTTPError as e:
        print("%-42s HTTP %s  %6.2fs" % (p, e.code, time.time() - t0))
    except Exception as e:
        print("%-42s ERR %s  %6.2fs" % (p, type(e).__name__, time.time() - t0))
