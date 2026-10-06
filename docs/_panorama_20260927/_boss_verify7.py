import os
import subprocess
import sys
from pathlib import Path

print("=== ① D:\\hikyuu_research 是否存在 ===")
print("exists:", Path(r"D:\hikyuu_research").exists())
print("D:\\ 下含 hikyuu 的目录:", [p.name for p in Path("D:/").iterdir() if "hikyuu" in p.name.lower()] or "无")

print("\n=== ② d:\\Aurora 是否符号链接 ===")
p = Path(r"D:\Aurora")
print("exists:", p.exists(), "| is_symlink:", p.is_symlink())
if p.is_symlink():
    print("  → 指向:", os.readlink(p))
print("D:\\ 下含 aurora 的目录:", [x.name for x in Path("D:/").iterdir() if "aurora" in x.name.lower()])

print("\n=== ③ setup_scheduler.ps1 内容前 6 行 ===")
sw = Path(r"D:\Hermes Agent CN Desktop\stock-workflow\scripts\setup_scheduler.ps1")
if sw.exists():
    lines = sw.read_text(encoding="utf-8", errors="ignore").splitlines()[:6]
    print("存在, %d 行" % len(sw.read_text(encoding='utf-8', errors='ignore').splitlines()))
    for l in lines:
        print("   ", l[:110])
else:
    print("不存在")

print("\n=== ④ vol_signal 在工作流引擎里的引用 ===")
root = Path(r"D:\Hermes Agent CN Desktop\stock-workflow")
needle = "vol_signal"
skip = {"__pycache__", ".git", "node_modules", ".venv", "data", "logs"}
hits = []
for dp, dn, fn in os.walk(root):
    dn[:] = [d for d in dn if d not in skip]
    for f in fn:
        if not f.endswith((".py", ".yaml", ".yml")):
            continue
        fp = Path(dp) / f
        try:
            t = fp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if needle in t:
            for i, line in enumerate(t.splitlines(), 1):
                if needle in line:
                    hits.append("%s:%d  %s" % (fp.relative_to(root), i, line.strip()[:110]))
                    break
print("命中:", len(hits))
for h in hits[:12]:
    print("  ", h)

print("\n=== ⑤ weekly_evolution.py 行数 ===")
we = root / "weekly_evolution.py"
print(we.exists(), sum(1 for _ in we.open(encoding="utf-8", errors="ignore")) if we.exists() else "-")
