"""风格切换检测 + 自适应参数"""
import logging, json, numpy as np
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger("aurora.adaptive")

class StyleDetector:
    """风格切换检测: 大盘vs小盘,价值vs成长"""
    
    @staticmethod
    def detect_style(quotes: dict = None) -> dict:
        """检测当前市场风格"""
        # 用已有数据近似判断
        # 默认中等风格
        style = {"large_cap": 50, "small_cap": 50, "value": 50, "growth": 50}
        
        if not quotes: return style
        
        # 从行情数据中估计大小盘偏好
        large_count = sum(1 for c in quotes if c.startswith(("6","0","300")) and c != "688")
        small_count = sum(1 for c in quotes if c not in ("6","0","300"))
        
        style["large_cap"] = min(100, large_count)
        style["small_cap"] = min(100, small_count)
        
        return style
    
    @staticmethod
    def style_advice(style: dict) -> str:
        if style["large_cap"] > 60: return "大盘股风格,关注沪深300成分股"
        elif style["small_cap"] > 60: return "小盘股风格,关注中证1000"
        else: return "混合风格,均衡配置"

class AdaptiveParams:
    """自适应参数 — 根据近期胜率自动调整交易参数"""
    
    def __init__(self):
        self.data_file = Path(__file__).resolve().parent.parent / "data" / "adaptive_params.json"
        self.params = self._load()
    
    def _load(self) -> dict:
        if self.data_file.exists():
            try: return json.loads(self.data_file.read_text())
            except: pass
        return {
            "momentum_confirm": 2.0,  # 突破确认幅度(%)
            "stop_loss_mult": 1.0,    # 止损倍数
            "take_profit_mult": 1.0,  # 止盈倍数
            "min_vol_ratio": 1.5,     # 最低量比
            "max_positions_mult": 1.0,# 仓位倍数
            "consecutive_losses": 0,  # 连续亏损次数
            "last_update": datetime.now().isoformat(),
        }
    
    def _save(self):
        self.params["last_update"] = datetime.now().isoformat()
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self.data_file.write_text(json.dumps(self.params, indent=2))
    
    def update_from_trades(self, trades: list, win_rate: float):
        """根据近期交易表现自动调参"""
        if len(trades) < 5: return
        
        cl = 0
        for t in trades[-10:]:
            if t.get("pnl_pct", 0) < 0: cl += 1
            else: cl = 0
        self.params["consecutive_losses"] = cl
        
        # 连续亏损 -> 收紧
        if cl >= 3:
            self.params["momentum_confirm"] = min(3.0, self.params["momentum_confirm"] * 1.15)
            self.params["stop_loss_mult"] = max(0.7, self.params["stop_loss_mult"] * 0.9)
            self.params["min_vol_ratio"] = min(3.0, self.params["min_vol_ratio"] * 1.1)
            logger.info(f"[Adaptive] 连续{cl}笔亏损,收紧参数")
        
        # 持续盈利 -> 放宽
        elif win_rate > 0.6 and len(trades) >= 10:
            self.params["momentum_confirm"] = max(1.5, self.params["momentum_confirm"] * 0.95)
            self.params["stop_loss_mult"] = min(1.2, self.params["stop_loss_mult"] * 1.05)
            self.params["min_vol_ratio"] = max(1.2, self.params["min_vol_ratio"] * 0.95)
            logger.info(f"[Adaptive] 胜率{win_rate:.0%},放宽参数")
        
        self._save()
    
    def get_confirmation_threshold(self, base: float) -> float:
        """获取调整后的确认门槛"""
        return round(base * self.params["stop_loss_mult"], 2)
    
    def get_stop_loss(self, base_pct: float) -> float:
        return round(base_pct * self.params["stop_loss_mult"], 4)
