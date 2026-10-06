import os
from pathlib import Path

ROOTS = [Path(r"D:\Hermes Agent CN Desktop\hunter-v2\backend"),
         Path(r"D:\Hermes Agent CN Desktop\stock-workflow\strategies"),
         Path(r"D:\Hermes Agent CN Desktop\stock-workflow\screening"),
         Path(r"D:\Hermes Agent CN Desktop\stock-workflow\core"),
         Path(r"D:\Hermes Agent CN Desktop\stock-workflow\scripts"),
         Path(r"D:\Hermes Agent CN Desktop\stock-workflow\workflows")]
NEEDLES = ["trend_strong", "_trend_strong_meta", "ATR>8", "atr>8", "atr_pct"]
hits = []
for root in ROOTS:
    if not root.exists():
        print("缺失:", root)
        continue
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", "chanpy", "node_modules", "backtest_strategies")]
        for fn in filenames:
            if not fn.endswith((".py", ".json", ".md")):
                continue
            p = Path(dirpath) / fn
            try:
                if p.stat().st_size > 2_000_000:
                    continue
                txt = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for n in NEEDLES:
                if n in txt:
                    for i, line in enumerate(txt.splitlines(), 1):
                        if n in line:
                            hits.append("%s:%d  [%s]  %s" % (p, i, n, line.strip()[:120]))
                            break
for h in hits[:30]:
    print(h)
print("命中文件数 =", len({h.split(":")[0] for h in hits}), " 命中行 =", len(hits))
