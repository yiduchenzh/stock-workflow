import json
from pathlib import Path

p = Path(r"D:\Hermes Agent CN Desktop\stock-workflow\docs\_panorama_20260927\scheduled_tasks_export.json")
data = json.loads(p.read_text(encoding="utf-8-sig"))
BAD = {0: "OK", 1: "0x1 函数不正确", 2: "0x2 文件未找到", 267009: "0x41301 正在运行",
       267011: "0x41303 从未运行", 2147942402: "0x80070002 找不到文件",
       2147942401: "0x80070001 函数不正确", -2147024894: "0x80070002 找不到文件"}
print("%-28s %-20s %-20s %-22s" % ("任务名", "上次运行", "下次运行", "上次结果"))
for t in sorted(data, key=lambda x: x["TaskName"]):
    lr = t.get("LastResult")
    hint = BAD.get(lr, "")
    print("%-28s %-20s %-20s %-14s %s" % (t["TaskName"], str(t.get("LastRun"))[:19],
                                          str(t.get("NextRun"))[:19], lr, hint))
