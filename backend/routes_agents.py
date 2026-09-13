"""AI交易员管理系统 — Fincept式多Agent架构"""
import os, json, sys, urllib.request
from datetime import datetime

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ)

from fastapi import APIRouter

router = APIRouter()

# 12位AI交易员画像
AGENTS = [
    {"id": "buffett", "name": "巴菲特", "icon": "🦉", "style": "价值投资",
     "desc": "寻找拥有持久竞争优势、合理价格的好公司",
     "persona": "你是沃伦·巴菲特，奉行价值投资哲学。关注企业的长期竞争优势、现金流和护城河。"},
    {"id": "graham", "name": "格雷厄姆", "icon": "📐", "style": "安全边际",
     "desc": "严格的安全边际原则，寻找低于内在价值的标的",
     "persona": "你是本杰明·格雷厄姆，价值投资之父。强调安全边际和低估值的选股策略。"},
    {"id": "lynch", "name": "彼得·林奇", "icon": "🔍", "style": "成长投资",
     "desc": "从日常生活中发现十倍股，关注PEG和成长性",
     "persona": "你是彼得·林奇，擅长从日常消费中发现成长股。关注PEG、增长率、品类空间。"},
    {"id": "soros", "name": "索罗斯", "icon": "🌀", "style": "反身性",
     "desc": "利用市场反身性和趋势的自我强化效应",
     "persona": "你是乔治·索罗斯，反身性理论大师。关注市场趋势、自我强化循环和转折点。"},
    {"id": "dali o", "name": "达利欧", "icon": "⚖️", "style": "风险平价",
     "desc": "全天候策略，通过资产配置实现风险平衡",
     "persona": "你是瑞·达利欧，桥水基金创始人。奉行全天候策略，关注宏观经济周期和风险平价。"},
    {"id": "munger", "name": "芒格", "icon": "🧠", "style": "多元思维",
     "desc": "用多元思维模型做投资决策，避免认知偏见",
     "persona": "你是查理·芒格，推崇多元思维模型和反向思考。关注心理偏见和商业本质。"},
    {"id": "akl", "name": "艾略特", "icon": "🌊", "style": "波浪理论",
     "desc": "利用艾略特波浪理论识别市场周期阶段",
     "persona": "你是拉尔夫·艾略特，波浪理论创始人。通过波浪结构分析市场所处阶段和方向。"},
    {"id": "livermore", "name": "利弗莫尔", "icon": "🎯", "style": "趋势跟踪",
     "desc": "在关键点入场，让利润奔跑，截断亏损",
     "persona": "你是杰西·利弗莫尔，史上最伟大的投机者。关注关键点、最小阻力方向和仓位管理。"},
    {"id": "oden", "name": "欧奈尔", "icon": "📊", "style": "CANSLIM",
     "desc": "通过CANSLIM七维选股体系寻找成长股",
     "persona": "你是威廉·欧奈尔，CANSLIM选股体系创始人。综合基本面和技术面寻找强势成长股。"},
    {"id": "david", "name": "大卫", "icon": "💼", "style": "上班族短线",
     "desc": "Aurora默认画像，适合上班族的短线交易系统",
     "persona": "你是上班族短线交易员，利用有限时间做高效决策。偏好明确的买卖信号。"},
    {"id": "trend", "name": "趋势者", "icon": "📈", "style": "趋势跟踪",
     "desc": "Aurora趋势跟踪画像，顺势而为",
     "persona": "你是趋势跟踪交易者，坚信趋势是你的朋友。顺势而为，不抄底不逃顶。"},
    {"id": "value", "name": "价值者", "icon": "💰", "style": "深度价值",
     "desc": "Aurora价值投资画像，长期持有优质标的",
     "persona": "你是价值投资者，关注低估值高股息优质公司。耐心持有，等待价值回归。"},
]

@router.get("/api/agents")
async def get_agents():
    """返回所有AI交易员画像"""
    result = []
    for a in AGENTS:
        result.append({
            "id": a["id"],
            "name": a["name"],
            "icon": a["icon"],
            "style": a["style"],
            "desc": a["desc"],
        })
    return {"agents": result}

@router.post("/api/agents/chat")
async def agent_chat(body: dict):
    """指定交易员回答问题"""
    agent_id = body.get("agent_id", "david")
    message = (body.get("message") or "").strip()
    
    # 找对应Agent
    agent = None
    for a in AGENTS:
        if a["id"] == agent_id:
            agent = a
            break
    if not agent:
        agent = AGENTS[0]
    
    # 获取市场上下文
    ctx = f"当前评分{_get_score()}分"
    
    # 基于关键词的规则回复（不依赖LLM）
    msg_lower = message.lower()
    if any(k in msg_lower for k in ["市场", "大盘", "指数"]):
        reply = f"作为{agent['name']}（{agent['style']}），我认为当前市场{ctx}。{agent['desc']}"
    elif any(k in msg_lower for k in ["策略", "操作", "买卖"]):
        reply = f"以{agent['style']}的视角：{agent['desc']}建议等待明确信号后再行动。"
    else:
        reply = f"{agent['name']}（{agent['style']}）：{agent['desc']}当前市场{ctx}，建议关注自己能力圈内的机会。"
    
    return {
        "reply": reply,
        "agent": {"id": agent["id"], "name": agent["name"], "icon": agent["icon"]}
    }

def _get_score():
    try:
        p = os.path.join(PROJ, "backend", "data", "engine_state.json")
        if os.path.exists(p):
            s = json.load(open(p, "r"))
            return s.get("market_score", 50)
    except:
        pass
    return 50
