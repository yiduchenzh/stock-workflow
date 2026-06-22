"""Aurora Trading — 每日自动运行 · 分阶段推送"""
import sys, logging, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("data/aurora.log", encoding="utf-8"), logging.StreamHandler()])

parser = argparse.ArgumentParser()
parser.add_argument("--phase", default="full", choices=["auction","monitor","review","full"],
                   help="auction=竞价选股, monitor=盘中监控+T0, review=盘后复盘, full=全流程")
args = parser.parse_args()

from core.engine import AuroraEngine
from notify.pusher import push_auction_results, push_trade_signal, push_daily_review

engine = AuroraEngine()

if args.phase == "auction":
    engine.step_market()
    engine.step_cascade()
    engine.step_screen()
    engine.step_analyze()
    engine.step_score()
    push_auction_results(engine)
elif args.phase == "monitor":
    engine.step_market()
    engine.step_cascade()
    engine.step_screen()
    engine.step_analyze()
    engine.step_score()
    engine.step_position()
    engine.step_risk()
    engine.step_simulate()
    engine.step_t0()
    engine.step_monitor()
    push_trade_signal(engine)
elif args.phase == "review":
    engine.run()
    push_daily_review(engine)
else:
    engine.run()