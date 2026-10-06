import json
import subprocess
import time
import urllib.request

HUNTER = r"D:\Hermes Agent CN Desktop\hunter-v2"
PY = HUNTER + r"\.venv\Scripts\python.exe"


def ps(cmd):
    return subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                          capture_output=True, text=True, encoding="utf-8", errors="ignore").stdout or ""


def pids():
    out = ps("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Where-Object { $_.CommandLine -like '*hunter-v2*main.py*' } | ForEach-Object { $_.ProcessId }")
    return sorted({x.strip() for x in out.splitlines() if x.strip().isdigit()})


def wait_health(t=60):
    for _ in range(t):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/api/v1/health", timeout=4) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(1)
    return False


# 语法门（禁 py_compile：只 ast.parse）
import ast
src = open(HUNTER + r"\backend\prevclose15_auto.py", encoding="utf-8").read()
ast.parse(src)
print("① ast.parse(prevclose15_auto.py) OK, %d 行" % len(src.splitlines()))

before = pids()
print("② 重启前后端进程:", before)
for p in before:
    ps("Stop-Process -Id %s -Force -ErrorAction SilentlyContinue" % p)
time.sleep(3)
subprocess.run([PY, "backend/launcher.py"], cwd=HUNTER, capture_output=True, text=True,
               encoding="utf-8", errors="ignore")
print("③ 重启完成 | 探活:", "OK" if wait_health() else "FAIL")

with urllib.request.urlopen("http://127.0.0.1:8000/api/v1/prevclose15/status", timeout=45) as r:
    d = json.loads(r.read().decode("utf-8", "ignore"))
print("④ /prevclose15/status 的 stats =", json.dumps(d.get("stats"), ensure_ascii=False))
print("   net=%s peak_net=%s cur_dd=%s 持仓=%d" % (d.get("net"), d.get("peak_net"), d.get("cur_dd"),
                                                   len(d.get("positions") or {})))
print("   positions[0] 关键字段:", {k: list((d.get("positions") or {}).values())[0].get(k)
                                    for k in ("cost", "last", "mkt_value", "float_pnl_pct")}
      if d.get("positions") else {})

with urllib.request.urlopen("http://127.0.0.1:8000/api/v1/prevclose15/trades", timeout=45) as r:
    t = json.loads(r.read().decode("utf-8", "ignore"))
rows = t.get("trades") or []
sells = [x for x in rows if x.get("action") == "清仓"]
print("⑤ trades 条数=%d 其中清仓=%d（closes 与之一致=%s）"
      % (len(rows), len(sells), d["stats"].get("closes") == len(sells)))
if sells:
    print("   最后一笔清仓 reason 原文:", sells[-1].get("reason"))
