"""AI聊天后端 v2 — 可插拔LLM + 规则回退"""
import os, json, sys, urllib.request
from datetime import datetime
from typing import Optional

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ)

from fastapi import APIRouter

router = APIRouter()

# ── 配置 ──
CONFIG_PATH = os.path.join(PROJ, "config", "ai_providers.json")

DEFAULT_CONFIG = {
    "provider": "rule",  # rule | deepseek | openrouter | freellmapi
    "deepseek_api_key": "",
    "openrouter_api_key": "",
    "freellmapi_url": "http://localhost:3001/v1",
    "model": "deepseek-chat",
}

def _load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            return json.load(open(CONFIG_PATH, "r"))
        except:
            pass
    return dict(DEFAULT_CONFIG)

def _get_market_context():
    ctx = {"time": datetime.now().strftime("%Y-%m-%d %H:%M")}
    sp = os.path.join(PROJ, "backend", "data", "engine_state.json")
    if os.path.exists(sp):
        try:
            s = json.load(open(sp, "r"))
            ctx["score"] = s.get("market_score", 50)
            ctx["regime"] = s.get("market_regime", "range")
        except:
            pass
    try:
        r = urllib.request.urlopen("http://qt.gtimg.cn/q=sh000001,sz399001,sz399006", timeout=3)
        raw = r.read().decode("gbk")
        idx = []
        for line in raw.split(";"):
            p = line.split("~")
            if len(p) > 32:
                nm = p[1]; pr = p[3]; cg = p[32]
                if nm: idx.append(f"{nm}{pr}({cg}%)")
        ctx["indices"] = " | ".join(idx[:3])
    except:
        ctx["indices"] = "--"
    return ctx

# ── LLM调用 ──
def _call_deepseek(msg, agent_ctx, cfg):
    """DeepSeek API"""
    key = cfg.get("deepseek_api_key", "")
    if not key:
        return None
    try:
        data = json.dumps({
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": agent_ctx},
                {"role": "user", "content": msg}
            ],
            "max_tokens": 500,
        }).encode()
        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=data,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
        )
        r = urllib.request.urlopen(req, timeout=15)
        d = json.loads(r.read())
        return d["choices"][0]["message"]["content"]
    except:
        return None

def _call_openrouter(msg, agent_ctx, cfg):
    """OpenRouter API"""
    key = cfg.get("openrouter_api_key", "")
    if not key:
        return None
    try:
        data = json.dumps({
            "model": "deepseek/deepseek-chat:free",
            "messages": [
                {"role": "system", "content": agent_ctx},
                {"role": "user", "content": msg}
            ],
        }).encode()
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
                "HTTP-Referer": "https://localhost:7878",
            }
        )
        r = urllib.request.urlopen(req, timeout=15)
        d = json.loads(r.read())
        return d["choices"][0]["message"]["content"]
    except:
        return None

# ── 规则引擎 (无需Key) ──
TEMPLATES = {
    "market": "当前市场评分{score}分，状态{regime}。\n指数: {indices}\n建议: {'市场偏强，可关注强势板块回调机会。' if score >= 60 else '市场震荡，控制仓位。'}",
    "strategy": "当前{'可适当积极' if score >= 60 else '建议保守'}，严格止损。",
    "risk": "单笔亏损不超过2%，总回撤不超过10%。",
    "position": "持仓建议关注多周期共振信号和资金流向。一只股票仓位不超过总资金20%。",
}

def _rule_reply(msg, ctx):
    ml = msg.lower()
    s = ctx.get("score", 50)
    r = ctx.get("regime", "range")
    if any(k in ml for k in ["大盘","市场","指数","行情"]):
        return TEMPLATES["market"].format(score=s, regime=r, indices=ctx.get("indices",""))
    if any(k in ml for k in ["策略","操作","买卖"]):
        return TEMPLATES["strategy"].format(score=s)
    if any(k in ml for k in ["风险","止损","回撤"]):
        return TEMPLATES["risk"]
    if any(k in ml for k in ["持仓","组合","仓位"]):
        return TEMPLATES["position"]
    return f"当前市场评分{s}分({r})。可以问我：大盘/策略/风险/持仓方面的问题。"

# ═══ API端点 ═══
@router.post("/api/ai/chat")
async def ai_chat(body: dict):
    msg = (body.get("message") or "").strip()
    agent_id = body.get("agent_id", "")
    if not msg:
        return {"reply": "请输入问题"}
    
    cfg = _load_config()
    ctx = _get_market_context()
    
    # Agent系统提示
    agent_ctx = f"你是Aurora AI量化投资助手。当前市场评分{ctx.get('score',50)}分，状态{ctx.get('regime','range')}。请用中文回答，简洁专业。"
    
    reply = None
    provider = cfg.get("provider", "rule")
    
    # 尝试LLM
    if provider == "deepseek":
        reply = _call_deepseek(msg, agent_ctx, cfg)
    elif provider == "openrouter":
        reply = _call_openrouter(msg, agent_ctx, cfg)
    
    # 回退规则引擎
    if not reply:
        reply = _rule_reply(msg, ctx)
    
    return {"reply": reply, "provider": provider if reply else "rule"}

@router.get("/api/ai/providers")
async def get_providers():
    """获取当前AI提供商配置状态"""
    cfg = _load_config()
    return {
        "current": cfg.get("provider", "rule"),
        "providers": {
            "rule": {"name": "规则引擎", "status": "ready", "need_key": False},
            "deepseek": {"name": "DeepSeek", "status": "ready" if cfg.get("deepseek_api_key") else "need_key", "need_key": True},
            "openrouter": {"name": "OpenRouter", "status": "ready" if cfg.get("openrouter_api_key") else "need_key", "need_key": True},
        }
    }
