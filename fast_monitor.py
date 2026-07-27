"""快速监控 — 每5分钟执行, 仅检查持仓状态, 不跑全市场扫描"""
import sys, logging, os
from pathlib import Path
from datetime import datetime

root = Path(__file__).parent
sys.path.insert(0, str(root))

# 仅在交易时段运行 (交易日 + 09:30-15:00)
now = datetime.now()
t = now.hour * 60 + now.minute
if t < 570 or t > 930:  # 09:30=570, 15:00=900
    sys.exit(0)  # 非交易时段直接退出
# 非交易日不执行
try:
    from core.calendar import is_trading_day
    if not is_trading_day():
        sys.exit(0)
except:
    if now.weekday() >= 5:
        sys.exit(0)

os.makedirs(str(root / "data"), exist_ok=True)
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(root / "data" / "fast_monitor.log"), encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("fast_monitor")

try:
    from core.engine import AuroraEngine
    engine = AuroraEngine(str(root / "config.yaml"))
    engine.phase = "monitor"
    logger.info(f"[FastMonitor] 启动 持仓={len(engine.positions)}只")

    # step_market: 轻量市场刷新
    engine.step_market()
    logger.info(f"[FastMonitor] 市场评分={engine.market_score} regime={engine.market_regime}")

    # step_monitor: 持仓止损止盈+T+0
    if engine.positions:
        engine.step_monitor()
        # step_rebalance: 仓位再平衡
        engine.step_rebalance()
        logger.info(f"[FastMonitor] 监控完成 持仓={len(engine.positions)}只")
    else:
        logger.info("[FastMonitor] 无持仓,跳过监控")

except Exception as e:
    logger.error(f"[FastMonitor] 异常: {e}")
