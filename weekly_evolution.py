"""周度自进化 — 策略评估 + 参数调整 + 自动淘汰"""
import json, logging, os
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("aurora.evolution")
DATA = Path(__file__).resolve().parent / "data"
STATE_FILE = DATA / "evolution_state.json"
TRADES_FILE = DATA / "sim_trades.json"

def get_state() -> dict:
    if STATE_FILE.exists():
        try: return json.loads(STATE_FILE.read_text())
        except: pass
    return {"strategies": {}, "blacklist": [], "adjustments": {}}

def save_state(state):
    DATA.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))

def get_evolved_params(strategy_name: str) -> dict:
    state = get_state()
    adj = state.get("adjustments", {}).get(strategy_name, {})
    score_delta = adj.get("score_delta", 0)
    suspended = strategy_name in state.get("blacklist", [])
    return {"score_delta": score_delta, "suspended": suspended}

def clear_suspensions():
    state = get_state()
    now = datetime.now()
    active = []
    for item in state.get("blacklist", []):
        if isinstance(item, dict):
            until = datetime.strptime(item.get("until", "2000-01-01"), "%Y-%m-%d")
            if until > now: active.append(item)
    state["blacklist"] = active
    save_state(state)

def run_weekly_evolution() -> str:
    if not TRADES_FILE.exists():
        msg = "无交易记录, 跳过进化"
        logger.info(msg)
        return msg
    trades = json.loads(TRADES_FILE.read_text())
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    weekly = [t for t in trades if t.get("time", "") >= week_ago]
    if not weekly:
        msg = f"本周({len(weekly)}笔交易)样本不足, 跳过进化"
        logger.info(msg)
        return msg
    
    # Group by strategy
    strat_trades = {}
    for t in weekly:
        strat = t.get("reason", "unknown")
        if strat not in strat_trades: strat_trades[strat] = []
        strat_trades[strat].append(t)
    
    state = get_state()
    log_lines = []
    for name, st in strat_trades.items():
        total = len(st)
        wins = sum(1 for t in st if t.get("pnl", 0) > 0)
        wr = wins / total if total > 0 else 0
        total_pnl = sum(t.get("pnl", 0) for t in st)
        pf = total_pnl / abs(sum(t.get("pnl", 0) for t in st if t.get("pnl", 0) < 0)) if any(t.get("pnl", 0) < 0 for t in st) else 99
        
        adj = state.setdefault("adjustments", {}).setdefault(name, {"score_delta": 0})
        old_delta = adj.get("score_delta", 0)
        
        if total >= 5:
            if wr < 0.30:
                state.setdefault("blacklist", []).append({"name": name, "until": (datetime.now()+timedelta(days=7)).strftime("%Y-%m-%d")})
                log_lines.append(f"{name}: WR={wr:.0%}<30%, 暂停7天")
            elif pf < 0.8:
                adj["score_delta"] = max(-20, old_delta - 5)
                log_lines.append(f"{name}: PF={pf:.1f}<0.8, 收紧阈值({old_delta}->{adj['score_delta']})")
            elif wr > 0.65:
                adj["score_delta"] = min(20, old_delta + 3)
                log_lines.append(f"{name}: WR={wr:.0%}>65%, 放宽阈值({old_delta}->{adj['score_delta']})")
    
    save_state(state)
    report = "\n".join(log_lines) if log_lines else "本周无策略调整"
    logger.info(f"[进化] {report}")
    
    # Push
    token = os.environ.get("SCT_TOKEN", "")
    if token and len(token) >= 10:
        try:
            import requests
            requests.post(f"https://sctapi.ftqq.com/{token}.send",
                json={"title": f"Aurora进化 {datetime.now():%m-%d}", "desp": report}, timeout=10)
        except: pass
    
    return report
