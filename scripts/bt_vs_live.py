"""回测 vs 实盘绩效对比 — 检测过拟合和策略衰减"""
import json, logging
from pathlib import Path

logger = logging.getLogger("aurora.btlive")
DATA = Path(__file__).resolve().parent.parent / "data"

def load_backtest_result():
    """加载最近一次回测结果"""
    candidates = ["bt_full_2020.json","bt_r24_5yr.json","bt_verify.json","bt_upgrade_verify.json"]
    for f in candidates:
        p = DATA / f
        if p.exists():
            try: return json.loads(p.read_text())
            except: continue
    return None

def load_live_performance():
    """加载实盘表现(from sim_state.json)"""
    sf = DATA / "sim_state.json"
    tf = DATA / "sim_trades.json"
    if not sf.exists():
        return None
    try:
        state = json.loads(sf.read_text())
        trades = json.loads(tf.read_text()) if tf.exists() else []
        positions = state.get("positions", {})
        total_value = state.get("cash", 1000000) + sum(
            p.get("shares",0)*p.get("current_price",p.get("avg_cost",0)) for p in positions.values())
        return {
            "total_value": total_value,
            "total_trades": len(trades),
            "positions_count": len(positions),
            "cash": state.get("cash", 0),
        }
    except:
        return None

def compare():
    """对比回测vs实盘"""
    bt = load_backtest_result()
    live = load_live_performance()
    
    if not bt and not live:
        return {"status": "no_data", "message": "尚无回测或实盘数据"}
    
    report = {"timestamp": __import__("time").time(), "bt": {}, "live": {}, "gap": {}}
    
    if bt:
        report["bt"] = {
            "pf": bt.get("pf", bt.get("profit_factor", 0)),
            "win_rate": bt.get("win_rate", bt.get("wr", 0)),
            "total_return": bt.get("total_return", bt.get("ret", 0)),
            "max_dd": bt.get("max_dd", bt.get("max_drawdown", 0)),
            "trades": bt.get("trades", 0),
        }
    
    if live:
        report["live"] = live
        initial = 1000000
        report["live"]["total_return_pct"] = round((live["total_value"] - initial) / initial * 100, 2)
    
    if bt and live:
        bt_ret = report["bt"].get("total_return", 0)
        live_ret = report["live"].get("total_return_pct", 0)
        report["gap"] = {
            "return_diff": round(live_ret - bt_ret, 2),
            "conclusion": "正常" if abs(live_ret - bt_ret) < 20 else "异常,需检查过拟合",
            "alert": abs(live_ret - bt_ret) > 20,
        }
    
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "bt_vs_live.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    logger.info(f"[BTLive] 对比完成: {report.get('gap',{}).get('conclusion','等待数据')}")
    return report

if __name__ == "__main__":
    r = compare()
    print(json.dumps(r, indent=2, ensure_ascii=False))