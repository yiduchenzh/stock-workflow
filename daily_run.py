"""Aurora Trading — 每日自动运行 · 分阶段推送"""
import sys, logging, argparse, os
from logging.handlers import RotatingFileHandler
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
# 从.env加载环境变量 (解决计划任务SYSTEM用户无环境变量的问题)
try:
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().strip().split("\n"):
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()
except Exception:
    pass

# 非交易日直接退出 (周末/法定节假日)
try:
    from core.calendar import is_trading_day
    if not is_trading_day():
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
        logging.getLogger("aurora").info("[Calendar] 非交易日,跳过")
        sys.exit(0)
except Exception:
    from datetime import datetime
    if datetime.now().weekday() >= 5:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
        logging.getLogger("aurora").info("[Calendar] 周末,跳过")
        sys.exit(0)

LOG_DIR = os.path.join(os.path.dirname(__file__) or ".", "data")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[RotatingFileHandler(os.path.join(LOG_DIR, "aurora.log"), maxBytes=10*1024*1024, backupCount=3, encoding="utf-8"), logging.StreamHandler()])



parser = argparse.ArgumentParser()
parser.add_argument("--phase", default="full", choices=["auction","monitor","review","morning","full","multi_morning","multi_monitor","close"],
                   help="auction=竞价选股, monitor=盘中监控+T0, review=盘后复盘, morning=晨报, full=全流程, close=日终处理")
args = parser.parse_args()

from core.engine import AuroraEngine
from notify.pusher import push_auction_results, push_trade_signal, push_daily_review

engine = AuroraEngine('config.yaml')
engine.phase = args.phase  # 设置阶段: morning/monitor/auction/review

if args.phase == "auction":
    engine.step_cascade()
    engine.step_screen()
    engine.step_analyze()
    engine.step_market()
    engine.step_score()
    push_auction_results(engine)
elif args.phase == "morning":
    engine.step_cascade()
    engine.step_screen()
    engine.step_analyze()
    engine.step_market()
    engine.step_score()
    engine.step_position()
    engine.step_risk()
    engine.step_simulate()
    from notify.pusher import push_morning_report, push_trade_plan
    push_morning_report(engine)
    push_trade_plan(engine)

elif args.phase == "monitor":
    engine.step_cascade()
    engine.step_screen()
    engine.step_analyze()
    engine.step_market()
    engine.step_score()
    engine.step_position()
    engine.step_risk()
    engine.step_simulate()
    engine.step_monitor()
    engine.step_rebalance()
    push_trade_signal(engine)
elif args.phase == "multi_morning":
    from multi_agent.coordinator import MultiAgentCoordinator
    coord = MultiAgentCoordinator()
    results = coord.run_all_morning()
    coord.push_aggregate_report()
    logging.getLogger("aurora").info(f"[6Agent] 晨扫完成, 6账户总资产: {sum(r.get('total_value',0) for r in results.values()):.0f}")
    try:
        from scripts.agent_comparison import snapshot_all
        snapshot_all()
    except: pass
elif args.phase == "multi_monitor":
    from multi_agent.coordinator import MultiAgentCoordinator
    coord = MultiAgentCoordinator()
    results = coord.run_all_intraday()
    logging.getLogger("aurora").info(f"[6Agent] 盘中完成, 6账户总资产: {sum(r.get('total_value',0) for r in results.values()):.0f}")
    try:
        from scripts.agent_comparison import snapshot_all
        snapshot_all()
    except: pass
elif args.phase == "close":
    logging.getLogger("aurora").info("[Close] 日终批量处理开始")
    engine = AuroraEngine('config.yaml')
    engine.step_close()
    logging.getLogger("aurora").info("[Close] 日终批量处理完成")
elif args.phase == "review":
    engine.run()
    push_daily_review(engine)
    from notify.review_report import generate_report, push_report
    report = generate_report(engine)
    logging.getLogger("aurora").info(f"`n{report}")
    push_report(engine)
    # PnL追踪
    try:
        from scripts.pnl_tracker import record
        record()
    except Exception as e:
        logging.getLogger("aurora").debug(f"[PnL] {e}")
else:
    engine.run()