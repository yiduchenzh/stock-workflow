import json
import os
import re
import urllib.request
from pathlib import Path

HUNTER = Path(r"D:\Hermes Agent CN Desktop\hunter-v2")

# 1) 后端路由前缀
paths = list(json.loads(urllib.request.urlopen("http://127.0.0.1:8000/openapi.json", timeout=30).read())["paths"].keys())
prefixes = set()
for p in paths:
    parts = p.strip("/").split("/")
    if len(parts) >= 3:
        prefixes.add(parts[2])
print("后端前缀数 =", len(prefixes))

# 2) 前端源码里出现过的前缀
src = ""
for f in list((HUNTER / "src").rglob("*.ts*")):
    src += f.read_text(encoding="utf-8", errors="ignore")
used = {p for p in prefixes if re.search(r"/api/v1/%s[/\"'`?]" % re.escape(p), src)}
orphan = sorted(prefixes - used)
print("前端消费前缀 =", len(used))
print("孤儿前缀 =", len(orphan), orphan)
orphan_routes = [p for p in paths if p.strip("/").split("/")[2] in orphan]
print("孤儿路由条数 =", len(orphan_routes))

# 3) Windows 计划任务
import subprocess
out = subprocess.run(["schtasks", "/query", "/fo", "csv"], capture_output=True, text=True, encoding="gbk", errors="ignore").stdout
hits = [l for l in out.splitlines() if re.search(r"hunter|stock|aurora|MarketData|chanlun|factor|screener", l, re.I)]
print("\n计划任务命中行数 =", len(hits))
for l in hits[:25]:
    print("  ", l[:150])
