# -*- coding: utf-8 -*-
"""AI Coach - intent routing + template Q&A"""
from __future__ import annotations
import json,re,random
from datetime import datetime
from backend.compliance_filter import signal_strength,safe_strategy,safe_regime,FULL_DISCLAIMER
from backend.commentary_engine import answer_faq
class I:
    SIGNAL="signal";POSITION="position";MARKET="market";STRATEGY="strategy";RISK="risk";DEEP="deep";FAQ="faq";GENERAL="general"
_KW = {
    I.SIGNAL: ["signal","trigger","alert","buy","sell"],
    I.POSITION: ["position","hold","portfolio","cost"],
    I.MARKET: ["market","index","today","大盘","行情"],
    I.STRATEGY: ["strategy","wave","mean","momentum","缠论","形态","策略"],
    I.RISK: ["risk","stop","loss","止损","风控","仓位"],
    I.DEEP: ["why","reason","detail","原理","逻辑"],
}
def classify(q):
    ql=q.lower().strip()
    if answer_faq(q): return I.FAQ
    for intent,kws in _KW.items():
        for kw in kws:
            if kw in ql: return intent
    return I.FAQ if answer_faq(q) else I.GENERAL
_GR=["Hi! I am Aurora AI Coach. Ask me about trading.","Welcome! Try asking about strategy or market.","In here! Ask me anything about trading."]
_TM={
    I.SIGNAL:["About {name}({code}) signal, score {score} ({strength})."],
    I.MARKET:["Market: {regime_cn} (score {score})."],
    I.STRATEGY:["Strategy info available for querying."],
    I.RISK:["Risk parameters: ATR={atr:.1f}, stop loss ref {sl:.1f}."],
    I.GENERAL:["Welcome! I can help with strategy, market and risk questions."],
}
def answer(intent,q,ctx=None):
    if intent==I.FAQ:
        a=answer_faq(q)
        if a: return {"answer":a,"intent":"faq","source":"kb","ts":datetime.now().isoformat()}
    if intent==I.GENERAL:
        return {"answer":random.choice(_GR)+"\n\u26a0\ufe0f "+FULL_DISCLAIMER,"intent":"general","source":"greeting","ts":datetime.now().isoformat()}
    ctx=ctx or {}
    t=random.choice(_TM.get(intent,_TM[I.GENERAL]))
    v={"name":ctx.get("name",""),"code":ctx.get("code",""),"score":ctx.get("score",50),"strength":signal_strength(ctx.get("score",50)).get("label",""),"safe_s":safe_strategy(ctx.get("strategy","")),"regime_cn":safe_regime(ctx.get("regime","range")),"atr":ctx.get("atr",35),"sl":ctx.get("sl",70),"commentary":ctx.get("commentary",""),"question":q}
    try: a=t.format(**v)
    except: a=t
    return {"answer":a+"\n\n\u26a0\ufe0f "+FULL_DISCLAIMER,"intent":intent,"source":"template","ts":datetime.now().isoformat()}
class Ctx:
    def __init__(s): s._sig=[];s._mkt=None;s._pos=[]
    def upd_sig(s,d): s._sig=(s._sig+[{"code":d.get("code",""),"name":d.get("name",""),"strategy":d.get("strategy",""),"score":d.get("score",0)}])[-5:]
    def set_mkt(s,m): s._mkt=m
    def set_pos(s,p): s._pos=p
    def get(s):
        r={}
        if s._mkt: r["market"]={"score":s._mkt.get("market_score",50),"regime":s._mkt.get("market_regime","range")}
        if s._sig: r["signals"]=s._sig[-3:]
        return r
_ctx=Ctx()
def get_ctx(): return _ctx
