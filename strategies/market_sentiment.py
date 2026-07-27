"""市场呼吸/情绪感知 — 通过量价数据感知市场的"体温"
   像一个老交易员说的:"今天这个市场有点不对劲"
"""
import logging, numpy as np
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("aurora.sentiment")

class MarketSentiment:
    """市场情绪感知器"""
    
    @staticmethod
    def compute_breath(data: dict = None) -> dict:
        """计算市场呼吸指数(0-100)
        高分=健康牛市,低分=恐慌熊市,中间=正常震荡
        """
        score = 50  # 基准
        
        # 1. 涨跌比 (上涨家数/下跌家数)
        up_down = data.get("up_stocks", 0) / max(data.get("down_stocks", 1), 1)
        if up_down > 2: score += 15      # 普涨
        elif up_down > 1.2: score += 8   # 偏涨
        elif up_down < 0.5: score -= 15  # 普跌
        elif up_down < 0.8: score -= 8   # 偏跌
        
        # 2. 涨停/跌停比
        limit_up = data.get("limit_up", 0) or 0
        limit_down = data.get("limit_down", 0) or 0
        limit_ratio = limit_up / max(limit_down, 1)
        if limit_ratio > 5: score += 10       # 做多情绪强
        elif limit_ratio < 0.2: score -= 10   # 做空情绪强
        
        # 3. 成交量变化 (放量/缩量)
        vol_ratio = data.get("volume_ratio", 1) or 1
        if vol_ratio > 1.5: score += 5    # 放量
        elif vol_ratio < 0.6: score -= 5  # 缩量
        
        # 4. 北向资金
        nb = data.get("northbound", 0) or 0
        if nb > 50: score += 10
        elif nb < -50: score -= 10
        elif nb > 20: score += 5
        elif nb < -20: score -= 5
        
        score = max(0, min(100, score))
        
        # 判断当前"呼吸"状态
        if score >= 75: state = "亢奋(过热)"
        elif score >= 60: state = "活跃(健康)"
        elif score >= 40: state = "平稳(正常)"
        elif score >= 25: state = "低迷(谨慎)"
        else: state = "恐慌(危险)"
        
        return {"score": score, "state": state, "time": datetime.now().strftime("%H:%M")}
    
    @staticmethod
    def market_feeling(market_score: float, sentiment_score: float) -> str:
        """综合市场分数和市场情绪,给出盘感描述"""
        diff = sentiment_score - market_score
        
        if diff > 20:
            return "市场实际情绪比指数看起来热,可能还有上涨空间"
        elif diff < -20:
            return "指数看着还行,但市场情绪已经转冷,注意风险"
        elif market_score >= 60 and sentiment_score >= 60:
            return "市场健康,个股活跃,适合积极操作"
        elif market_score < 40 and sentiment_score < 40:
            return "市场偏弱,缩量观望,减少操作"
        else:
            return "市场正常震荡,精选个股,不追高不杀跌"

sentiment = MarketSentiment()
