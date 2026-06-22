
"""反身性分析 — 索罗斯繁荣-萧条八阶段"""
import numpy as np
import logging
logger = logging.getLogger("aurora.reflex")

def analyze_reflexivity(market_score: float, regime: str, breadth_data: dict = None) -> dict:
    """反身性状态评估"""
    # 阶段识别 (简化版)
    stages = {
        (75, 100, "bull_strong"): "阶段④: 信念强化/过度扩张 — 反身性正反馈加速",
        (55, 75, "bull_strong"): "阶段③: 通过考验 — 趋势加速",
        (55, 100, "bull_weak"): "阶段②: 趋势加速 — 尚未过度",
        (45, 55, "range"): "阶段①: 未被认知的趋势 或 阶段⑦: 转折点",
        (25, 45, "bear_weak"): "阶段⑥: 顶点/黄昏期 — 认知与现实背离",
        (0, 25, "bear_strong"): "阶段⑧: 崩溃 — 反身性负反馈",
    }
    
    stage_desc = "阶段不明"
    reflexivity_score = 50
    for (lo, hi, reg), desc in stages.items():
        if lo <= market_score <= hi and regime == reg:
            stage_desc = desc
            break
    
    # 反身性评分
    if "过度扩张" in stage_desc:
        reflexivity_score = 20  # 危险: 泡沫中
    elif "趋势加速" in stage_desc and "过度" not in stage_desc:
        reflexivity_score = 70  # 健康: 可以跟随
    elif "崩溃" in stage_desc:
        reflexivity_score = 10  # 极危: 踩踏
    elif "转折" in stage_desc:
        reflexivity_score = 30  # 谨慎
    
    # 正反馈检测: 近期连续大涨+放量
    positive_feedback = market_score >= 70 and regime == "bull_strong"
    
    return {
        "stage": stage_desc,
        "reflexivity_score": reflexivity_score,
        "positive_feedback": positive_feedback,
        "soros_advice": "试探性假设→小仓测试→验证后加码" if reflexivity_score >= 60 else (
            "错时迅速退出" if reflexivity_score <= 20 else "观望等待确认")
    }
