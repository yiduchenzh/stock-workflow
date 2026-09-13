"""多Agent启动器v2 — 共享数据缓存,避免重复API请求"""
import sys, time, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("aurora.launcher")

from multi_agent.coordinator import MultiAgentCoordinator

def main():
    # 1. 清除旧数据
    c = MultiAgentCoordinator()
    n = c.clear_all_data()
    print(f"[1] 清除: {n}个旧文件")
    
    # 2. 共享缓存获取市场状态(只请求1次API)
    from data.shared_cache import cache
    state = cache.get_market_state(force_refresh=True)
    print(f"[2] 市场: {state['regime']}({state['score']}/100)")
    
    # 3. 逐个启动Agent(跳过各自的市场扫描,直接共享数据)
    for i, (name, agent) in enumerate(c.agents.items()):
        print(f"[3.{i+1}] {name}...", end=" ")
        try:
            # 使用共享数据,不重新请求API
            from core.engine import AuroraEngine
            agent.engine = AuroraEngine()
            agent.engine.profile_name = name
            agent.engine._apply_profile()
            agent.engine.market_regime = state['regime']
            agent.engine.market_score = state['score']
            
            # 只运行策略分析(跳过step_market)
            if hasattr(agent.engine, 'step_cascade'): agent.engine.step_cascade()
            if hasattr(agent.engine, 'step_screen'): agent.engine.step_screen()
            
            # 模拟执行
            agent._execute_plans()
            agent._save_state()
            
            s = agent.get_summary()
            print(f"{s['total_value']:.0f}元 仓位{s['positions']}")
        except Exception as e:
            print(f"跳过({str(e)[:30]})")
    
    # 4. 推送
    c.push_aggregate_report()
    r = c.get_aggregate_report()
    print(f"\n[4] 6AI交易员:")
    for line in r['summary'].split(chr(10)):
        print(f"  {line}")
    print(f"缓存命中率: {cache.stats()['hit_rate']}%")
    print("微信已推送")

if __name__ == "__main__":
    main()
