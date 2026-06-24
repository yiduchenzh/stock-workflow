
"""模拟交易账户"""
import json, logging
from datetime import datetime
from pathlib import Path
logger = logging.getLogger("aurora.sim")
DATA = Path(__file__).resolve().parent.parent / "data"
STATE = DATA / "sim_state.json"
TRADES = DATA / "sim_trades.json"
COMM = 0.0003; STAMP = 0.001; SLIP = 0.001

class SimAccount:
    def __init__(self, capital=1_000_000, cfg=None):  # cfg参数兼容engine.py调用
        self.capital = capital; self.cash = capital
        self.positions = {}; self.trades = []
        self._load()

    def buy(self, code, price, shares, reason=""):
        cost = shares * price * (1 + COMM + SLIP)
        if cost > self.cash:
            shares = int(self.cash / (price * (1 + COMM + SLIP)) / 100) * 100
            if shares < 100: return None
            cost = shares * price * (1 + COMM + SLIP)
        self.cash -= cost
        if code in self.positions:
            p = self.positions[code]
            old = p["shares"] * p["avg_cost"]
            p["shares"] += shares
            p["avg_cost"] = round((old + cost) / p["shares"], 4)
        else:
            self.positions[code] = {"shares": shares, "avg_cost": round(cost/shares, 4), "current_price": price}
        t = {"action": "buy", "code": code, "price": price, "shares": shares, "cost": round(cost,2), "reason": reason, "time": datetime.now().isoformat()}
        self.trades.append(t); self._save(); return t

    def sell(self, code, price, shares, reason=""):
        if code not in self.positions: return None
        p = self.positions[code]
        if shares > p["shares"]: shares = p["shares"]
        raw = shares * price
        net = raw * (1 - COMM - STAMP - SLIP)
        pnl = net - shares * p["avg_cost"]
        self.cash += net
        p["shares"] -= shares
        if p["shares"] <= 0: del self.positions[code]
        t = {"action": "sell", "code": code, "price": price, "shares": shares, "net": round(net,2), "pnl": round(pnl,2), "reason": reason, "time": datetime.now().isoformat()}
        self.trades.append(t); self._save(); return t

    # utility: available for future use
    @property
    def total_value(self):
        return self.cash + sum(p["shares"] * p.get("current_price", p["avg_cost"]) for p in self.positions.values())

    def _save(self):
        DATA.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"capital": self.capital, "cash": round(self.cash,2), "positions": self.positions, "total": round(self.total_value,2)}, indent=2, ensure_ascii=False))
        TRADES.write_text(json.dumps(self.trades, indent=2, ensure_ascii=False))

    def _load(self):
        if STATE.exists():
            try:
                d = json.loads(STATE.read_text())
                self.cash = d.get("cash", self.capital)
                self.positions = d.get("positions", {})
            except Exception: pass
