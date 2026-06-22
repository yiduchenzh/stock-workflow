"""推送系统 v2.0 — 竞价/信号/复盘 分阶段推送"""
import os, requests, logging
from datetime import datetime
logger = logging.getLogger("aurora.push")

def push_auction_results(engine):
    candidates = getattr(engine, "candidates", [])
    screened = getattr(engine, "screened", [])
    title = f"🔍 Aurora 竞价选股 {datetime.now():%m-%d %H:%M}"
    desc = f"市场: {engine.market_regime} ({engine.market_score:.0f}/100)\n候选: {len(candidates)}只\nCAN SLIM通过: {len(screened)}只\n"
    if screened:
        desc += "\nTOP 5:\n"
        for s in screened[:5]:
            desc += f"  {s.get('code','?')} {s.get('name','?')} CS={s.get('can_slim',0)}({s.get('cs_grade','?')})\n"
    _send(title, desc, engine)

def push_trade_signal(engine):
    plans = getattr(engine, "plans", [])
    alerts = getattr(engine, "alerts", [])
    t0 = getattr(engine, "t0_plans", [])
    if not plans and not alerts and not t0: return
    title = f"📈 Aurora 交易信号 {datetime.now():%H:%M}"
    desc = ""
    if plans:
        desc += f"🟢 开仓: {len(plans)}笔\n"
        for p in plans[:3]:
            desc += f"  {p.get('code','?')} {p.get('name','?')} {p.get('strategy','?')} @{p.get('entry_price',0):.2f} x{p.get('shares',0)} w={p.get('weight',0):.2f}\n"
    if t0:
        desc += f"\n🔄 T+0: {len(t0)}个\n"
        for t in t0[:3]:
            desc += f"  {t.get('code','?')} {t.get('t0_type','?')} {t.get('direction','?')} {t.get('shares',0)}sh score={t.get('score',0)}\n"
    if alerts:
        desc += f"\n⚠️ 告警: {len(alerts)}条\n"
        for a in alerts[:3]:
            desc += f"  [{a.get('type','?')}] {a.get('code','')} {a.get('msg','')}\n"
    _send(title, desc, engine)

def push_daily_review(engine):
    plans = getattr(engine, "plans", [])
    alerts = getattr(engine, "alerts", [])
    account = getattr(engine, "account", None)
    title = f"📋 Aurora 复盘 {datetime.now():%m-%d}"
    desc = f"市场: {engine.market_regime} ({engine.market_score:.0f}/100)\n今日交易: {len(plans)}笔\n告警: {len(alerts)}条\n"
    if account:
        info = account.get_account_info()
        desc += f"账户: 现金{info.get('cash',0):,.0f} 总{info.get('total_value',0):,.0f}\n持仓: {info.get('positions',0)}只\n"
    from strategies.evolution import get_all_health
    health = get_all_health()
    desc += "\n策略:\n"
    for n, h in list(health.items())[:5]:
        if h.get('trades', 0) > 0:
            desc += f"  {n}: {h['status']} wr={h.get('win_rate','?')}\n"
    from strategies.behavior import diagnose
    diag = diagnose()
    if diag.get("issues"):
        desc += f"\n⚠️ 行为: {'; '.join(diag['issues'])}"
    _send(title, desc, engine)

def _send(title, desc, engine):
    token = engine.cfg.get("notify", {}).get("sct_token", "")
    if not token: return
    try:
        token = os.environ.get("SCT_TOKEN", token)
        if not token or len(token) < 10: return
        requests.post(f"https://sctapi.ftqq.com/{token}.send",
            json={"title": title, "desp": desc}, timeout=10)
        logger.info(f"[Push] {title[:30]}...")
    except: pass