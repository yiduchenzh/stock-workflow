"""策略自动调优 — 按月回算表现，自动降权亏损策略"""
import logging
logger=logging.getLogger("aurora.autotune")
def auto_downgrade(min_trades=5, min_pf=1.0, lookback_days=90):
    try:
        from strategies.evolution import get_all_health, recommend_weights
        health=get_all_health(); rec=recommend_weights()
        adj={}
        for name,h in health.items():
            trades=h.get("trades",0); pf=h.get("pf",0)
            if trades>=min_trades and pf<min_pf:
                old_w=rec.get(name,0); new_w=old_w*0.5
                if new_w<0.1: new_w=0.0
                adj[name]={"old_weight":old_w,"new_weight":round(new_w,2),"reason":f"PF={pf}<{min_pf}"}
                logger.warning(f"[AutoTune] {name}: {adj[name]['reason']}")
        return adj
    except Exception as e: logger.error(f"[AutoTune] fail: {e}"); return {}
def apply_adjustments(engine, adj):
    if not adj: return
    sw=engine.cfg.get("strategy_weights",{}); changed=False
    for name,a in adj.items():
        if name in sw and sw[name]!=a["new_weight"]:
            old=sw[name]; sw[name]=a["new_weight"]; changed=True
            logger.info(f"[AutoTune] {name}: {old}->{a['new_weight']}")
    if changed: engine.cfg["strategy_weights"]=sw
def run_monthly_tune(engine):
    adj=auto_downgrade(); apply_adjustments(engine,adj); return adj