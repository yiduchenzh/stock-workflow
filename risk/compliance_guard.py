"""风险合规检查器 — 程序化交易合规"""
import logging
logger = logging.getLogger("aurora.compliance")

class ComplianceGuard:
    """A股量化交易合规检查 (证监会令第179号/2024)"""
    
    MAX_DAILY_ORDERS = 300       # 个人程序化交易建议上限
    MAX_POSITION_PCT = 0.10      # 单票持仓<10%
    BAN_AUCTION_PERIODS = [      # 禁止下单时段
        (9*60+15, 9*60+20),      # 9:15-9:20 集合竞价(可撤单)
        (9*60+20, 9*60+25),      # 9:20-9:25 集合竞价(不可撤)
        (14*60+57, 15*60),       # 14:57-15:00 收盘集合竞价
    ]
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.daily_order_count = 0
        self.today = ""
    
    def check_order(self, code: str, order_type: str = "new") -> tuple:
        """检查单笔交易合规性, 返回 (通过, 原因)"""
        from datetime import datetime
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        
        # 日交易频率检查
        if today != self.today:
            self.daily_order_count = 0
            self.today = today
        self.daily_order_count += 1
        if self.daily_order_count > self.MAX_DAILY_ORDERS:
            return False, f"超日交易上限{self.MAX_DAILY_ORDERS}笔"
        
        # 集合竞价禁止下单时段
        time_min = now.hour * 60 + now.minute
        for start, end in self.BAN_AUCTION_PERIODS:
            if start <= time_min < end:
                return False, f"集合竞价时段({start//60}:{start%60:02d}-{end//60}:{end%60:02d})禁止下单"
        
        # 涨跌停价格合规(应由交易所接口检查)
        return True, "ok"
    
    def check_position_concentration(self, positions: dict, capital: float) -> list:
        """检查持仓集中度"""
        alerts = []
        for code, pos in positions.items():
            value = pos.get("shares", 0) * pos.get("current_price", 0)
            pct = value / capital if capital > 0 else 0
            if pct > self.MAX_POSITION_PCT:
                alerts.append({"type": "concentration", "code": code,
                               "msg": f"持仓{value:.0f}占资金{pct:.1%}>上限{self.MAX_POSITION_PCT:.0%}"})
        return alerts
