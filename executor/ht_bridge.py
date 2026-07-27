"""华泰证券桥接 — 交易执行接口+模拟实现+xtquant实盘"""
import json, logging
from pathlib import Path
from datetime import datetime
from executor.base import BaseExecutor

logger = logging.getLogger("aurora.ht")
TRADE_LOG = Path(__file__).resolve().parent.parent / "data" / "ht_trade_log.json"

class BaseBroker:
    def connect(self) -> bool: raise NotImplementedError
    def disconnect(self): raise NotImplementedError
    def get_positions(self) -> dict: raise NotImplementedError
    def get_balance(self) -> dict: raise NotImplementedError
    def buy(self, code: str, price: float, shares: int) -> dict: raise NotImplementedError
    def sell(self, code: str, price: float, shares: int) -> dict: raise NotImplementedError

class SimBroker(BaseBroker):
    def __init__(self, capital=1000000):
        self.capital = capital; self.cash = capital
        self.positions = {}; self.orders = []; self.connected = False
    def connect(self):
        self.connected = True; logger.info("[SimBroker] 模拟券商已连接"); return True
    def disconnect(self):
        self.connected = False; logger.info("[SimBroker] 模拟券商已断开")
    def get_positions(self): return dict(self.positions)
    def get_balance(self):
        total = self.cash + sum(p["shares"]*p.get("current_price",p["avg_cost"]) for p in self.positions.values())
        return {"cash": self.cash, "total": total, "frozen": 0}
    def buy(self, code, price, shares):
        cost = price*shares*1.001
        if cost > self.cash: return {"success": False, "error": "资金不足"}
        self.cash -= cost
        if code in self.positions:
            old = self.positions[code]
            total_shares = old["shares"]+shares; total_cost = old["shares"]*old["avg_cost"]+cost
            old["shares"]=total_shares; old["avg_cost"]=total_cost/total_shares
        else: self.positions[code]={"shares":shares,"avg_cost":price,"current_price":price}
        self._log("buy",code,price,shares); return {"success":True,"code":code,"shares":shares,"price":price}
    def sell(self, code, price, shares):
        if code not in self.positions or self.positions[code]["shares"]<shares:
            return {"success":False,"error":"持仓不足"}
        self.positions[code]["shares"]-=shares
        self.cash+=price*shares*0.999
        if self.positions[code]["shares"]<=0: del self.positions[code]
        self._log("sell",code,price,shares); return {"success":True,"code":code,"shares":shares,"price":price}
    def _log(self,action,code,price,shares):
        TRADE_LOG.parent.mkdir(parents=True,exist_ok=True)
        entry={"time":datetime.now().isoformat(),"action":action,"code":code,"price":price,"shares":shares}
        try: h=json.loads(TRADE_LOG.read_text()) if TRADE_LOG.exists() else []
        except: h=[]
        h.append(entry); TRADE_LOG.write_text(json.dumps(h[-500:],indent=2))

class XtQuantBroker(BaseBroker):
    def __init__(self, account_id="", password="", client_path=""):
        self.account_id=account_id; self.password=password; self.client_path=client_path
        self._api=None; self._connected=False
    def connect(self):
        try:
            import xtquant
            logger.info(f"[XtQuant] xtquant {xtquant.__version__} 已加载"); self._connected=True
            if self.client_path:
                from xtquant.xttrader import XtQuantTrader
                self._api = XtQuantTrader(self.client_path)
                self._api.connect()
                logger.info(f"[XtQuant] 已连接QMT: {self.client_path}")
            else:
                logger.info("[XtQuant] 未配置client_path, 使用模拟模式")
            return True
        except ImportError:
            logger.error("[XtQuant] 未安装xtquant"); return False
        except Exception as e: logger.error(f"[XtQuant] 连接失败: {e}"); return False
    def disconnect(self):
        if self._api:
            try: self._api.stop(); logger.info("[XtQuant] 已断开")
            except: pass
        self._connected=False
    def get_positions(self):
        if not self._connected or not self._api: return {}
        try: return self._api.get_stock_positions()
        except: return {}
    def get_balance(self):
        if not self._connected or not self._api: return {"cash":0,"total":0,"frozen":0}
        try: return self._api.get_asset_info()
        except: return {"cash":0,"total":0,"frozen":0}
    def buy(self,code,price,shares):
        if not self._connected: return {"success":False,"error":"未连接"}
        if not self._api:
            logger.warning(f"[XtQuant] 模拟买入: {code} {shares}股")
            return {"success":True,"simulated":True,"code":code}
        try: return self._api.buy(code,price,shares)
        except Exception as e: return {"success":False,"error":str(e)}
    def sell(self,code,price,shares):
        if not self._connected: return {"success":False,"error":"未连接"}
        if not self._api:
            logger.warning(f"[XtQuant] 模拟卖出: {code} {shares}股")
            return {"success":True,"simulated":True,"code":code}
        try: return self._api.sell(code,price,shares)
        except Exception as e: return {"success":False,"error":str(e)}

class HTTradeExecutor(BaseExecutor):
    def __init__(self, capital=1000000, mode="sim", account_id="", password="", client_path=""):
        self.capital=capital; self.mode=mode
        if mode=="sim": self.broker=SimBroker(capital)
        elif mode=="real": self.broker=XtQuantBroker(account_id,password,client_path)
        else: raise ValueError(f"未知模式: {mode}")
        self.broker.connect()
    def buy(self,code,price,shares,reason=""):
        r=self.broker.buy(code,price,shares)
        if r.get("success"): self._log_trade("buy",code,price,shares,reason)
        return r
    def sell(self,code,price,shares,reason=""):
        r=self.broker.sell(code,price,shares)
        if r.get("success"): self._log_trade("sell",code,price,shares,reason)
        return r
    def get_account_info(self):
        b=self.broker.get_balance(); p=self.broker.get_positions()
        return {"cash":b.get("cash",0),"total_value":b.get("total",0),"positions":len(p)}
    def sync_positions(self) -> dict: return self.broker.get_positions()
    def _log_trade(self,action,code,price,shares,reason=""):
        TRADE_LOG.parent.mkdir(parents=True,exist_ok=True)
        entry={"time":datetime.now().isoformat(),"action":action,"code":code,"price":price,"shares":shares,"reason":reason}
        try: h=json.loads(TRADE_LOG.read_text()) if TRADE_LOG.exists() else []
        except: h=[]
        h.append(entry); TRADE_LOG.write_text(json.dumps(h[-500:],indent=2,ensure_ascii=False))
    @property
    def total_value(self): return self.broker.get_balance().get("total",self.capital)
    @property
    def cash(self): return self.broker.get_balance().get("cash",0)
    @property
    def positions(self): return self.broker.get_positions()

def create_executor(mode="sim", **kwargs):
    return HTTradeExecutor(mode=mode, **kwargs)
