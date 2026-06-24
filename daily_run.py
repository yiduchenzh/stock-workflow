"""Aurora Trading — 每日自动运行 · 分阶段推送"""
import sys, logging, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("data/aurora.log", encoding="utf-8"), logging.StreamHandler()])

parser = argparse.ArgumentParser()
parser.add_argument("--phase", default="full", choices=["auction","monitor","review","morning","full"],
                   help="auction=竞价选股, monitor=盘中监控+T0, review=盘后复盘, morning=晨报, full=全流程")
args = parser.parse_args()

from core.engine import AuroraEngine
from notify.pusher import push_auction_results, push_trade_signal, push_daily_review

engine = AuroraEngine('config.yaml')

if args.phase == "auction":
    engine.step_market()
    engine.step_cascade()
    engine.step_screen()
    engine.step_analyze()
    engine.step_score()
    push_auction_results(engine)
elif args.phase == "morning":
    engine.step_market()
    engine.step_cascade()
    engine.step_screen()
    from notify.pusher import push_morning_report
    push_morning_report(engine)

elif args.phase == "monitor":
    engine.step_market()
    engine.step_cascade()
    engine.step_screen()
    engine.step_analyze()
    engine.step_score()
    engine.step_position()
    engine.step_risk()
    engine.step_simulate()
    engine.step_monitor()
    engine.step_rebalance()
    push_trade_signal(engine)
elif args.phase == "review":
    engine.run()
    push_daily_review(engine)
    from notify.review_report import generate_report, push_report
    report = generate_report(engine)
    logger.info(f"\n{report}")
    push_report(engine)
else:
    engine.run()