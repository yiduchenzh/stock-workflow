"""Aurora崩溃恢复引擎 — 自动检测异常退出并恢复运行状态
纯JSON操作，不依赖pandas/engine导入，可在任意环境运行"""
import json, logging, sys
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger("aurora.recovery")

BASE = Path(__file__).resolve().parent.parent
import os as _ra
_rag = _ra.environ.get("AURORA_AGENT")
if _rag:
    RECOVERY_STATE = BASE / "data" / f"recovery_state_{_rag}.json"
else:
    RECOVERY_STATE = BASE / "data" / "recovery_state.json"
del _ra, _rag

RECOVERY_STATE_ORIG = RECOVERY_STATE
LIVE_STATE = BASE / "data" / "live_state.json"


def _read_state() -> dict:
    """安全读取恢复状态"""
    if not RECOVERY_STATE.exists():
        return {}
    try:
        return json.loads(RECOVERY_STATE.read_text(encoding="utf-8"))
    except:
        return {}


def _write_state(state: dict):
    """安全写入恢复状态"""
    RECOVERY_STATE.parent.mkdir(parents=True, exist_ok=True)
    RECOVERY_STATE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def save_recovery_point(regime: str = None, score: float = None,
                        positions_count: int = 0, step: str = None):
    """保存恢复点（engine外调用，无需导入engine）"""
    now = datetime.now().isoformat()
    state = _read_state()
    state["last_heartbeat"] = now
    state["last_completed_step"] = step or state.get("last_completed_step", "unknown")
    if regime:
        state["last_regime"] = regime
    if score is not None:
        state["last_score"] = score
    state["positions_count"] = positions_count
    state.setdefault("crash_count", 0)
    state.setdefault("recovery_count", 0)
    _write_state(state)
    logger.info(f"[Recovery] 保存点: step={step} regime={regime}")


def mark_crash():
    """标记一次崩溃事件"""
    state = _read_state()
    state["crash_count"] = state.get("crash_count", 0) + 1
    _write_state(state)
    logger.warning(f"[Recovery] 崩溃计数: {state['crash_count']}")


def need_recovery() -> bool:
    """检测是否需要恢复（独立检测，不依赖engine）"""
    state = _read_state()
    if not state:
        return False
    last_hb = state.get("last_heartbeat")
    if not last_hb:
        return False
    try:
        hb_time = datetime.fromisoformat(last_hb)
        return (datetime.now() - hb_time) > timedelta(minutes=10)
    except:
        return False


def recover_engine(engine) -> bool:
    """将恢复状态写入engine对象"""
    state = _read_state()
    if not state:
        return False

    recovered = False
    if state.get("last_regime"):
        engine.market_regime = state["last_regime"]
        recovered = True
    if state.get("last_score") is not None:
        engine.market_score = state["last_score"]
        recovered = True

    # 更新恢复计数
    state["recovery_count"] = state.get("recovery_count", 0) + 1
    state["last_heartbeat"] = datetime.now().isoformat()
    _write_state(state)

    logger.info(f"[Recovery] 引擎恢复: regime={state.get('last_regime')} "
                f"score={state.get('last_score')} "
                f"累计恢复={state['recovery_count']}次")
    return recovered


def status() -> dict:
    """查看恢复状态"""
    return _read_state()


def main():
    """命令行入口"""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    action = sys.argv[1] if len(sys.argv) > 1 else "status"

    if action == "status":
        s = status()
        if s:
            print(json.dumps(s, indent=2, ensure_ascii=False))
        else:
            print("{}  (无恢复记录)")
        print(f"need_recovery: {need_recovery()}")

    elif action == "check":
        print(json.dumps({"need_recovery": need_recovery()}))

    elif action == "mark":
        step = sys.argv[2] if len(sys.argv) > 2 else "manual"
        save_recovery_point(step=step)
        print(f"已标记恢复点: step={step}")

    else:
        print(f"用法: python core/recovery.py [status|check|mark [step]]")


if __name__ == "__main__":
    main()
