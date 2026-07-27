"""统一决策引擎 v2 — 融合模式记忆+情绪感知+自适应+风格检测"""
import sys, logging
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("aurora.decision")

def make_decision_v2(engine) -> dict:
    """增强版决策: 融合市场记忆+情绪+自适应"""
    from strategies.regime import get_regime_config, get_regime_params
    from profiling import get_trader_profile
    from strategies.market_memory import market_memory
    from strategies.market_sentiment import sentiment
    from strategies.style_adaptive import StyleDetector, AdaptiveParams
    
    regime = getattr(engine, "market_regime", "range")
    score = getattr(engine, "market_score", 50)
    profile_name = getattr(engine, "profile_name", "上班族中短线")
    profile = get_trader_profile(profile_name)
    rc = get_regime_config(regime)
    rp = get_regime_params(regime)
    
    # 情绪感知
    sent = sentiment.compute_breath({
        "up_stocks": getattr(engine, "up_stocks", 400),
        "down_stocks": getattr(engine, "down_stocks", 300),
        "limit_up": getattr(engine, "limit_up", 0),
        "limit_down": getattr(engine, "limit_down", 0),
        "volume_ratio": getattr(engine, "volume_ratio", 1),
        "northbound": getattr(engine, "northbound", {}).get("net_flow_yi", 0),
    })
    
    # 风格检测
    style = StyleDetector.detect_style()
    
    # 自适应参数
    ap = AdaptiveParams()
    
    # 仓位信息
    session = _get_session()
    current = len(getattr(engine, "positions", {}))
    plans = len(getattr(engine, "plans", []))
    maxpos = rp.get("max_positions", 5)
    available = max(0, maxpos - current - plans)
    
    return {
        "time": datetime.now().strftime("%H:%M"),
        "session": session,
        "regime": regime,
        "market_score": score,
        "sentiment": sent,         # 新增: 情绪感知
        "feeling": sentiment.market_feeling(score, sent["score"]),  # 新增: 盘感
        "style": style,            # 新增: 风格检测
        "trader": profile_name,
        "available_slots": available,
        "primary_strategy": rc.get("active_strategies", ["mean_reversion"])[0],
        "risk": {
            "stop_loss_pct": ap.get_stop_loss(rp.get("stop_loss_pct", 0.05)),
            "take_profit_pct": rp.get("take_profit_pct", 0.10),
            "confirmation": ap.get_confirmation_threshold(rp.get("confirmation_threshold", 60)),
        },
        "can_trade": available > 0 and sent["score"] > 20,
        "advice": sentiment.market_feeling(score, sent["score"]),
    }

def _get_session():
    from datetime import time as dtime
    n = datetime.now().time()
    if dtime(9,25) <= n < dtime(10,0): return "早盘"
    if dtime(10,0) <= n < dtime(14,30): return "盘中"
    if dtime(14,30) <= n < dtime(14,57): return "尾盘"
    return "闭市"
