"""引擎实时包装器 — run_forever() SSE推送模式"""
from __future__ import annotations
import asyncio
import json
import logging
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

PROJ = Path(__file__).resolve().parent.parent
logger = logging.getLogger("aurora.live")

class EngineLiveWrapper:
    MODE_POLL = "poll"
    MODE_BATCH = "batch"
    MODE_HYBRID = "hybrid"

    def __init__(self, config_path: str = None, mode: str = "poll"):
        self.config_path = config_path or str(PROJ / "config.yaml")
        self.mode = mode
        self._engine = None
        self._running = False
        self._on_signal: Optional[Callable] = None
        self._on_trade: Optional[Callable] = None
        self._on_market: Optional[Callable] = None
        self._last_polled: dict = {}
        self._watchlist: list = []

    @property
    def engine(self):
        if self._engine is None:
            from core.engine import AuroraEngine
            self._engine = AuroraEngine(self.config_path)
        return self._engine

    async def run_forever(self):
        self._running = True
        logger.info(f"🔴 Aurora实时流启动 | 模式={self.mode}")
        if self.mode in (self.MODE_BATCH, self.MODE_HYBRID):
            try:
                logger.info("执行每日批处理...")
                self.engine.run()
                logger.info("批处理完成")
                if self._on_market:
                    await self._on_market({
                        "market_score": getattr(self.engine,"market_score",50),
                        "market_regime": getattr(self.engine,"market_regime","range"),
                        "plans": getattr(self.engine,"plans",[]),
                        "alerts": getattr(self.engine,"alerts",[]),
                    })
            except Exception as e:
                logger.error(f"批处理失败: {e}")
        logger.info("开始轮询行情...")
        poll_interval = 5
        market_poll_interval = 15
        last_market_poll = 0
        while self._running:
            try:
                now = time.time()
                if now - last_market_poll >= market_poll_interval:
                    if self._on_market:
                        market_data = await self._poll_market_data()
                        if market_data:
                            await self._on_market(market_data)
                    last_market_poll = now
                if self._on_signal:
                    signals = await self._poll_signals()
                    for sig in signals:
                        await self._on_signal(sig)
                await asyncio.sleep(poll_interval)
            except asyncio.CancelledError:
                logger.info("实时流被取消")
                break
            except Exception:
                logger.error(f"轮询异常: {traceback.format_exc()}")
                await asyncio.sleep(10)
        self._running = False
        logger.info("Aurora实时流停止")

    async def _poll_market_data(self) -> Optional[dict]:
        try:
            from data.sources import get_index_snapshot, get_market_breadth, get_sector_ranking
            indices = get_index_snapshot(["000001","399001","399006"])
            breadth = get_market_breadth()
            sectors = get_sector_ranking(10) or []
            return {"type":"market_update","indices":indices or {},"breadth":breadth or {},"sectors":sectors,"timestamp":datetime.now().isoformat()}
        except Exception:
            return None

    async def _poll_signals(self) -> list:
        return []

    def stop(self): self._running = False
    def set_watchlist(self, codes: list): self._watchlist = codes
    def register_signal_callback(self, cb: Callable): self._on_signal = cb
    def register_trade_callback(self, cb: Callable): self._on_trade = cb
    def register_market_callback(self, cb: Callable): self._on_market = cb

def run_batch_and_export() -> dict:
    from core.engine import AuroraEngine
    logger.info("🔄 执行引擎批处理...")
    engine = AuroraEngine()
    engine.run()
    web_dir = PROJ / "backend" / "data"
    web_dir.mkdir(parents=True, exist_ok=True)
    plans_data = [{
        "code": p.get("code",""), "name": p.get("name",""),
        "strategy": p.get("strategy",""), "entry_price": p.get("entry_price",0),
        "shares": p.get("shares",0), "score": p.get("score",0),
        "stop_loss": p.get("stop_loss",0), "take_profit": p.get("take_profit",0),
        "reason": p.get("signal_detail",""),
    } for p in (engine.plans or [])]
    export = {
        "updated_at": datetime.now().isoformat(),
        "market_score": getattr(engine,"market_score",50),
        "market_regime": getattr(engine,"market_regime","range"),
        "plans": plans_data,
        "alerts": [{"type":a.get("type"),"code":a.get("code"),"reason":a.get("reason")} for a in (engine.alerts or [])],
    }
    (web_dir / "engine_state.json").write_text(json.dumps(export, ensure_ascii=False, default=str))
    logger.info(f"✅ 批处理完成 | 市场评分={export['market_score']} | 计划={len(plans_data)}条")
    return export