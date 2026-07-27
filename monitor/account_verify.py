"""实盘监控 — 持仓核对+资金对账+熔断恢复"""
import json, logging
from pathlib import Path
from datetime import datetime

DATA = Path(__file__).resolve().parent.parent / "data"
RECONCILIATION_FILE = DATA / "reconciliation_log.json"

logger = logging.getLogger("aurora.verify")

class AccountVerifier:
    """账户核对器 — 确保引擎状态与真实券商一致"""
    
    def __init__(self):
        self.max_position_discrepancy = 0.05  # 持仓差异>5%告警
        self.max_cash_discrepancy = 1000      # 现金差异>1000元告警
    
    def reconcile(self, engine_positions: dict, broker_positions: dict) -> list:
        """
        比对引擎持仓 vs 券商持仓
        返回差异告警列表
        """
        alerts = []
        engine_codes = set(engine_positions.keys())
        broker_codes = set(broker_positions.keys())
        
        # 引擎有但券商没有
        missing = engine_codes - broker_codes
        for code in missing:
            alerts.append({
                "type": "position_mismatch",
                "code": code,
                "engine_only": True,
                "shares": engine_positions[code].get("shares", 0),
                "msg": f"[对账] 引擎有{code}但券商无"
            })
        
        # 券商有但引擎没有
        extra = broker_codes - engine_codes
        for code in extra:
            alerts.append({
                "type": "position_mismatch",
                "code": code,
                "broker_only": True,
                "shares": broker_positions[code].get("shares", 0),
                "msg": f"[对账] 券商有{code}但引擎无"
            })
        
        # 共有持仓核对股数
        common = engine_codes & broker_codes
        for code in common:
            e_shares = engine_positions[code].get("shares", 0)
            b_shares = broker_positions[code].get("shares", 0)
            if e_shares != b_shares:
                diff_ratio = abs(e_shares - b_shares) / max(e_shares, b_shares, 1)
                if diff_ratio > self.max_position_discrepancy:
                    alerts.append({
                        "type": "shares_mismatch",
                        "code": code,
                        "engine_shares": e_shares,
                        "broker_shares": b_shares,
                        "msg": f"[对账] {code} 股数不一致: 引擎{e_shares} vs 券商{b_shares}"
                    })
        
        # 记录对账日志
        self._log_reconciliation(alerts)
        return alerts
    
    def _log_reconciliation(self, alerts):
        """记录对账日志"""
        log = {
            "time": datetime.now().isoformat(),
            "alert_count": len(alerts),
            "alerts": alerts[:10],
        }
        RECONCILIATION_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            history = json.loads(RECONCILIATION_FILE.read_text()) if RECONCILIATION_FILE.exists() else []
        except:
            history = []
        history.append(log)
        RECONCILIATION_FILE.write_text(json.dumps(history[-100:], indent=2))
    
    def check_capital_safety(self, total_value: float, initial_capital: float) -> list:
        """资金安全检查"""
        alerts = []
        drawdown = (total_value - initial_capital) / initial_capital
        
        if drawdown < -0.20:
            alerts.append({
                "type": "capital_safety",
                "severity": "critical",
                "drawdown": round(drawdown * 100, 1),
                "msg": f"[资金安全] 总回撤{drawdown*100:.1f}%超过20%, 建议停止交易"
            })
        elif drawdown < -0.10:
            alerts.append({
                "type": "capital_safety",
                "severity": "warning",
                "drawdown": round(drawdown * 100, 1),
                "msg": f"[资金安全] 总回撤{drawdown*100:.1f}%超过10%, 关注"
            })
        
        return alerts
    
    def check_daily_pnl(self, daily_pnl: float, capital: float) -> list:
        """日盈亏检查"""
        alerts = []
        pnl_pct = daily_pnl / capital * 100
        
        if pnl_pct < -5:
            alerts.append({
                "type": "daily_pnl",
                "severity": "critical",
                "pnl_pct": round(pnl_pct, 1),
                "msg": f"[日盈亏] 今日亏损{pnl_pct:.1f}%超过5%, 建议暂停"
            })
        elif pnl_pct < -3:
            alerts.append({
                "type": "daily_pnl",
                "severity": "warning",
                "pnl_pct": round(pnl_pct, 1),
                "msg": f"[日盈亏] 今日亏损{pnl_pct:.1f}%超过3%, 注意"
            })
        
        return alerts
    
    def emergency_shutdown(self, engine, reason: str):
        """紧急停机关闭所有持仓"""
        logger.warning(f"[紧急停机] {reason}")
        # 记录停机原因
        shutdown_log = DATA / "emergency_shutdown.json"
        shutdown_log.write_text(json.dumps({
            "time": datetime.now().isoformat(),
            "reason": reason,
            "positions": list(getattr(engine, 'positions', {}).keys()),
        }, indent=2))
        # 触发熔断
        from risk.controls import _load, _save
        state = _load()
        state["breaker"] = True
        state["breaker_time"] = __import__('time').time()
        state["emergency_reason"] = reason
        _save(state)

def verify_all(engine, broker_positions=None, broker_capital=None):
    """全量核验(外部调用接口)"""
    verifier = AccountVerifier()
    all_alerts = []
    
    # 1. 持仓核对
    if broker_positions:
        pos_alerts = verifier.reconcile(engine.positions, broker_positions)
        all_alerts.extend(pos_alerts)
    
    # 2. 资金检查
    account = getattr(engine, 'account', None)
    if account and hasattr(account, 'total_value'):
        cap_alerts = verifier.check_capital_safety(account.total_value, engine.capital)
        all_alerts.extend(cap_alerts)
    
    # 3. 熔断状态检查
    from risk.controls import _load
    state = _load()
    if state.get("breaker"):
        all_alerts.append({
            "type": "breaker_active",
            "msg": "熔断已触发, 需手动恢复或等待24h自动解除"
        })
    
    return all_alerts
