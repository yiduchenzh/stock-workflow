"""多用户启动器v2 — 跳过重复API,共享市场数据"""
import sys, time, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("aurora.multi")

from multi_user import UserManager
from data.shared_cache import cache

def main():
    um = UserManager()
    
    # 1. 共享市场数据(仅1次API)
    state = cache.get_market_state(force_refresh=True)
    print(f"[1] 市场: {state['regime']}({state['score']}/100)")
    
    # 2. 每个用户运行Agent(跳过市场扫描)
    from core.engine import AuroraEngine
    for i, (uid, user) in enumerate(um.users.items()):
        print(f"[2.{i+1}] 用户{uid}...")
        for j, (name, agent) in enumerate(user.agents.items()):
            try:
                agent.engine = AuroraEngine()
                agent.engine.profile_name = name
                agent.engine._apply_profile()
                agent.engine.market_regime = state["regime"]
                agent.engine.market_score = state["score"]
                # 只跑策略步骤,跳过市场扫描
                if hasattr(agent.engine, "step_cascade"): agent.engine.step_cascade()
                agent._execute_plans()
                agent._save_state()
            except Exception as e:
                print(f"    {name}: {str(e)[:30]}")
    
    # 3. 汇总
    r = um.get_aggregate_report()
    print(f"[3] 总用户: {len(um.users)}")
    for line in r["summary"].split(chr(10)):
        print(f"  {line.strip()}")
    um._push_report(r)
    print("微信已推送")

if __name__ == "__main__":
    main()
