"""多Agent启动器 — 共享市场数据,避免重复请求"""
import sys, json, time, logging
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).resolve().parent))
logging.basicConfig(level=logging.WARNING)

from multi_agent.coordinator import MultiAgentCoordinator

logger = logging.getLogger("aurora.launcher")

def main():
    c = MultiAgentCoordinator()
    
    # 1. 清数据
    n = c.clear_all_data()
    print(f"[1] 清除: {n}个旧文件")
    
    # 2. 仅运行一次市场扫描(所有Agent共享)
    from core.engine import AuroraEngine
    shared = AuroraEngine()
    print("[2] 市场扫描...", end=" ")
    shared.step_market()
    print(f"{shared.market_regime}({shared.market_score}/100)")
    
    # 3. 逐个运行Agent(共享市场数据,跳过step_market)
    for i, (name, agent) in enumerate(c.agents.items()):
        print(f"[3.{i+1}] {name}...", end=" ")
        try:
            # 用共享引擎的数据加速
            agent.engine = AuroraEngine()
            agent.engine.market_regime = shared.market_regime
            agent.engine.market_score = shared.market_score
            agent.engine.profile_name = name
            agent.engine._apply_profile()
            agent.engine.run()
            agent._execute_plans()
            agent._save_state()
            s = agent.get_summary()
            print(f"{s['total_value']:.0f}元")
        except Exception as e:
            print(f"跳过({str(e)[:30]})")
    
    # 4. 推送
    c.push_aggregate_report()
    r = c.get_aggregate_report()
    print(f"\n[4] 6AI交易员测试结果:")
    print(r['summary'])
    print("微信已推送")
    return c

if __name__ == "__main__":
    main()
