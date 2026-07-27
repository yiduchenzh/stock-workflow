"""日内三级选股 — 早盘·盘中·尾盘不同策略
   核心原则: 按仓位管理持续扫描,满足条件即可开仓
"""
import sys, time, json, logging
from pathlib import Path
from datetime import datetime, time as dtime
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("aurora.intraday")
DATA = Path(__file__).resolve().parent.parent / "data"

# 时段定义
MORNING = (dtime(9,25), dtime(10,0))
MID     = (dtime(10,0), dtime(14,30))
TAIL    = (dtime(14,30), dtime(14,57))

def get_session():
    n = datetime.now().time()
    if MORNING[0] <= n < MORNING[1]: return "morning"
    if MID[0] <= n < MID[1]: return "mid"
    if TAIL[0] <= n < TAIL[1]: return "tail"
    return "closed"

SESSION_NAMES = {"morning":"早盘","mid":"盘中","tail":"尾盘","closed":"闭市"}
SESSION_STRS  = {"morning":"早盘强势+跳空缺口","mid":"突破确认+盘口动量","tail":"尾盘强势+收盘决策"}

# ─── 能否开仓检查 ───
def can_open_position(engine) -> dict:
    """检查是否还能开新仓,返回{ok,reason,available_slots}"""
    maxpos = engine.cfg.get("risk",{}).get("max_positions", 5)
    current = len(getattr(engine,"positions",{}))
    cash = getattr(engine,"cash", 1000000)
    if hasattr(engine,"account") and hasattr(engine.account,"cash"):
        cash = engine.account.cash
    elif hasattr(engine,"_day_start_value"):
        cash = engine._day_start_value
    
    available = maxpos - current
    if available <= 0:
        return {"ok":False, "reason":f"已达上限{maxpos}只","slots":0}
    if cash < 50000:
        return {"ok":False, "reason":"剩余资金不足","slots":0}
    return {"ok":True, "reason":f"可用{available}仓","slots":available, "cash":cash}

# ─── 检查是否已持仓或已有计划 ───
def already_in_engine(engine, code: str) -> bool:
    """检查股票是否已在持仓或计划中"""
    for p in getattr(engine,"positions",{}):
        if p == code: return True
    for p in getattr(engine,"plans",[]):
        if p.get("code") == code: return True
    return False

# ─── 早盘选股 ───
def scan_morning(engine) -> list:
    from data.sources import get_tencent_quotes
    from screening.cascade import cascade_screen
    from screening.strong_stock import screen_strong_stocks
    
    cap = can_open_position(engine)
    if not cap["ok"]: return []
    
    phase = getattr(engine, 'phase', 'monitor')
    candidates = cascade_screen(engine.cfg, phase=phase) if hasattr(engine,"cfg") else []
    if not candidates: return []
    quotes = get_tencent_quotes(candidates)
    
    signals = []
    for code, q in quotes.items():
        if already_in_engine(engine, code): continue
        chg = q.get("change_pct",0)
        price = q.get("price",0)
        vol_ratio = q.get("vol_ratio",0)
        # 早盘强势条件: 高开+放量
        # 熊市条件更严格: 涨幅需>3%且量比>2.0
        r = getattr(engine,"market_regime","range")
        min_chg = 3.0 if r.startswith("bear") else 2.0
        min_vr = 2.0 if r.startswith("bear") else 1.5
        if chg > min_chg and vol_ratio > min_vr and price > 0:
            signals.append({
                "code":code,"name":q.get("name",""),"strategy":"morning_gap",
                "score":min(chg*10,90),"entry_price":price,
                "reason":f"早盘强势↑{chg:.1f}% 量比{vol_ratio:.1f}"
            })
    return signals

# ─── 尾盘选股 ───
def scan_tail(engine) -> list:
    from data.sources import get_tencent_quotes
    from screening.cascade import cascade_screen
    cap = can_open_position(engine)
    if not cap["ok"]: return []
    
    phase = getattr(engine, 'phase', 'monitor')
    candidates = cascade_screen(engine.cfg, phase=phase) if hasattr(engine,"cfg") else []
    if not candidates: return []
    quotes = get_tencent_quotes(candidates)
    
    signals = []
    for code, q in quotes.items():
        if already_in_engine(engine, code): continue
        chg = q.get("change_pct",0)
        price = q.get("price",0)
        turnover = q.get("turnover",0)
        r = getattr(engine,"market_regime","range")
        min_chg = 2.0 if r.startswith("bear") else 0
        min_to = 3.0 if r.startswith("bear") else 2.0
        if chg > min_chg and turnover > min_to and price > 0:
            signals.append({
                "code":code,"name":q.get("name",""),"strategy":"tail_momentum",
                "score":min(50+chg*5,85),"entry_price":price,
                "reason":f"尾盘强势↑{chg:.1f}% 换手{turnover:.1f}%"
            })
    return signals

# ─── 统一入口 ───
def run_intraday_cycle(engine) -> dict:
    session = get_session()
    sname = SESSION_NAMES.get(session,"")
    sstr = SESSION_STRS.get(session,"")
    
    cap = can_open_position(engine)
    logger.info(f"[决策] {sname} | {cap['reason']} | 可开:{cap['ok']}")
    
    if not cap["ok"]:
        return {"session":sname,"new_signals":0,"reason":cap["reason"]}
    
    if session == "morning": signals = scan_morning(engine)
    elif session == "tail": signals = scan_tail(engine)
    else: signals = []
    
    if signals:
        for s in signals[:cap["slots"]]:
            if not already_in_engine(engine, s["code"]):
                engine.plans.append(s)
        logger.info(f"[Intraday] {sname} 新增{len(signals)}信号(上限{cap['slots']})")
        DATA.mkdir(parents=True, exist_ok=True)
        (DATA / "intraday_signals.json").write_text(
            json.dumps({"time":datetime.now().isoformat(),"session":sname,"signals":signals},
                      indent=2, ensure_ascii=False))
    
    return {"session":sname,"new_signals":len(signals),"total_plans":len(engine.plans)}