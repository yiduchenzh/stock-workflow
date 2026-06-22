"""Aurora Trading v2.0 — 每日自动运行 · 9书框架全映射"""
import sys, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("data/aurora.log", encoding="utf-8"), logging.StreamHandler()])
from core.engine import AuroraEngine
if __name__ == "__main__":
    AuroraEngine().run()
