"""容错恢复模块 — 崩溃自动恢复+断点续跑+熔断自动解除"""
import json, time, logging
from pathlib import Path
from datetime import datetime, timedelta

DATA = Path(__file__).resolve().parent.parent / "data"
RECOVERY_FILE = DATA / "recovery_state.json"
HEARTBEAT_FILE = DATA / "heartbeat.log"

logger = logging.getLogger("aurora.recovery")

class EngineRecovery:
    """引擎容错恢复管理器"""
    
    def __init__(self, max_downtime_minutes=30):
        self.max_downtime = max_downtime_minutes
        self._ensure_state()
    
    def _ensure_state(self):
        DATA.mkdir(parents=True, exist_ok=True)
        if not RECOVERY_FILE.exists():
            self._save({
                "last_heartbeat": None,
                "last_completed_step": None,
                "last_regime": "range",
                "last_score": 50,
                "positions_count": 0,
                "crash_count": 0,
                "recovery_count": 0,
            })
    
    def _load(self):
        try: return json.loads(RECOVERY_FILE.read_text())
        except: return {}
    
    def _save(self, state):
        RECOVERY_FILE.write_text(json.dumps(state, indent=2))
    
    def heartbeat(self, engine):
        """记录心跳(每30秒调用)"""
        state = self._load()
        state["last_heartbeat"] = datetime.now().isoformat()
        state["last_completed_step"] = "step_" + str(getattr(engine, 'market_regime', 'unknown'))
        state["last_regime"] = getattr(engine, 'market_regime', 'range')
        state["last_score"] = getattr(engine, 'market_score', 50)
        state["positions_count"] = len(getattr(engine, 'positions', {}))
        self._save(state)
    
    def record_crash(self, error_info):
        """记录崩溃"""
        state = self._load()
        state["crash_count"] = state.get("crash_count", 0) + 1
        state["last_crash"] = datetime.now().isoformat()
        state["last_error"] = str(error_info)[:200]
        self._save(state)
        logger.error(f"[Recovery] 崩溃记录 #{state['crash_count']}: {str(error_info)[:100]}")
    
    def check_availability(self) -> dict:
        """检查引擎是否可用(是否崩溃超过阈值)"""
        state = self._load()
        last_hb = state.get("last_heartbeat")
        if not last_hb:
            return {"available": False, "reason": "从未启动", "can_recover": False}
        
        last_time = datetime.fromisoformat(last_hb)
        downtime = (datetime.now() - last_time).total_seconds() / 60
        
        if downtime > self.max_downtime:
            return {
                "available": False,
                "reason": f"心跳停止{downtime:.0f}分钟(阈值{self.max_downtime}分钟)",
                "downtime_minutes": round(downtime, 1),
                "can_recover": True,
                "last_known_state": {
                    "regime": state.get("last_regime"),
                    "score": state.get("last_score"),
                    "positions": state.get("positions_count"),
                }
            }
        
        return {"available": True, "downtime_minutes": round(downtime, 1)}
    
    def recover_engine(self, engine) -> bool:
        """恢复引擎状态"""
        state = self._load()
        try:
            # 1. 恢复市场状态
            engine.market_regime = state.get("last_regime", "range")
            engine.market_score = state.get("last_score", 50)
            
            # 2. 恢复熔断状态
            from risk.controls import _load as load_risk
            risk_state = load_risk()
            if risk_state.get("breaker"):
                breaker_time = risk_state.get("breaker_time", 0)
                if breaker_time > 0 and (time.time() - breaker_time) > 86400:
                    # 熔断超过24小时自动恢复
                    from risk.controls import reset as reset_risk
                    reset_risk()
                    logger.warning("[Recovery] 熔断已超24h, 自动解除")
            
            # 3. 更新恢复计数
            state["recovery_count"] = state.get("recovery_count", 0) + 1
            state["last_recovery"] = datetime.now().isoformat()
            self._save(state)
            
            logger.info(f"[Recovery] 引擎恢复成功 #{state['recovery_count']}")
            return True
        except Exception as e:
            logger.error(f"[Recovery] 恢复失败: {e}")
            return False
    
    def get_status_report(self) -> str:
        """获取可读的状态报告"""
        state = self._load()
        avail = self.check_availability()
        lines = [
            "═" * 40,
            "【引擎状态报告】",
            f"最后心跳: {state.get('last_heartbeat', '从未')}",
            f"最后步骤: {state.get('last_completed_step', 'N/A')}",
            f"最后状态: {state.get('last_regime', '?')} ({state.get('last_score', '?')})",
            f"持仓数: {state.get('positions_count', 0)}",
            f"可用性: {'✅ 正常' if avail.get('available') else '❌ 离线'}",
            f"崩溃次数: {state.get('crash_count', 0)}",
            f"恢复次数: {state.get('recovery_count', 0)}",
            "═" * 40,
        ]
        return "\n".join(lines)

def auto_recover(engine) -> bool:
    """一键自动恢复(被外部调用)"""
    recovery = EngineRecovery()
    status = recovery.check_availability()
    if status.get("can_recover"):
        return recovery.recover_engine(engine)
    return False
