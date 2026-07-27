"""统一决策引擎 — 交易员×市场×战法×仓位 联动决策"""
import sys, logging
from pathlib import Path
from datetime import datetime, time as dtime
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("aurora.decision")

# ─── 时段定义 ───
MORNING = (dtime(9,25), dtime(10,0))
MID     = (dtime(10,0), dtime(14,30))
TAIL    = (dtime(14,30), dtime(14,57))

SESSION_NAMES = {
    "morning": "早盘(09:25-10:00)",
    "mid": "盘中(10:00-14:30)",
    "tail": "尾盘(14:30-14:57)",
    "closed": "闭市",
}

def get_session():
    n = datetime.now().time()
    if MORNING[0] <= n < MORNING[1]: return "morning"
    if MID[0] <= n < MID[1]: return "mid"
    if TAIL[0] <= n < TAIL[1]: return "tail"
    return "closed"

# ─── 核心决策函数 ───
def make_decision(engine) -> dict:
    """全维度决策：根据交易员+市场+仓位+时段，输出当前最佳行动方案"""
    from strategies.regime import get_regime_config, get_regime_params
    from profiling import get_trader_profile
    
    session = get_session()
    regime = getattr(engine, "market_regime", "range")
    score = getattr(engine, "market_score", 50)
    profile_name = getattr(engine, "profile_name", "上班族中短线")
    profile = get_trader_profile(profile_name)
    rp = get_regime_params(regime)
    rc = get_regime_config(regime)
    
    # 1. 当前该用什么战法?
    session_name = SESSION_NAMES.get(session, "闭市")
    session_strategies = {
        "morning": "跳空突破+集合竞价强势",
        "mid": "动量确认+均线支撑",
        "tail": "尾盘动量+收盘布局",
    }
    
    # 2. 仓位还有多少空间?
    maxpos = rp.get("max_positions", rc.get("max_positions", 3))
    current = len(getattr(engine, "positions", {}))
    plans = len(getattr(engine, "plans", []))
    available = max(0, maxpos - current - plans)
    
    # 3. 交易员偏好的战法（从画像获取）
    trader_weights = profile.get("strategy_weights", {})
    top_strategies = sorted(trader_weights, key=trader_weights.get, reverse=True)
    
    # 4. 当前regime允许的战法
    allowed = rc.get("active_strategies", ["mean_reversion"])
    
    # 5. 取交集: 交易员喜欢 × 市场允许 × 时段适合
    recommended = [s for s in top_strategies if s in allowed]
    
    # 6. 风控参数
    stop_pct = rp.get("stop_loss_pct", 0.05)
    take_pct = rp.get("take_profit_pct", 0.10)
    kelly = rp.get("kelly_mult", 0.5)
    
    decision = {
        "timestamp": datetime.now().isoformat(),
        "session": session,
        "session_name": session_name,
        "session_strategy": session_strategies.get(session, ""),
        "regime": regime,
        "market_score": score,
        "trader": profile_name,
        "trader_level": profile.get("trader_level", "中级"),
        "trader_style": profile.get("analysis_style", ""),
        "trader_holding": profile.get("holding_period", ""),
        "max_positions": maxpos,
        "current_positions": current,
        "available_slots": available,
        "allowed_strategies": allowed,
        "recommended_strategies": recommended,
        "primary_strategy": recommended[0] if recommended else "无",
        "risk": {
            "stop_loss_pct": stop_pct,
            "take_profit_pct": take_pct,
            "kelly_fraction": kelly,
        },
        "regime_advice": rp.get("trading_advice", ""),
        "description": profile.get("description", ""),
        "can_trade": available > 0 and regime not in ["closed"],
    }
    
    logger.info(f"[决策] {session_name} | {profile_name}({profile.get('trader_level','')}) | "
                f"{regime}({score}分) | 仓位{current}/{maxpos} | "
                f"主战法:{decision['primary_strategy']} | 止损:{stop_pct*100:.0f}%")
    return decision

def filter_stocks_by_decision(stocks: list, engine) -> list:
    """根据决策结果筛选股票"""
    decision = make_decision(engine)
    if not decision["can_trade"]:
        return []
    
    # 1. 按仓位限制数量
    candidates = stocks[:decision["available_slots"]]
    
    # 2. 按交易员风格过滤
    from profiling import get_trader_profile
    profile = get_trader_profile(decision["trader"])
    
    # 3. 按战法偏好排序
    primary = decision["primary_strategy"]
    if primary == "momentum_breakout":
        candidates.sort(key=lambda x: abs(x.get("change_pct", 0)), reverse=True)
    elif primary == "mean_reversion":
        candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    return candidates

def should_scan_now(engine) -> bool:
    """判断当前是否应该执行选股扫描"""
    from strategies.regime import get_regime_config
    regime = getattr(engine, "market_regime", "range")
    session = get_session()
    
    # 闭市不扫描
    if session == "closed":
        return False
    
    # 熊市强(极弱)且尾盘已过
    if regime == "bear_strong" and session == "mid":
        # 熊市盘中可以扫(逆势股)
        return True
    if regime == "bear_strong" and session == "tail":
        return True
    
    # 正常情况
    return True