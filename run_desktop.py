"""Aurora Desktop Entry Point"""
import sys, os, logging, threading, time

PROJ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJ)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
logger = logging.getLogger("aurora.desktop")

os.environ["AURORA_MODE"] = "desktop"
os.environ["WZ_TOKEN"] = "ed988da5e5656095965e158ffa29f625"

def _engine_loop():
    from core.engine import AuroraEngine
    from core.recovery import save_recovery_point
    from core.calendar import is_trading_day
    import json
    from datetime import datetime
    from pathlib import Path
    engine = AuroraEngine()
    ep = Path(PROJ) / "backend" / "data" / "engine_state.json"
    logger.info("[Engine] 引擎线程启动")
    while True:
        try:
            # 非交易日跳过
            if not is_trading_day():
                time.sleep(600)
                continue
            # 非交易时段跳过
            _n = datetime.now()
            _m = _n.hour * 60 + _n.minute
            if _m < 570 or _m > 930:
                time.sleep(300)
                continue
            engine.step_market()
            mr = getattr(engine, "market_regime", "range")
            # [Soul] 快速持仓监控(30秒/次): 急跌感知
            try:
                from executor.sim_account import SimAccount as _SA; from data.sources import get_tencent_quotes as _GT
                for _code, _pos in _SA(engine.capital, engine.cfg).positions.items():
                    _cur = _GT([_code]).get(_code, {}).get('price', 0)
                    if _cur > 0 and _pos.get('avg_cost', 0) > 0:
                        _chg = (_cur - _pos['avg_cost']) / _pos['avg_cost'] * 100
                        if _chg < -5: engine.log.warning(f'[Soul] 急跌! {_code} 浮亏{_chg:.1f}%')
            except Exception:
                pass
            ms = getattr(engine, "market_score", 50)
            state = {
                "updated_at": datetime.now().isoformat(),
                "market_score": ms,
                "market_regime": str(mr),
                "indices": {},
                "sectors": [],
                "plans": getattr(engine, "plans", []),
                "alerts": getattr(engine, "alerts", []),
                "signals": getattr(engine, "analysis", [])[:10],
            }
            ep.parent.mkdir(parents=True, exist_ok=True)
            ep.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            # 从sim_state.json读取实际持仓数
            try:
                import json
                _sp = Path(PROJ) / "data" / "sim_state.json"
                _pc = len(json.loads(_sp.read_text()).get("positions", {})) if _sp.exists() else 0
            except Exception:
                _pc = 0
            save_recovery_point(mr, ms, _pc, "desktop_scan")
            logger.info(f"[Engine] OK: {mr} score={ms:.0f}")
        except Exception as e:
            logger.warning(f"[Engine] {e}")
        time.sleep(300)

threading.Thread(target=_engine_loop, daemon=True).start()
logger.info("[Desktop] 引擎线程已启动")

from backend.main import app
import uvicorn

if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("Aurora AI 量化投资工作站")
    logger.info("API: http://127.0.0.1:7878")
    logger.info("=" * 50)
    uvicorn.run(app, host="127.0.0.1", port=7878, log_level="info")
