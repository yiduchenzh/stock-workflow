from .trader_types import detect_profile_from_answers

QUESTIONS = [
    {"id": "q1", "text": "你通常持有股票多久？", "options": [("A", "几小时到1天（超短线）"), ("B", "1-3天（短线）"), ("C", "3-10天（中短线）"), ("D", "10-30天（中长线）"), ("E", "30天以上（长线持有）")]},
    {"id": "q2", "text": "你能接受最大的单笔亏损是多少？", "options": [("A", "不超过5%（保守）"), ("B", "5%-10%（稳健）"), ("C", "10%-15%（进取）"), ("D", "15%以上（激进）")]},
    {"id": "q3", "text": "你每天有多少时间看盘？", "options": [("A", "8小时以上（全职交易）"), ("B", "2-4小时（半职）"), ("C", "早晚各15分钟（上班族）"), ("D", "收盘后看看（佛系）")]},
    {"id": "q4", "text": "你更相信哪种分析方法？", "options": [("A", "纯K线技术分析"), ("B", "基本面+估值"), ("C", "消息面+热点驱动"), ("D", "结合多种方法")]},
    {"id": "q5", "text": "持仓下跌时你通常怎么做？", "options": [("A", "立即止损"), ("B", "再观察一下"), ("C", "加仓摊平成本"), ("D", "放着不管，总会回来的")]},
]

def get_questions():
    return QUESTIONS

def evaluate(answers):
    profile_name = detect_profile_from_answers(answers)
    from .strategy_mapping import get_engine_config
    config = get_engine_config(profile_name)
    return {"matched_profile": profile_name, "description": config["description"], "strategy_weights": config["strategy_weights"], "risk_params": config["risk"], "config": config}