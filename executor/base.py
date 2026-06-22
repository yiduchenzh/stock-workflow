"""交易执行器抽象层 — 统一模拟/实盘接口"""
from abc import ABC, abstractmethod
import logging
logger = logging.getLogger("aurora.executor")

class BaseExecutor(ABC):
    """交易执行器基类 — 模拟账户和华泰实盘账户共用此接口"""
    
    def __init__(self, capital: float = 1_000_000):
        self.capital = capital
        self.cash = capital
        self.positions = {}
        self.orders = []
        self.trades = []
    
    @abstractmethod
    def buy(self, code: str, price: float, shares: int, reason: str = "") -> dict:
        """买入"""
        pass
    
    @abstractmethod
    def sell(self, code: str, price: float, shares: int, reason: str = "") -> dict:
        """卖出"""
        pass
    
    @abstractmethod
    def sync_positions(self) -> dict:
        """同步持仓(从券商/模拟状态)"""
        pass
    
    @abstractmethod
    def get_account_info(self) -> dict:
        """获取账户信息"""
        pass
    
    @property
    def total_value(self) -> float:
        """总资产"""
        pos_value = sum(p.get("shares", 0) * p.get("current_price", p.get("avg_cost", 0))
                       for p in self.positions.values())
        return self.cash + pos_value
    
    def cancel_all(self):
        """撤销所有未成交订单"""
        self.orders = [o for o in self.orders if o.get("status") == "filled"]
        logger.info("All pending orders cancelled")


def create_executor(mode: str = "paper", capital: float = 1_000_000, config: dict = None):
    """工厂方法: 根据模式创建执行器"""
    if mode == "live":
        from executor.ht_account import HTAccount
        return HTAccount(capital, config)
    else:
        from executor.sim_account import SimAccount
        return SimAccount(capital, config)