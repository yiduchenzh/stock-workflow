# -*- coding: utf-8 -*-
"""阶段2 修复 P0-2 补丁②(v2): close_day() 内补 画像预算入账(record_pnl)

v1 插入的 close_day 块是 LF 行尾(文件其余为 CRLF) → 锚点(含 CR)匹配不到。
本版: ①把 close_day 整段统一为 CRLF ②在 return 前插入 budget.record_pnl 段。
主 sim 的 engine.step_close() 有此步(engine.py:2181-2187), Agent 侧缺 → 铁律4。
"""
import io
import py_compile
import shutil
from pathlib import Path

ROOT = Path(r"D:\Hermes Agent CN Desktop\stock-workflow")
AG = ROOT / "multi_agent" / "agent.py"

INSERT_LINES = [
    "        # 2026-09-24 weekly-review P0-2: profile budget entry (same as",
    "        #   engine.step_close -> budget.record_pnl). RiskBudget resolves its file",
    "        #   from the AURORA_AGENT env var, so set it before instantiating.",
    "        try:",
    "            import os as _os",
    '            _os.environ["AURORA_AGENT"] = self.profile_name',
    "            from risk.budget import RiskBudget",
    '            _b = RiskBudget(getattr(acc, "cfg", None) or {}, float(self.capital))',
    "            _base = float(acc.day_baseline())",
    "            _cur = float(acc.total_value)",
    "            _dpnl = (_cur - _base) / _base if _base > 0 else 0.0",
    "            _b.record_pnl(_dpnl, _cur)",
    '            logger.info("[Close] %s budget: daily=%+.4f%% base=%.0f current=%.0f"',
    "                        % (self.profile_name, _dpnl * 100, _base, _cur))",
    "        except Exception as e:",
    '            logger.warning("[Close] %s budget record failed: %s" % (self.profile_name, e))',
]

src = io.open(AG, encoding="utf-8", newline="").read()
assert "record_pnl" not in src, "already patched (idempotent exit)"

lines = src.split("\n")
i = next(k for k, l in enumerate(lines) if l.startswith("    def close_day(self) -> dict:"))
j = next(k for k in range(i + 1, len(lines))
         if lines[k].startswith("    def _sync_account(self):"))
print("[POS] close_day: line %d..%d" % (i + 1, j))

# ① 该段行尾统一 CRLF
n_fixed = 0
for k in range(i, j):
    body = lines[k][:-1] if lines[k].endswith("\r") else lines[k]
    new = body + "\r"
    if new != lines[k]:
        n_fixed += 1
    lines[k] = new
print("[EOL] 归一 CRLF: %d 行" % n_fixed)

# ② 在 return 前插入 budget 段
ri = next(k for k in range(i, j) if lines[k].startswith('        return {"profile": self.profile_name, "prices": updated,'))
lines[ri:ri] = [l + "\r" for l in INSERT_LINES]
print("[INS] budget 段插入于 line %d" % (ri + 1))

bak = AG.with_suffix(AG.suffix + ".bak0924b")
if not bak.exists():
    shutil.copy2(AG, bak)
    print("[BAK] %s" % bak.name)

io.open(AG, "w", encoding="utf-8", newline="").write("\n".join(lines))
py_compile.compile(str(AG), doraise=True)
print("[OK ] agent.py written + compiles")

back = io.open(AG, encoding="utf-8").read().splitlines()
k = next(x for x, l in enumerate(back) if "def close_day(self)" in l)
print("[RBK] close_day 回读:")
for l in back[k: k + 45]:
    print("      " + l)
