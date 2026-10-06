import ast
import json
import subprocess
import time
import urllib.error
import urllib.request

P = r"D:\Hermes Agent CN Desktop\hunter-v2\backend\auto_trader.py"
src = open(P, encoding="utf-8").read()
ast.parse(src)
print("① ast.parse(auto_trader.py) OK, %d 行" % len(src.splitlines()))

print("② 重启后端：杀 8000 → launcher.py")
out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
pids = set()
for line in out.splitlines():
    if ":8000" in line and "LISTENING" in line:
        pids.add(line.split()[-1])
print("   占用 8000 的 PID:", pids)
for pid in pids:
    r = subprocess.run(["taskkill", "/PID", pid, "/F", "/T"], capture_output=True, text=True)
    print("   taskkill", pid, "->", (r.stdout or r.stderr).strip()[:90])
time.sleep(2)

r = subprocess.run([r"D:\Hermes Agent CN Desktop\hunter-v2\.venv\Scripts\python.exe",
                    "backend/launcher.py"],
                   cwd=r"D:\Hermes Agent CN Desktop\hunter-v2",
                   capture_output=True, text=True)
print("   launcher:", (r.stdout or "").strip()[:120], (r.stderr or "").strip()[:200])

BASE = "http://127.0.0.1:8000"
for i in range(40):
    try:
        urllib.request.urlopen(BASE + "/openapi.json", timeout=5)
        print("   后端就绪，等待 %.0fs" % (i * 2))
        break
    except Exception:
        time.sleep(2)
else:
    print("   !! 后端未就绪")
