"""Aurora 双轨工作流
   模拟账户: 全自动交易(用于跟踪回测)
   实盘: 推送微信 → 您在涨乐财富通手动操作
"""
import sys, time, logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
_log_dir = Path("logs"); _log_dir.mkdir(exist_ok=True)
_fh = RotatingFileHandler(str(_log_dir/"aurora.log"),maxBytes=10485760,backupCount=5,encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
logging.getLogger().addHandler(_fh); logging.getLogger().setLevel(logging.INFO)
sys.path.insert(0, str(Path(__file__).resolve().parent))

def phase_morning():
    """晨盘: 模拟全自动交易 + 实盘推送微信"""
    from core.engine import AuroraEngine
    from executor.ht_bridge import create_executor
    from notify.pusher import push_morning_report, push_trade_plan
    import json
    
    logger = logging.getLogger("aurora.dual")
    
    # 1. 引擎运行
    e = AuroraEngine()
    e.run()
    logger.info(f"[Dual] 引擎完成: {e.market_regime}({e.market_score:.0f}) 计划{len(e.plans)}笔")
    
    # 2. 模拟账户自动执行(仅模拟,跟踪回测)
    sim = create_executor(mode="sim")
    executed = []
    for p in e.plans[:5]:
        action = p.get("action", "buy")
        code = p.get("code", "")
        price = p.get("entry_price", 0)
        shares = p.get("shares", 100)
        if action == "buy":
            r = sim.buy(code, price, shares, reason=p.get("strategy",""))
        else:
            r = sim.sell(code, price, shares, reason=p.get("strategy",""))
        if r.get("success"):
            executed.append({"code":code,"action":action,"shares":shares,"price":price})
    
    if executed:
        logger.info(f"[Dual] 模拟执行: {len(executed)}笔")
        # 保存模拟状态
        Path("data/sim_state.json").write_text(json.dumps(sim.get_account_info()))
    
    # 3. 推送微信(实盘半自动)
    try: push_morning_report(e)
    except: pass
    try: push_trade_plan(e)
    except: pass
    
    # 4. 输出摘要
    info = sim.get_account_info()
    print(f"\n【双轨晨盘】{e.market_regime}({e.market_score:.0f})")
    print(f"  模拟账户: {info['total_value']:.0f}元 | {info['positions']}持仓 | {len(executed)}笔新成交")
    print(f"  实盘: 请查看微信 → 在涨乐财富通操作")
    print(f"  画像: {e.profile_name} | 建议: {getattr(e,'trading_advice','')}")
    for p in e.plans[:3]:
        print(f"  {p.get('code','?')} {p.get('strategy','?')} @{p.get('entry_price',0):.2f}")

def phase_review():
    """复盘: 对比模拟vs实盘"""
    from notify.pusher import push_daily_review
    from scripts.bt_vs_live import compare
    try:
        r = compare()
        print(f"模拟vs回测对比: {r.get('gap',{}).get('conclusion','等待数据')}")
    except: pass
    try: push_daily_review(None)
    except: pass

if __name__ == "__main__":
    if "--review" in sys.argv:
        phase_review()
    else:
        phase_morning()