import json
from pathlib import Path

p = Path(r"D:\Hermes Agent CN Desktop\stock-workflow\docs\_panorama_20260927\scheduled_tasks_export.json")
data = json.loads(p.read_text(encoding="utf-8-sig"))
for t in sorted(data, key=lambda x: x["TaskName"]):
    print("### %s | user=%s runlevel=%s logon=%s state=%s" % (
        t["TaskName"], t.get("UserId"), t.get("RunLevel"), t.get("LogonType"), t.get("State")))
    for g in (t.get("Triggers") or []):
        print("    ", json.dumps(g, ensure_ascii=False))
