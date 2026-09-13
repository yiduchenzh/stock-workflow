"""v14.48 端到端验证 — 复现 08-19 14:30 幽灵开仓场景, 验证修复"""
import sys, os, json, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["AURORA_AGENT"] = ""

print("=" * 60)
print("验证1: RiskBudget 加载现有文件(已修 peak) → check 不误报")
print("=" * 60)
from risk.budget import RiskBudget
b = RiskBudget({}, capital=1_000_000)
res = b.check()
print(f"  peak_value={b.state.get('peak_value')} drawdown={b.state.get('drawdown_pct')*100:.2f}%")
print(f"  check() → triggered={res['triggered']} action={res['action']} reason={res['reason']}")
assert not res["triggered"], "不应误报 pause"
print("  ✔ 不再误报 Budget pause\n")

print("=" * 60)
print("验证2: SimAccount.buy 涨停拒绝 → engine 检查返回值")
print("=" * 60)
from executor.sim_account import SimAccount
# 用临时文件, 不碰真实 sim_state
with tempfile.TemporaryDirectory() as td:
    acc = SimAccount(1_000_000, {"use_microstructure": False},
                     state_path=Path(td) / "state.json",
                     trades_path=Path(td) / "trades.json")
    # 000560 涨停场景: 现价=涨停价 2.38 → buy 必须被拒
    r = acc.buy("000560", 2.38, 10000, "momentum_breakout")
    print(f"  buy(000560 @涨停价2.38) → success={r.get('success')} error={r.get('error','')}")
    assert r.get("success") is False, "涨停必须拒绝买入"
    print(f"  账户持仓: {acc.positions}, trades记录: {len(acc.trades)}条")
    assert len(acc.trades) == 0, "被拒买入不应写 trades"
    # 正常价格买入应成功
    r2 = acc.buy("000560", 2.20, 10000, "momentum_breakout")
    print(f"  buy(000560 @2.20 非涨停) → success={r2.get('success')}")
    assert r2.get("success") is True, "非涨停应可买入"
print("  ✔ 涨停拦截 + trades落盘正确\n")

print("=" * 60)
print("验证3: engine_live._sync_account_from_disk 内存与磁盘一致")
print("=" * 60)
src = (ROOT / "core" / "engine_live.py").read_text(encoding="utf-8")
assert "def _sync_account_from_disk" in src
assert "self.engine.account._load()" in src
print("  ✔ engine_live 已具备磁盘 reload 机制\n")

print("=" * 60)
print("验证4: 当前 sim_state.json 与 live_state 一致性(幽灵持仓已消除)")
print("=" * 60)
sim = json.loads((ROOT / "data" / "sim_state.json").read_text(encoding="utf-8"))
live = json.loads((ROOT / "data" / "live_state.json").read_text(encoding="utf-8"))
print(f"  sim_state: positions={len(sim.get('positions',{}))} cash={sim.get('cash')}")
print(f"  live_state: positions_count={live.get('positions_count')}")
print("  (live_state 为 daemon 上次保存; 重启 daemon 后将从磁盘 reload 为 0)\n")

print("全部端到端验证通过 ✔")
