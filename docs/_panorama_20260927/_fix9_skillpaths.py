import os
import re
from pathlib import Path

SK = Path(r"C:\Users\User871619\AppData\Roaming\cn.org.hermesagent.desktop\runtime\hermes-home\skills")
FILES = [
    SK / "trading/a-share-backtest/SKILL.md",
    SK / "trading/a-share-trading-system-design/SKILL.md",
    SK / "trading/a-share-web-data-architecture/SKILL.md",
    SK / "trading/limitup-prevclose-system/SKILL.md",
    SK / "trading/limitup-prevclose-trading/SKILL.md",
    SK / "trading/mainrise-factor-signature/SKILL.md",
    SK / "trading/real-time-financial-dashboard/SKILL.md",
    SK / "stock-trading/hikyuu-reference/SKILL.md",
]

OLD_BASES = [
    r"C:\Users\chenzhang\AppData\Local\Hermes Agent CN Desktop",
    r"C:\\Users\\chenzhang\\AppData\\Local\\Hermes Agent CN Desktop",
    "C:/Users/chenzhang/AppData/Local/Hermes Agent CN Desktop",
    "C:\\\\Users\\\\chenzhang\\\\AppData\\\\Local\\\\Hermes Agent CN Desktop",
]
NEW_BASE = r"D:\Hermes Agent CN Desktop"
NEW_BASE_ESC = r"D:\\Hermes Agent CN Desktop"

OLD_VENV = [
    r"D:\Hermes Agent CN Desktop\.venv",
    r"D:\\Hermes Agent CN Desktop\\.venv",
    "D:/Hermes Agent CN Desktop/.venv",
]
NEW_VENV = r"D:\Hermes Agent CN Desktop\hunter-v2\.venv"
NEW_VENV_ESC = r"D:\\Hermes Agent CN Desktop\\hunter-v2\\.venv"

NOTE = """

---

## 路径校正 (2026-09-27 · 本机实测)

本文正文里原先出现的 `C:\\Users\\chenzhang\\AppData\\Local\\Hermes Agent CN Desktop\\...` 是**旧机器/旧用户**路径，
本机已不存在（`ls C:/Users/chenzhang` → No such file or directory）。已批量改为本机真实路径：

| 用途 | 本机真实路径 |
|---|---|
| 双工程根 | `D:\\Hermes Agent CN Desktop\\` |
| hunter-v2（web 工程） | `D:\\Hermes Agent CN Desktop\\hunter-v2` |
| stock-workflow（工作流引擎） | `D:\\Hermes Agent CN Desktop\\stock-workflow` |
| limitup-system | `D:\\Hermes Agent CN Desktop\\limitup-system` |
| Python（带 mootdx） | `D:\\Hermes Agent CN Desktop\\hunter-v2\\.venv\\Scripts\\python.exe` |
| Python（工作流引擎） | `D:\\Hermes Agent CN Desktop\\stock-workflow\\.venv\\Scripts\\python.exe` |

⚠️ 注意：**工作区级 `Hermes Agent CN Desktop\\.venv` 在本机不存在**（旧文多处引用它）——
hunter-v2 的 launcher.py 候选顺序 `[hunter_dir/.venv, dirname(hunter_dir)/.venv]` 第一个就命中，
即直接用 `hunter-v2\\.venv`。引用旧 venv 的命令行请改指 hunter-v2 的 venv。
"""

changed = []
for f in FILES:
    if not f.exists():
        print("MISSING:", f)
        continue
    txt = f.read_text(encoding="utf-8")
    orig = txt
    for i, ob in enumerate(OLD_BASES):
        nb = NEW_BASE_ESC if "\\\\" in ob else (NEW_BASE if "\\" in ob and "C:\\\\" not in ob else NEW_BASE)
        txt = txt.replace(ob, nb)
    # venv: 先精确替换带转义的两级路径
    txt = txt.replace('C:\\\\Users\\\\chenzhang\\\\AppData\\\\Local\\\\Hermes Agent CN Desktop\\\\.venv', NEW_VENV_ESC)
    txt = txt.replace(r"C:\Users\chenzhang\AppData\Local\Hermes Agent CN Desktop\.venv", NEW_VENV)
    txt = txt.replace(r"D:\Hermes Agent CN Desktop\.venv", NEW_VENV)
    txt = txt.replace(r"D:\\Hermes Agent CN Desktop\\.venv", NEW_VENV_ESC)
    txt = txt.replace("D:/Hermes Agent CN Desktop/.venv", NEW_VENV.replace("\\", "/"))
    if "## 路径校正 (2026-09-27" not in txt:
        txt = txt.rstrip() + NOTE
    if txt != orig:
        f.write_text(txt, encoding="utf-8")
        changed.append((f, len(orig.splitlines()), len(txt.splitlines())))

print("已改文件数:", len(changed))
for f, a, b in changed:
    print("  %-62s %d → %d 行" % (str(f).replace(str(SK), ""), a, b))

print("\n=== 残留 chenzhang 检查 ===")
left = []
for f in FILES:
    t = f.read_text(encoding="utf-8")
    for i, line in enumerate(t.splitlines(), 1):
        if "chenzhang" in line and "旧机器" not in line and "已不存在" not in line:
            left.append("%s:%d %s" % (f.name, i, line.strip()[:90]))
print("残留真实引用:", len(left))
for x in left[:10]:
    print("  ", x)
