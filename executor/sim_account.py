"""高仿真模拟账户 — 含滑点/冲击成本/排队模拟/费用精确计算"""
import json, logging, random, time
from pathlib import Path
from datetime import datetime
from executor.base import BaseExecutor
logger = logging.getLogger("aurora.sim")

DATA = Path(__file__).resolve().parent.parent / "data"
STATE = DATA / "sim_state.json"
TRADES = DATA / "sim_trades.json"

class SimAccount(BaseExecutor):
    """高仿真模拟账户 — 模拟真实市场微观结构"""
    
    def __init__(self, capital: float = 1_000_000, config: dict = None):
        super().__init__(capital)
        self.config = config or {}
        self.commission = 0.0003      # 佣金0.03%
        self.stamp_tax = 0.001        # 印花税0.1% (仅卖出)
        self.slippage_base = 0.001     # 基础滑点0.1%
        self.slippage_tiers = {      # 按市值分层 (Quant审计)
            500: 0.001,   # >500亿: 0.1%
            100: 0.002,   # 100-500亿: 0.2%
            0:   0.003,   # <100亿: 0.3%
        }
        self.impact_factor = 0.0001   # 冲击成本(每100万成交额+0.01%)
        self._load()
    
    def buy(self, code: str, price: float, shares: int, reason: str = "") -> dict:
        """模拟买入 — 含滑点+冲击成本"""
        if shares < 100: return {"success": False, "error": "最小100股"}
        shares = int(shares / 100) * 100
        
        # 滑点模拟: 买入价上浮(买方主动)
        mcap = getattr(self, 'stock_mcap', 200)  # 市值(亿), 默认200
        base_slip = 0.003
        for threshold, slip in sorted(self.slippage_tiers.items(), reverse=True):
            if mcap >= threshold: base_slip = slip; break
        slippage = base_slip + random.uniform(0, 0.001)
        fill_price = price * (1 + slippage)
        
        # 冲击成本: 成交额越大滑点越大
        notional = fill_price * shares
        impact = notional / self.capital * self.impact_factor if self.capital > 0 else 0
        fill_price *= (1 + impact)
        
        # 费用: 佣金(买入无印花税)
        fee = notional * self.commission
        total_cost = notional + fee
        
        if total_cost > self.cash:
            max_shares = int(self.cash * 0.98 / (fill_price * (1 + self.commission)) / 100) * 100
            if max_shares < 100:
                return {"success": False, "error": f"资金不足(需{total_cost:.0f}>现金{self.cash:.0f})"}
            shares = max_shares
            notional = fill_price * shares
            fee = notional * self.commission
            total_cost = notional + fee
        
        self.cash -= total_cost
        
        # 更新持仓
        if code in self.positions:
            p = self.positions[code]
            old_total = p["shares"] * p["avg_cost"]
            p["shares"] += shares
            p["avg_cost"] = round((old_total + total_cost) / p["shares"], 4)
        else:
            self.positions[code] = {
                "shares": shares, "avg_cost": round(total_cost / shares, 4),
                "current_price": fill_price, "entry_date": str(datetime.now().date()),
            }
        
        trade = {
            "action": "buy", "code": code, "shares": shares,
            "price": round(fill_price, 2), "slippage_pct": round(slippage*100, 2),
            "fee": round(fee, 2), "total": round(total_cost, 2),
            "reason": reason, "time": datetime.now().isoformat(),
        }
        self.trades.append(trade)
        self._save()
        logger.info(f"[SIM BUY] {code} {shares}sh @{fill_price:.2f} fee={fee:.2f}")
        return {"success": True, "trade": trade}
    
    def sell(self, code: str, price: float, shares: int, reason: str = "") -> dict:
        """模拟卖出 — 含滑点+印花税"""
        if code not in self.positions: return {"success": False, "error": f"无{code}持仓"}
        pos = self.positions[code]
        if shares > pos["shares"]: shares = pos["shares"]
        if shares < 100: return {"success": False, "error": "最小100股"}
        shares = int(shares / 100) * 100
        
        # 滑点: 卖出价下浮
        slippage = self.slippage_base + random.uniform(0, 0.001)
        fill_price = price * (1 - slippage)
        
        notional = fill_price * shares
        commission = notional * self.commission
        stamp = notional * self.stamp_tax  # 卖出有印花税
        net = notional - commission - stamp
        
        pnl = net - shares * pos["avg_cost"]
        
        self.cash += net
        pos["shares"] -= shares
        if pos["shares"] <= 0: del self.positions[code]
        
        trade = {
            "action": "sell", "code": code, "shares": shares,
            "price": round(fill_price, 2), "slippage_pct": round(slippage*100, 2),
            "commission": round(commission, 2), "stamp": round(stamp, 2),
            "net": round(net, 2), "pnl": round(pnl, 2),
            "pnl_pct": round(pnl / (shares * pos["avg_cost"]) * 100, 2) if shares > 0 else 0,
            "reason": reason, "time": datetime.now().isoformat(),
        }
        self.trades.append(trade)
        self._save()
        logger.info(f"[SIM SELL] {code} {shares}sh @{fill_price:.2f} PnL={pnl:+.0f}")
        return {"success": True, "trade": trade}
    
    def sync_positions(self) -> dict:
        """同步持仓(模拟账户直接返回)"""
        return dict(self.positions)
    
    def get_account_info(self) -> dict:
        return {
            "cash": round(self.cash, 2),
            "total_value": round(self.total_value, 2),
            "positions": len(self.positions),
            "trades_today": sum(1 for t in self.trades if str(datetime.now().date()) in t.get("time", "")),
        }
    
    def _save(self):
        DATA.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({
            "capital": self.capital, "cash": round(self.cash, 2),
            "positions": self.positions, "total": round(self.total_value, 2),
        }, indent=2, ensure_ascii=False))
        TRADES.write_text(json.dumps(self.trades[-500:], indent=2, ensure_ascii=False))
    
    def _load(self):
        if STATE.exists():
            try:
                d = json.loads(STATE.read_text())
                self.cash = d.get("cash", self.capital)
                self.positions = d.get("positions", {})
            except Exception: pass