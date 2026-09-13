# -*- coding: utf-8 -*-
"""端到端验证 trades.json 持久化修复"""
import sys, json, warnings
sys.path.insert(0, '.')
warnings.filterwarnings('ignore')
from pathlib import Path
from unittest.mock import patch
from executor.sim_account import SimAccount

ROOT = Path(r"D:\Hermes Agent CN Desktop\stock-workflow")
data_dir = ROOT / "data"
trades_file = data_dir / "agent_短线狙击手" / "trades.json"
state_file = data_dir / "agent_短线狙击手" / "state.json"

# mock 行情: 600001/600002 正常价(非涨跌停) — limit_up/down 随价动态, 防误拦
def _fake_quotes(codes):
    return {c: {"price": 10.0, "limit_up": 999.0, "limit_down": 0.01} for c in codes}

print("=== 1. sim_trades.json 内容 (迁移后) ===")
sim = json.loads((data_dir / "sim_trades.json").read_text(encoding="utf-8"))
for t in sim:
    print(f"  {t.get('time','')[:16]} {t.get('action')} {t.get('code')} {t.get('reason','')[:30]}")

print()
print("=== 2. SimAccount 加载 GBK-迁移后文件 ===")
with patch("data.sources.get_tencent_quotes", side_effect=_fake_quotes):
    acc = SimAccount(1_000_000, {}, state_path=state_file, trades_path=trades_file)
print(f"  加载 trades: {len(acc.trades)}条 (修复前=0)")
assert len(acc.trades) > 0, "trades 必须能加载"
print("  ✅ 加载成功, 不再丢失")

print()
print("=== 3. 模拟 buy+sell 后重启再加载 (持久化闭环) ===")
# 用临时文件避免污染真实账户
tmp_state = data_dir / "_test_persist_state.json"
tmp_trades = data_dir / "_test_persist_trades.json"
if tmp_state.exists(): tmp_state.unlink()
if tmp_trades.exists(): tmp_trades.unlink()

# 第一次: 买入
with patch("data.sources.get_tencent_quotes", side_effect=_fake_quotes):
    acc1 = SimAccount(1_000_000, {}, state_path=tmp_state, trades_path=tmp_trades)
    r = acc1.buy("600001", 10.0, 100, "persist_test")
    assert r.get("success"), r
    acc1._save()

    # 模拟进程重启: 新实例重新加载
    acc2 = SimAccount(1_000_000, {}, state_path=tmp_state, trades_path=tmp_trades)
    print(f"  重启后加载: {len(acc2.trades)}条 (应≥1, 修复前=0)")
    assert len(acc2.trades) >= 1, "重启后记录必须保留"
    print(f"  记录内容: {acc2.trades[-1].get('reason')} @ {acc2.trades[-1].get('time','')[:19]}")
    print("  ✅ 重启后记录保留 (持久化闭环 OK)")

    # 再买入一笔, 验证追加不覆盖
    acc2.buy("600002", 20.0, 100, "persist_test2")
    acc3 = SimAccount(1_000_000, {}, state_path=tmp_state, trades_path=tmp_trades)
    print(f"  两次买入后加载: {len(acc3.trades)}条 (应=2, 追加不覆盖)")
    assert len(acc3.trades) == 2, f"应2条, got {len(acc3.trades)}"
    print("  ✅ 追加不覆盖 (历史记录累积)")

# 验证编码: 写入的是 UTF-8
raw = tmp_trades.read_bytes()
raw.decode("utf-8")  # 不抛异常 = UTF-8
print("  ✅ 写入编码=UTF-8")

# 清理临时文件
for f in (tmp_state, tmp_trades):
    if f.exists(): f.unlink()

print()
print("=== 持久化修复 全部验证通过 ===")

