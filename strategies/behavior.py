"""行为偏误诊断 — 处置效应/过度交易/追涨杀跌"""
import json, logging
from pathlib import Path
from datetime import datetime
logger = logging.getLogger("aurora.behavior")
JOURNAL = Path(__file__).resolve().parent.parent / "data" / "behavior_journal.json"

def record_entry(plan: dict):
    j = _load_journal()
    j.append({"time": datetime.now().isoformat(), "action": "entry",
              "code": plan.get("code",""), "strategy": plan.get("strategy",""),
              "score": plan.get("score", 0), "confidence": plan.get("confidence", 0),
              "planned": True})
    _save_journal(j)

def record_exit(code: str, pnl_pct: float, reason: str, planned: bool = True):
    j = _load_journal()
    j.append({"time": datetime.now().isoformat(), "action": "exit",
              "code": code, "pnl_pct": round(pnl_pct, 2), "reason": reason, "planned": planned})
    _save_journal(j)

def diagnose() -> dict:
    j = _load_journal()
    entries = [e for e in j if e.get("action") == "entry"]
    exits = [e for e in j if e.get("action") == "exit"]
    if not exits: return {"status": "insufficient_data", "message": "不足5笔出场"}
    wins = [e for e in exits if e.get("pnl_pct", 0) > 0]
    unplanned = sum(1 for e in exits if not e.get("planned", True))
    unplanned_ratio = unplanned / max(len(exits), 1)
    chasing = sum(1 for e in entries if e.get("confidence", 0) < 0.3)
    issues = []
    if unplanned_ratio > 0.3: issues.append(f"未按计划出场{unplanned_ratio:.0%}")
    if len(wins)/max(len(exits),1) > 0.7 and len(exits) >= 5: issues.append("盈利过早止盈")
    if chasing > len(entries)*0.3 and entries: issues.append(f"低置信度入场{chasing}次")
    return {"status": "healthy" if not issues else "warning",
            "total_exits": len(exits), "win_rate": round(len(wins)/max(len(exits),1),2),
            "unplanned_exit_ratio": round(unplanned_ratio, 2), "issues": issues,
            "advice": "暂无明显偏误" if not issues else "; ".join(issues)}

def _load_journal():
    try: return json.loads(JOURNAL.read_text()) if JOURNAL.exists() else []
    except: return []
def _save_journal(j):
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    JOURNAL.write_text(json.dumps(j[-200:], indent=2, ensure_ascii=False))