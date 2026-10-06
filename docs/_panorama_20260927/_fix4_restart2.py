import subprocess
import time
import urllib.error
import urllib.request

HUNTER = r"D:\Hermes Agent CN Desktop\hunter-v2"
PY = HUNTER + r"\.venv\Scripts\python.exe"


def ps(cmd):
    return subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                          capture_output=True, text=True, encoding="utf-8", errors="ignore")


def listeners():
    out = ps("(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue).OwningProcess")
    return sorted({x.strip() for x in (out.stdout or "").splitlines() if x.strip().isdigit()})


def main_pids():
    out = ps("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Where-Object { $_.CommandLine -like '*main.py*' } | ForEach-Object { $_.ProcessId }")
    return sorted({x.strip() for x in (out.stdout or "").splitlines() if x.strip().isdigit()})


print("① 重启前: 监听 8000 的 PID =", listeners(), "| 跑 main.py 的 PID =", main_pids())
for pid in set(listeners()) | set(main_pids()):
    ps("Stop-Process -Id %s -Force -ErrorAction SilentlyContinue" % pid)
    print("   已杀", pid)
time.sleep(3)
print("② 杀后: 监听 =", listeners(), "| main.py =", main_pids())

r = subprocess.run([PY, "backend/launcher.py"], cwd=HUNTER, capture_output=True, text=True,
                   encoding="utf-8", errors="ignore")
print("③ launcher:", (r.stdout or "").strip()[:80])

ok = False
for i in range(45):
    time.sleep(2)
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/api/v1/health", timeout=5) as resp:
            if resp.status == 200:
                print("④ 真实 HTTP 探活成功: /api/v1/health = 200 (等待 %ds) | 监听 = %s"
                      % (i * 2, listeners()))
                ok = True
                break
    except Exception:
        pass
if not ok:
    print("④ !! 45×2s 内未探活成功 | 监听 =", listeners())

for path in ("/openapi.json", "/api/v1/auto-trade/trades?limit=1", "/api/v1/auto-trade/status"):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000" + path, timeout=25) as resp:
            body = resp.read()
            print("⑤ %-38s %d  %d bytes" % (path, resp.status, len(body)))
    except urllib.error.HTTPError as e:
        print("⑤ %-38s HTTP %d" % (path, e.code))
    except Exception as e:
        print("⑤ %-38s ERR %s" % (path, type(e).__name__))
