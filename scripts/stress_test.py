"""极端场景压力测试 — 模拟股灾/千股跌停/流动性枯竭"""
import sys, json, numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SCENARIOS = {
    "千股跌停_2015": {"daily_drop": -0.095, "days": 5, "vol_drop": 0.9},
    "熔断_2016": {"daily_drop": -0.07, "days": 4, "vol_drop": 0.7},
    "疫情_2020": {"daily_drop": -0.08, "days": 3, "vol_drop": 0.5},
    "流动性枯竭": {"daily_drop": -0.05, "days": 10, "vol_drop": 0.95},
    "阴跌_2018": {"daily_drop": -0.02, "days": 30, "vol_drop": 0.6},
}

def run_stress_test(scenario_name="千股跌停_2015", initial_capital=1000000):
    """运行单个压力测试场景"""
    from executor.ht_bridge import SimBroker
    from risk.controls import check_all, reset as reset_risk
    
    scenario = SCENARIOS.get(scenario_name, SCENARIOS["千股跌停_2015"])
    reset_risk()
    
    broker = SimBroker(initial_capital)
    # 先买入3只股票各10万
    for code in ["600519", "000333", "300750"]:
        broker.buy(code, 100, 1000)
    
    results = {"scenario": scenario_name, "days": [], "survived": True}
    daily_drop = scenario["daily_drop"]
    
    for day in range(scenario["days"]):
        # 模拟当日暴跌
        for code, pos in list(broker.positions.items()):
            old_price = pos.get("current_price", pos["avg_cost"])
            new_price = old_price * (1 + daily_drop)
            pos["current_price"] = new_price
        
        # 检查风控
        total = broker.get_balance()["total"]
        drawdown = (total - initial_capital) / initial_capital
        results["days"].append({"day": day+1, "total": round(total, 2), "drawdown": round(drawdown*100, 2)})
        
        if drawdown < -0.20:
            results["survived"] = False
            results["fail_day"] = day + 1
            results["fail_reason"] = f"回撤{drawdown*100:.1f}%超过20%"
            break
    
    results["final_drawdown"] = round((broker.get_balance()["total"] - initial_capital) / initial_capital * 100, 2)
    return results

def run_all():
    """运行全部场景"""
    results = {}
    for name in SCENARIOS:
        results[name] = run_stress_test(name)
    Path("data/stress_test_report.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False))
    return results

if __name__ == "__main__":
    r = run_all()
    for name, res in r.items():
        status = "PASS" if res["survived"] else "FAIL"
        print(f"[{status}] {name}: {res['days'][-1]['drawdown']}% | 存活{res['days'][-1]['day']}天")