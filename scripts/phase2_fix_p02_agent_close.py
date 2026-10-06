# -*- coding: utf-8 -*-
"""阶段2 修复 P0-2 (v2): daily_run.py --phase close 追加 6Agent 收盘处理

v1 已成功改 multi_agent/agent.py（新增 TraderAgent.close_day()）。
本版只补 daily_run.py，采用「按行号块替换」规避 CRLF 锚点不匹配，并做幂等保护。
"""
import io
import py_compile
import shutil
from pathlib import Path

ROOT = Path(r"D:\Hermes Agent CN Desktop\stock-workflow")
DR = ROOT / "daily_run.py"
AG = ROOT / "multi_agent" / "agent.py"

# 幂等: agent.py 已改则跳过
ag_src = io.open(AG, encoding="utf-8", newline="").read()
print("[CHK] agent.py close_day 存在: %s" % ("def close_day(self)" in ag_src))
assert "def close_day(self)" in ag_src, "agent.py 未改成功, 先跑 v1"

src = io.open(DR, encoding="utf-8", newline="").read()
assert "a.close_day() for a in" not in src, "daily_run.py 已改过(幂等退出)"
assert "elif args.phase == \"close\":" in src, "close 分支未找到"

lines = src.split("\n")          # CRLF 文件: 每行尾部保留 \r
i = next(k for k, l in enumerate(lines) if l.strip().startswith('elif args.phase == "close":'))
j = next(k for k in range(i + 1, len(lines)) if lines[k].strip().startswith('elif args.phase == "review":'))
print("[POS] close 分支: line %d..%d" % (i + 1, j))

CR = "\r"
NEW = [
    'elif args.phase == "close":' + CR,
    '    logging.getLogger("aurora").info("[Close] 日终批量处理开始")' + CR,
    "    engine = AuroraEngine('config.yaml')" + CR,
    "    engine.step_close()" + CR,
    "    # 2026-09-24 weekly-review P0-2: 6Agent close handling (was missing entirely)" + CR,
    "    #   agent positions' current_price was only set at buy time and mark_day_close" + CR,
    "    #   never ran -> valuation stuck at cost -> per-profile budget gate dead." + CR,
    "    try:" + CR,
    "        from multi_agent.coordinator import MultiAgentCoordinator" + CR,
    "        _coord = MultiAgentCoordinator()" + CR,
    "        _res = [a.close_day() for a in _coord.agents.values()]" + CR,
    "        try:" + CR,
    "            _coord._save_aggregate()" + CR,
    "        except Exception:" + CR,
    "            pass" + CR,
    '        logging.getLogger("aurora").info("[Close] 6Agent close done: %s" % (_res,))' + CR,
    "    except Exception as _e:" + CR,
    '        logging.getLogger("aurora").warning("[Close] 6Agent close failed: %s" % _e)' + CR,
    '    logging.getLogger("aurora").info("[Close] 日终批量处理完成")' + CR,
]

bak = DR.with_suffix(DR.suffix + ".bak0924")
if not bak.exists():
    shutil.copy2(DR, bak)
    print("[BAK] %s" % bak.name)

lines[i:j] = NEW
io.open(DR, "w", encoding="utf-8", newline="").write("\n".join(lines))
py_compile.compile(str(DR), doraise=True)
print("[OK ] daily_run.py written + compiles")

print("[RBK] close 分支回读:")
back = io.open(DR, encoding="utf-8").read().splitlines()
k = next(x for x, l in enumerate(back) if l.strip().startswith('elif args.phase == "close":'))
for l in back[k: k + 20]:
    print("      " + l)
