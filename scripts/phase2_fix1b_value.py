# -*- coding: utf-8 -*-
"""阶段2 修复①修正: 价值画像不再降 B 型(避免重演 v14.49 死账户), 改为「A 型主导」差异化
- A 型(挖坑低吸, 与 30天+ 价值画像一致) 2.0 → 3.0
- B 型(追涨短线) 保持 2.0 → 账户不重新饿死(v1449 回归测试同步通过)
"""
import io
import py_compile

P = r"D:\Hermes Agent CN Desktop\stock-workflow\profiling\trader_types.py"
src = io.open(P, encoding="utf-8", newline="").read()
NL = "\r\n" if "\r\n" in src else "\n"
for tag in ("① strategy_weights L66", "② signal_prefer L142"):
    old = '"prev_close_A": 3.0, "prev_close_B": 1.0}'
    assert src.count(old) == 2, f"锚点命中 {src.count(old)} 次(期望2): {tag}"
src = src.replace('"prev_close_A": 3.0, "prev_close_B": 1.0}',
                  '"prev_close_A": 3.0, "prev_close_B": 2.0}')
io.open(P, "w", encoding="utf-8", newline="").write(src)
py_compile.compile(P, doraise=True)
print("✅ 价值画像: A 3.0 / B 2.0 (A 主导 + 保活) — py_compile 通过")

import importlib.util
spec = importlib.util.spec_from_file_location("tt", P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print("\n=== 5 画像『可单信号确认(≥2.0)』信号集合 ===")
sets = {}
for nm, prof in m.TRADER_PROFILES.items():
    s = {k for k, v in prof["strategy_weights"].items() if v >= 2.0}
    sets[nm] = s
    print(f"  {nm:<10} {sorted(s)}")
print(f"\n不同集合数: {len({frozenset(v) for v in sets.values()})} (修复前=1~2, 目标≥3)")
