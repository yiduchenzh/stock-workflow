# -*- coding: utf-8 -*-
"""修正: or 链使 0(不限) 被吞 → 改显式 None 判断"""
import io
import os
import py_compile
import shutil
from datetime import datetime

ROOT = r"D:\Hermes Agent CN Desktop\stock-workflow"
p = os.path.join(ROOT, "executor", "sim_account.py")
raw = io.open(p, encoding="utf-8", newline="").read()
nl = "\r\n" if "\r\n" in raw else "\n"
src = raw.replace("\r\n", "\n")

OLD = '''        try:
            _cfg0 = self.config or {}
            _cap = (_cfg0.get("max_opens_per_day")
                    or (_cfg0.get("execution") or {}).get("max_opens_per_day")
                    or (_cfg0.get("risk") or {}).get("max_opens_per_day"))
            _cap = 2 if _cap is None else int(_cap)
        except Exception:
            _cap = 2'''
NEW = '''        try:
            # ⚠️ 必须用显式 None 判断: `0 or x or y` 会把「0=不限」吞成默认值(实测踩过)
            _cfg0 = self.config or {}
            _cap = _cfg0.get("max_opens_per_day")
            if _cap is None:
                _cap = (_cfg0.get("execution") or {}).get("max_opens_per_day")
            if _cap is None:
                _cap = (_cfg0.get("risk") or {}).get("max_opens_per_day")
            _cap = 2 if _cap is None else int(_cap)
        except Exception:
            _cap = 2'''

if NEW in src:
    print("[SKIP] 已修正")
else:
    assert src.count(OLD) == 1, "锚点 count=%d" % src.count(OLD)
    bk = os.path.join(ROOT, "_restore", "fix5_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(bk, exist_ok=True)
    shutil.copy2(p, os.path.join(bk, "sim_account.py"))
    src = src.replace(OLD, NEW, 1)
    out = src.replace("\n", nl) if nl == "\r\n" else src
    tmp = p + ".chk.py"
    io.open(tmp, "w", encoding="utf-8", newline="").write(out)
    py_compile.compile(tmp, doraise=True)
    os.remove(tmp)
    io.open(p, "w", encoding="utf-8", newline="").write(out)
    print("[OK] 0=不限 现在可正确表达 (备份 %s)" % bk)
