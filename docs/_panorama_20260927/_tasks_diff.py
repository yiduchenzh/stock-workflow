import json
from pathlib import Path

before_p = Path(r"D:\Hermes Agent CN Desktop\stock-workflow\docs\_panorama_20260927\scheduled_tasks_export.json")
after_p = Path(r"D:\Hermes Agent CN Desktop\stock-workflow\docs\_panorama_20260927\scheduled_tasks_after.json")
b = {t["TaskName"]: t for t in json.loads(before_p.read_text(encoding="utf-8-sig"))}
a = {t["task_name"]: t for t in json.loads(after_p.read_text(encoding="utf-8-sig"))}

print("任务数: before=%d after=%d | 集合相同=%s" % (len(b), len(a), set(b) == set(a)))

print("\n=== ① 可执行体/参数变化（预期: junction→真实路径 + Autostart 引号）===")
for n in sorted(b):
    be = (b[n]["Actions"][0].get("Execute") or "")
    ae = (a[n]["actions"][0].get("execute") or "")
    ba = (b[n]["Actions"][0].get("Arguments") or "")
    aa = (a[n]["actions"][0].get("arguments") or "")
    if be != ae or ba != aa:
        print("  %-28s\n     before exec=%s | args=%s\n     after  exec=%s | args=%s" % (n, be, ba, ae, aa))

print("\n=== ② 触发器漂移检查（应为空）===")
drift = 0
for n in sorted(b):
    bt = [(g["Type"], str(g["StartBoundary"])[11:19], g.get("DaysInterval"), g.get("Repetition")) for g in b[n]["Triggers"]]
    at = [(g["type"].replace("MSFT_Task", ""), str(g["start"])[11:19], g.get("days_interval"), g.get("rep")) for g in a[n]["triggers"]]
    norm = lambda x: [("Daily" if t in ("MSFT_TaskDailyTrigger", "Daily") else
                       "Weekly" if "Weekly" in t else
                       "Logon" if "Logon" in t else
                       "Time" if "Time" in t else t) for t in [y[0]]] + list(y[1:])
    if norm(bt) != norm(at):
        drift += 1
        print("  %-28s before=%s\n     %-28s after =%s" % (n, bt, "", at))
print("  漂移任务数 =", drift)

print("\n=== ③ 账户/权限对比（应为空）===")
for n in sorted(b):
    bp = (b[n].get("UserId"), b[n].get("RunLevel"), b[n].get("LogonType"))
    ap = (a[n].get("user_id"), a[n].get("run_level"), a[n].get("logon"))
    if bp != ap:
        print("  %-28s before=%s after=%s" % (n, bp, ap))
print("  （无输出=一致）")
