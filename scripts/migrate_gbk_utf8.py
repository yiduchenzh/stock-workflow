# -*- coding: utf-8 -*-
"""迁移 GBK-only JSON 文件为 UTF-8 (v14.46 trades.json 持久化修复)"""
import json
from pathlib import Path

ROOT = Path(r"D:\Hermes Agent CN Desktop\stock-workflow")
data_dir = ROOT / "data"

targets = [
    data_dir / "agent_aggregate.json",
    data_dir / "agent_comparison.json",
    data_dir / "shared_watchlist.json",
    data_dir / "sim_trades.json",
    data_dir / "agent_上班族中短线" / "trades.json",
    data_dir / "agent_价值投资者" / "trades.json",
    data_dir / "agent_新手入门" / "trades.json",
    data_dir / "agent_短线狙击手" / "trades.json",
    data_dir / "agent_趋势跟踪者" / "trades.json",
]

for p in targets:
    if not p.exists():
        print(f"  ⚠️ 不存在: {p.name}")
        continue
    raw = p.read_bytes()
    try:
        raw.decode("utf-8")
        print(f"  ✅ 已是UTF-8: {p.relative_to(ROOT)}")
        continue
    except UnicodeDecodeError:
        pass
    # GBK → 内容读出来 → 重写 UTF-8
    try:
        text = raw.decode("gbk")
        data = json.loads(text)
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        # 验证
        back = json.loads(p.read_text(encoding="utf-8"))
        print(f"  🔄 已迁移UTF-8: {p.relative_to(ROOT)} ({len(data)}条 → {len(back)}条)")
    except Exception as e:
        print(f"  ❌ 迁移失败 {p.relative_to(ROOT)}: {e}")

print("\n=== 迁移完成, 验证读取 ===")
# 重新用 UTF-8 读短线狙击手 trades
t = json.loads((data_dir / "agent_短线狙击手" / "trades.json").read_text(encoding="utf-8"))
print(f"短线狙击手 trades: {len(t)}条 (UTF-8 读取成功)")
for x in t[:3]:
    print(f"  {x.get('time','')[:16]} {x.get('action')} {x.get('code')}")
