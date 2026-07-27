"""盈利追踪器 — PnL vs Token成本"""
import json
from pathlib import Path
from datetime import datetime, date
import sys

ROOT = Path(r"D:\Hermes Agent CN Desktop\stock-workflow")
TRACKER = ROOT / "data" / "pnl_tracker.json"

# Token成本 (deepseek-v4-flash): 约$0.15/M输入token, $0.60/M输出token
# 每次全管线~100K tokens, 约5美分
# 每次快速监控~20K tokens, 约1美分
TOKEN_COST_FULL = 0.05   # USD/次
TOKEN_COST_FAST = 0.01   # USD/次

def init():
    if TRACKER.exists():
        return json.loads(TRACKER.read_text())
    return {
        "created": str(datetime.now()),
        "currency": "CNY",
        "capital": 1000000,
        "daily": [],
        "total_token_usd": 0,
        "total_trade_pnl": 0,
    }

def record():
    t = init()
    today = str(date.today())
    if any(d["date"] == today for d in t["daily"]):
        return

    sim = json.loads((ROOT / "data" / "sim_state.json").read_text())
    prev = t["daily"][-1] if t["daily"] else None
    prev_total = prev["total"] if prev else t["capital"]
    pnl = round(sim["total"] - prev_total, 2)

    # 估算当日token消耗
    scans = 4  # 全管线: morning + 3次FullScan (review不计入)
    # 快速监控: 12次/小时 * 5.5交易小时 = 66次 (减午休)
    monitors = 66 if sim.get("positions") else 0
    token_cost = round(scans * TOKEN_COST_FULL + monitors * TOKEN_COST_FAST, 3)

    entry = {
        "date": today,
        "total": round(sim["total"], 2),
        "cash": round(sim["cash"], 2),
        "positions": len(sim.get("positions", {})),
        "pnl": pnl,
        "pnl_pct": round(pnl / prev_total * 100, 2) if prev_total else 0,
        "cum": round(sim["total"] - t["capital"], 2),
        "cum_pct": round((sim["total"] - t["capital"]) / t["capital"] * 100, 4),
        "token_usd": token_cost,
    }
    t["daily"].append(entry)
    t["total_token_usd"] = round(t.get("total_token_usd", 0) + token_cost, 3)
    TRACKER.write_text(json.dumps(t, ensure_ascii=False, indent=2))
    print(f"[PnL] {today}: 盈亏{pnl:+,.2f} Token${token_cost:.3f}")

def report():
    t = init()
    print("=" * 55)
    print("  Aurora 盈利追踪")
    print("=" * 55)
    print(f"\n  本金: {t['capital']:,.0f} CNY")
    
    daily = t.get("daily", [])
    if not daily:
        print("  尚无交易记录")
        return

    last = daily[-1]
    cum = last["cum"]
    cum_pct = last["cum_pct"]
    token_usd = t["total_token_usd"]
    token_cny = token_usd * 7.3
    net = cum - token_cny

    print(f"  当前值: {last['total']:,.2f}")
    print(f"  累计盈亏: {cum:+,.2f} ({cum_pct:+.4f}%)")
    print(f"  Token消耗: ${token_usd:.3f} ≈ ¥{token_cny:.2f}")
    print(f"  净收益(扣Token): {net:+,.2f}")
    if token_cny > 0:
        print(f"  ROI: {cum/token_cny*100:+.1f}%")
    
    print(f"\n  明细:")
    print(f"  {'日期':<12} {'总值':>10} {'日盈亏':>9} {'累计%':>8} {'Token$':>7}")
    print(f"  {'-'*46}")
    for d in daily:
        print(f"  {d['date']:<12} {d['total']:>10,.2f} {d['pnl']:>+8.2f} "
              f"{d['cum_pct']:>+7.4f}% ${d['token_usd']:<6.3f}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--record":
        record()
    else:
        report()
