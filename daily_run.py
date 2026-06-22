"""每日自动运行入口"""
import sys, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("data/aurora.log", encoding="utf-8"), logging.StreamHandler()])
from core.engine import AuroraEngine
if __name__ == "__main__":
    engine = AuroraEngine()
    engine.run()
