"""华泰证券桥接 — 32位Python subprocess JSON通信控制xiadan.exe"""
import json, logging, subprocess, os, time
from pathlib import Path
logger = logging.getLogger("aurora.ht")

# 华泰客户端配置
HT_CLIENT_PATH = r"C:\htzqzyb3\xiadan.exe"
HT_PROCESSES = ["xiadan.exe", "hexin.exe"]
BRIDGE_SCRIPT = Path(__file__).resolve().parent / "ht_bridge_worker.py"

class HTBridge:
    """华泰交易桥接 — 通过subprocess调用32位Python操控客户端"""
    
    def __init__(self, python32_path: str = None):
        # 32位Python路径 (pywinauto需要32位操控32位xiadan.exe)
        self.python32 = python32_path or self._find_python32()
        self.process = None
        self.connected = False
    
    def _find_python32(self) -> str:
        """查找32位Python"""
        candidates = [
            r"d:\Hermes Agent CN Desktop\stock-workflow\.venv32\Scripts\python.exe",
            r"C:\Python312-32\python.exe",
            r"C:\Python311-32\python.exe",
        ]
        for p in candidates:
            if os.path.exists(p): return p
        return "python"  # fallback
    
    def connect(self) -> bool:
        """连接华泰客户端"""
        if not os.path.exists(HT_CLIENT_PATH):
            logger.warning(f"华泰客户端未找到: {HT_CLIENT_PATH}")
            return False
        if not os.path.exists(self.python32):
            logger.warning(f"32位Python未找到: {self.python32}")
            return False
        self.connected = True
        logger.info(f"华泰桥接就绪: client={HT_CLIENT_PATH}, py32={self.python32}")
        return True
    
    def _send_command(self, cmd: dict, timeout: int = 15) -> dict:
        """发送指令到32位Python worker"""
        if not self.connected:
            return {"success": False, "error": "未连接华泰客户端"}
        try:
            result = subprocess.run(
                [self.python32, str(BRIDGE_SCRIPT), json.dumps(cmd)],
                capture_output=True, text=True, timeout=timeout
            )
            return json.loads(result.stdout) if result.stdout else {"success": False, "error": result.stderr}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "指令超时"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def buy(self, code: str, price: float, shares: int) -> dict:
        """买入委托 — 核买(买入确认)"""
        return self._send_command({
            "action": "buy", "code": code,
            "price": round(price, 2), "shares": int(shares / 100) * 100,
        })
    
    def sell(self, code: str, price: float, shares: int) -> dict:
        """卖出委托 — 核卖(卖出确认)"""
        return self._send_command({
            "action": "sell", "code": code,
            "price": round(price, 2), "shares": int(shares / 100) * 100,
        })
    
    def cancel_order(self, order_id: str) -> dict:
        """撤单"""
        return self._send_command({"action": "cancel", "order_id": order_id})
    
    def get_positions(self) -> dict:
        """获取持仓"""
        return self._send_command({"action": "positions"})
    
    def get_balance(self) -> dict:
        """获取资金"""
        return self._send_command({"action": "balance"})
    
    def get_today_trades(self) -> dict:
        """获取当日成交"""
        return self._send_command({"action": "today_trades"})
    
    def close(self):
        self.connected = False
        logger.info("华泰桥接已断开")


class HTAccount:
    """华泰实盘账户 — 通过HTBridge操控xiadan.exe"""
    
    def __init__(self, capital: float = 1_000_000, config: dict = None):
        self.capital = capital
        self.config = config or {}
        self.bridge = HTBridge(config.get("python32_path") if config else None)
        self.positions = {}
        self.cash = capital
        self.connected = False
        self.exec_mode = config.get("exec_mode", "manual") if config else "manual"
    
    def connect(self) -> bool:
        """连接华泰客户端"""
        self.connected = self.bridge.connect()
        if self.connected:
            self._sync()
        return self.connected
    
    def _sync(self):
        """同步持仓和资金"""
        if not self.connected: return
        pos_result = self.bridge.get_positions()
        if pos_result.get("success"):
            self.positions = pos_result.get("positions", {})
        bal_result = self.bridge.get_balance()
        if bal_result.get("success"):
            self.cash = bal_result.get("available", self.cash)
    
    def buy(self, code: str, price: float, shares: int, reason: str = "") -> dict:
        """实盘买入"""
        if not self.connected:
            return {"success": False, "error": "华泰未连接"}
        
        if self.exec_mode == "manual":
            logger.info(f"[HT 人工确认] 买入 {code} {shares}股 @{price:.2f} — {reason}")
            logger.info("  请在华泰客户端确认此交易")
        
        result = self.bridge.buy(code, price, shares)
        if result.get("success"):
            self._sync()
            logger.info(f"[HT BUY] {code} {shares}sh @{price:.2f}")
        return result
    
    def sell(self, code: str, price: float, shares: int, reason: str = "") -> dict:
        """实盘卖出"""
        if not self.connected:
            return {"success": False, "error": "华泰未连接"}
        
        if self.exec_mode == "manual":
            logger.info(f"[HT 人工确认] 卖出 {code} {shares}股 @{price:.2f} — {reason}")
            logger.info("  请在华泰客户端确认此交易")
        
        result = self.bridge.sell(code, price, shares)
        if result.get("success"):
            self._sync()
            logger.info(f"[HT SELL] {code} {shares}sh @{price:.2f}")
        return result
    
    def sync_positions(self) -> dict:
        self._sync()
        return dict(self.positions)
    
    def get_account_info(self) -> dict:
        self._sync()
        return {
            "cash": round(self.cash, 2),
            "total_value": round(self.cash + sum(
                p.get("shares",0) * p.get("current_price", p.get("cost",0))
                for p in self.positions.values()
            ), 2),
            "positions": len(self.positions),
            "connected": self.connected,
        }
    
    @property
    def total_value(self) -> float:
        return self.cash + sum(
            p.get("shares",0) * p.get("current_price", p.get("cost",0))
            for p in self.positions.values()
        )