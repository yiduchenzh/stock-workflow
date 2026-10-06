import json
from pathlib import Path

bp = Path(r"D:\Hermes Agent CN Desktop\stock-workflow\docs\_panorama_20260927\scheduled_tasks_export.json")
ap = Path(r"D:\Hermes Agent CN Desktop\stock-workflow\docs\_panorama_20260927\scheduled_tasks_after.json")
b = {t["TaskName"]: t for t in json.loads(bp.read_text(encoding="utf-8-sig"))}
a = {t["task_name"]: t for t in json.loads(ap.read_text(encoding="utf-8-sig"))}


def kind(t):
    for k in ("Daily", "Weekly", "Logon", "Time", "Boot", "Idle"):
        if k in t:
            return k
    return t


drift = []
for n in sorted(b):
    bt = [(kind(g["Type"]), str(g["StartBoundary"])[11:19], str(g.get("DaysInterval")),
           str(g.get("Repetition"))) for g in b[n]["Triggers"]]
    at = [(kind(g["type"]), str(g["start"])[11:19], str(g.get("days_interval")),
           str(g.get("rep"))) for g in a[n]["triggers"]]
    if bt != at:
        drift.append((n, bt, at))

print("=== ② 触发器漂移（预期仅 Aurora_Monitor_5min 的 rep 表示差异）===")
for n, bt, at in drift:
    print("  %-24s before=%s\n     %-24s after =%s" % (n, bt, "", at))
print("  漂移任务数 =", len(drift), "/", len(b))

print("\n=== ③ 账户/权限对比 ===")
mis = [(n, (b[n].get("UserId"), b[n].get("RunLevel"), b[n].get("LogonType")),
        (a[n].get("user_id"), a[n].get("run_level"), a[n].get("logon")))
       for n in sorted(b)
       if (b[n].get("UserId"), b[n].get("RunLevel"), b[n].get("LogonType"))
       != (a[n].get("user_id"), a[n].get("run_level"), a[n].get("logon"))]
for n, x, y in mis:
    print("  %-24s before=%s after=%s" % (n, x, y))
print("  不一致数 =", len(mis))
