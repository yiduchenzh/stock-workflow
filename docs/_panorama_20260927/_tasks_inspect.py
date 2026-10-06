import json
from pathlib import Path

p = Path(r"D:\Hermes Agent CN Desktop\stock-workflow\docs\_panorama_20260927\scheduled_tasks_export.json")
data = json.loads(p.read_text(encoding="utf-8-sig"))
print("任务数:", len(data), "| 文件大小:", p.stat().st_size)
print()
for t in data:
    acts = t.get("Actions") or []
    for a in acts:
        ex = a.get("Execute") or ""
        ar = a.get("Arguments") or ""
        wd = a.get("WorkingDirectory") or ""
        flag = ""
        if " " in ex and not ex.startswith('"'):
            flag = "   ⚠️未加引号(含空格)"
        print("%-26s exec=%-58s args=%-52s wd=%-38s%s" % (t["TaskName"], ex[:58], ar[:52], (wd or "")[:38], flag))
print()
# 触发器摘要（只打前 4 个）
for t in data[:4]:
    print("###", t["TaskName"], "| user=", t.get("UserId"), "| runlevel=", t.get("RunLevel"),
          "| logon=", t.get("LogonType"))
    for g in (t.get("Triggers") or [])[:3]:
        print("     ", json.dumps(g, ensure_ascii=False))
