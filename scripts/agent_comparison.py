"""6Agent对比追踪器 — 每个Agent独立PnL, 排名, 对比"""
import json, sys
from pathlib import Path
from datetime import datetime

ROOT = Path(r"D:\Hermes Agent CN Desktop\stock-workflow")

def snapshot_all():
    """记录所有Agent当前状态到对比文件"""
    sys.path.insert(0, str(ROOT))
    from multi_agent.coordinator import MultiAgentCoordinator, ALL_PROFILES
    
    coord = MultiAgentCoordinator()
    summaries = {name: coord.agents[name].get_summary() for name in ALL_PROFILES}
    
    tracker_file = ROOT / "data" / "agent_comparison.json"
    history = []
    if tracker_file.exists():
        history = json.loads(tracker_file.read_text())
    
    entry = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "date": str(datetime.now().date()),
        "agents": summaries,
        "total_capital": sum(s["total_value"] for s in summaries.values()),
        "total_pnl": sum(s["pnl"] for s in summaries.values()),
    }
    history.append(entry)
    tracker_file.write_text(json.dumps(history[-90:], indent=2, ensure_ascii=False))
    return entry

def print_report():
    tracker_file = ROOT / "data" / "agent_comparison.json"
    if not tracker_file.exists():
        print("尚无对比数据")
        return
    
    history = json.loads(tracker_file.read_text())
    if not history:
        print("空记录")
        return
    
    last = history[-1]
    agents = last["agents"]
    
    print("=" * 65)
    print("  6AI交易员 — 盈亏对比")
    print("=" * 65)
    print(f"\n  时间: {last['time']}")
    
    # 按收益率排序
    ranked = sorted(agents.items(), key=lambda x: x[1]["return_pct"], reverse=True)
    
    print(f"\n  {'排名':<4} {'交易员':<14} {'总资产':>10} {'日盈亏':>9} {'收益率':>8} {'持仓':>4}")
    print(f"  {'-'*49}")
    for i, (name, s) in enumerate(ranked, 1):
        arrow = "📈" if s["pnl"] >= 0 else "📉"
        print(f"  {i:<4} {name:<14} {s['total_value']:>10,.0f} {arrow}{s['pnl']:>+8.0f} {s['return_pct']:>+7.4f}% {s['positions']:>4}只")
    
    print(f"\n  6账户合计:")
    print(f"    总资本: {last['total_capital']:,.0f}")
    print(f"    总盈亏: {last['total_pnl']:+,.0f}")
    print(f"    平均收益率: {sum(s['return_pct'] for s in agents.values())/len(agents):+.4f}%")
    
    # 最佳/最差
    best = ranked[0]
    worst = ranked[-1]
    print(f"\n  🏆 最佳: {best[0]} ({best[1]['return_pct']:+.4f}%)")
    print(f"  😞 最差: {worst[0]} ({worst[1]['return_pct']:+.4f}%)")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--snapshot":
        snapshot_all()
        print("[6Agent] 快照已保存")
    else:
        print_report()
