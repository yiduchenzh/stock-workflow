# -*- coding: utf-8 -*-
"""阶段2 量测第三批: 落单路径(prev_close_B 计划从哪来) + 画像 budget 日收益传参点 + 板块源"""
import os
import re

BASE = os.getcwd()
D = os.path.join(BASE, "data")

def scan(pats, exts=(".py",), limit=40):
    out = []
    for root, _d, fs in os.walk(BASE):
        if any(x in root for x in (".git", "__pycache__", ".venv", "node_modules")):
            continue
        for f in fs:
            if not f.endswith(exts):
                continue
            p = os.path.join(root, f)
            try:
                src = open(p, encoding="utf-8", errors="replace").read()
            except Exception:
                continue
            for i, line in enumerate(src.splitlines(), 1):
                for pat in pats:
                    if re.search(pat, line):
                        out.append((os.path.relpath(p, BASE), i, line.strip()[:165]))
                        break
            if len(out) > limit * 3:
                break
    return out[:limit]

print("=" * 22, "① 谁在按 Agent 生成 plan（coordinator/agent 计划入口）")
for h in scan([r"def plan.*agent", r"coordinator", r"class .*Coordinator", r"agent_plan", r"per_agent",
               r"def .*_plan\(", r"generate_plan"], limit=30):
    print(f"   {h[0]}:{h[1]}: {h[2]}")

print("\n" + "=" * 22, "② prev_close_B 计划生成/落单路径")
for h in scan([r"prev_close_B", r"prev_close_A"], limit=30):
    print(f"   {h[0]}:{h[1]}: {h[2]}")

print("\n" + "=" * 22, "③ 画像 budget 日收益传参（record_daily / pnl_pct 计算）")
for h in scan([r"record_daily", r"record\(.*pnl", r"pnl_pct", r"_budget_file_path", r"RiskBudget\("], limit=40):
    print(f"   {h[0]}:{h[1]}: {h[2]}")

print("\n" + "=" * 22, "④ 板块数据源（新浪/东财板块接口）")
for h in scan([r"板块", r"sector.*requests|requests.*sector", r"getHQNodeData", r"push2.*clist", r"f14\b"],
              limit=30):
    print(f"   {h[0]}:{h[1]}: {h[2]}")
