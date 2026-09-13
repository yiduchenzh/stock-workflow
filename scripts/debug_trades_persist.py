# -*- coding: utf-8 -*-
"""诊断 trades.json 持久化丢失根因"""
import sys, json
sys.path.insert(0, '.')
import warnings
warnings.filterwarnings('ignore')
from pathlib import Path
from executor.sim_account import SimAccount

ROOT = Path(r"D:\Hermes Agent CN Desktop\stock-workflow")
data_dir = ROOT / "data" / "agent_短线狙击手"
trades_file = data_dir / "trades.json"
state_file = data_dir / "state.json"

print(f"trades_file: {trades_file} (exists={trades_file.exists()})")
print(f"state_file: {state_file} (exists={state_file.exists()})")

# 1. 直接加载当前文件
raw = trades_file.read_bytes()
print(f"\n1. 当前 trades.json: {len(raw)}B, 尝试编码...")
trades = None
for enc in ("utf-8", "gbk"):
    try:
        trades = json.loads(raw.decode(enc))
        print(f"   {enc}: OK, {len(trades)}条")
        break
    except Exception as e:
        print(f"   {enc}: 失败 {e}")

# 2. SimAccount._load 是否正确加载
print("\n2. SimAccount(trades_path=...) 加载:")
acc = SimAccount(1_000_000, {}, state_path=state_file, trades_path=trades_file)
print(f"   acc.trades: {len(acc.trades)}条")
if acc.trades:
    for t in acc.trades[:3]:
        print(f"     {t.get('time','')[:16]} {t.get('action')} {t.get('code')}")

# 3. AgentSimAccount 加载
print("\n3. AgentSimAccount 加载:")
sys.path.insert(0, str(ROOT))
from multi_agent.agent import AgentSimAccount
a = AgentSimAccount(1_000_000, {}, state_file, trades_file)
print(f"   agent.trades: {len(a.trades)}条")
print(f"   agent._inner.trades: {len(a._inner.trades)}条")

# 4. 模拟一次 buy 后看写入
print("\n4. 模拟 buy(600001, 10, 100) 后写入检查:")
a.buy("600001", 10.0, 100, "test_persistence")
after = json.loads(trades_file.read_bytes().decode("utf-8", errors="replace"))
print(f"   写入后 trades.json: {len(after)}条")
print(f"   历史记录保留: {any(t.get('code')=='603232' for t in after)}")
# 清理测试污染
a.sell("600001", 10.0, 100, "test_cleanup")
