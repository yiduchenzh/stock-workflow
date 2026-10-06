import glob
import os

os.chdir(r"D:\Hermes Agent CN Desktop\stock-workflow")


def n(pat, exclude_init=True):
    fs = [f for f in glob.glob(pat) if not (exclude_init and os.path.basename(f) == "__init__.py")]
    return len(fs)


print("strategies .py      =", n("strategies/*.py"))
print("screening .py       =", n("screening/*.py"))
print("tests test_*.py     =", len(glob.glob("tests/test_*.py")))
print("scripts .py         =", n("scripts/*.py"))
print("root .bat           =", len(glob.glob("*.bat")))
print("root .md            =", len(glob.glob("*.md")))
print("data/*.md           =", len(glob.glob("data/*.md")))
print("core/engine.py 行数 =", sum(1 for _ in open("core/engine.py", encoding="utf-8", errors="ignore")))
tot = 0
for d in ("core", "risk", "monitor", "executor", "multi_agent"):
    c = n(d + "/*.py")
    tot += c
    print("%-12s .py = %d" % (d, c))
print("五层合计 =", tot)
print("multi_agent 目录:", sorted(os.listdir("multi_agent")))
print("research/warfare_validation:", sorted(os.listdir("research/warfare_validation"))[:20])
