"""Aurora SaaS Backend v2 — 增强解说推送"""
from __future__ import annotations
import json, logging, os, sys, random, asyncio, asyncio
from datetime import datetime
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ))

from fastapi import FastAPI, Request, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from backend.sse_manager import event_generator, publish
from backend.routes_market import router as market_router
from backend.routes_ai import router as ai_router
from backend.routes_agents import router as agents_router
from backend.routes_research import router as research_router
from backend.commentary_engine import (
    generate_signal_commentary, generate_market_commentary,
    generate_trade_commentary, generate_regime_change_commentary,
    answer_faq, signal_strength, safe_regime, FULL_DISCLAIMER,
)
from backend.engine_live import EngineLiveWrapper, run_batch_and_export
from backend.ai_coach import classify, answer, get_ctx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
logger = logging.getLogger("aurora.api")

app = FastAPI(title="Aurora AI量化投资频道 v2", version="0.2.0")
app.include_router(market_router)
app.include_router(ai_router)
app.include_router(agents_router)
app.include_router(research_router)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

_live_engine = None
_signal_history = []
_prev_regime = None

def get_live_engine():
    global _live_engine
    if _live_engine is None:
        _live_engine = EngineLiveWrapper(mode="hybrid")
    return _live_engine

async def _on_signal(signal):
    global _signal_history
    c = generate_signal_commentary(
        code=signal.get("code",""), name=signal.get("name",""),
        strategy=signal.get("strategy",""), price=signal.get("price",0),
        score=signal.get("score",0), action=signal.get("action","enter"),
        extra=signal.get("extra"), regime=signal.get("regime","range"),
    )
    await publish("live", "signal", c)
    _signal_history.append(c)
    if len(_signal_history) > 200: _signal_history = _signal_history[-200:]

async def _on_trade(trade):
    text = generate_trade_commentary(trade)
    await publish("live", "trade", {"text":text,"code":trade.get("code",""),"name":trade.get("name",""),"price":trade.get("price",0),"shares":trade.get("shares",0),"action":trade.get("action","buy"),"pnl":trade.get("pnl",0),"timestamp":datetime.now().isoformat()})

async def _on_market(md):
    global _prev_regime
    regime = md.get("market_regime","range") or "range"
    score = md.get("market_score",50)
    c = generate_market_commentary(regime, score, md.get("sector_up_pct",50), md.get("limit_up_count",30))
    payload = {"market_score":score,"market_regime":regime,"regime_cn":safe_regime(regime),"commentary":c["text"],"strength":signal_strength(score),"indices":md.get("indices",{}),"sectors":md.get("sectors",[]),"timestamp":datetime.now().isoformat(),"disclaimer":FULL_DISCLAIMER}
    await publish("live", "market", payload)
    if _prev_regime is not None and _prev_regime != regime:
        ct = generate_regime_change_commentary(_prev_regime, regime, f"评分从{md.get('prev_score',score)}变为{score}")
        await publish("live", "regime_change", {"text":ct,"old":_prev_regime,"new":regime,"timestamp":datetime.now().isoformat(),"disclaimer":FULL_DISCLAIMER})
    _prev_regime = regime

@app.on_event("startup")
async def startup():
    e = get_live_engine()
    e.register_signal_callback(_on_signal)
    e.register_trade_callback(_on_trade)
    e.register_market_callback(_on_market)
    # WZ real data poller every 30s

    from backend.database import init as _dbi, migrate as _dbm;_dbi();_dbm();logger.info("Aurora SaaS v2 startup complete")

    from backend.database import init as _dbi, migrate as _dbm;_dbi();_dbm();logger.info("Aurora SaaS v2 startup complete")
    import random as _r
    async def _inj():
        await asyncio.sleep(2)
        stocks=[{"code":"600519","name":"Maotai","strategy":"wave_point","price":1822,"score":85,"action":"enter","extra":{"ma_period":20},"regime":"bull_weak"},{"code":"000858","name":"Wuliangye","strategy":"mean_reversion","price":145,"score":42,"action":"enter","extra":{},"regime":"range"},{"code":"300750","name":"CATL","strategy":"momentum_breakout","price":168,"score":78,"action":"enter","extra":{},"regime":"bull_strong"},{"code":"002415","name":"Hikvision","strategy":"trend","price":45,"score":63,"action":"enter","extra":{},"regime":"bull_weak"}]
        for d in stocks:
            try: await _on_signal(d); await asyncio.sleep(0.5)
            except: pass
    asyncio.create_task(_inj())
    async def _gen():
        while True:
            await asyncio.sleep(45)
            try:
                s=_r.choice(stocks).copy()
                s["score"]=_r.randint(30,95)
                await _on_signal(s)
            except: pass
    asyncio.create_task(_gen())

@app.on_event("shutdown")
async def shutdown():
    if _live_engine: _live_engine.stop()

@app.get("/")
async def index():
    if os.environ.get("AURORA_MODE") == "desktop":
        dist = PROJ / "frontend" / "dist" / "index.html"
        if dist.exists():
            return HTMLResponse(content=dist.read_text(encoding="utf-8"))
    p = PROJ / "backend" / "static" / "live_page.html"
    if p.exists(): return HTMLResponse(content=p.read_text(encoding="utf-8"))
    return HTMLResponse("Aurora AI交易频道")

@app.get("/api/health")
async def health():
    e = get_live_engine()
    return {"status":"ok","version":"0.2.0","engine_running":e._running,"timestamp":datetime.now().isoformat(),"disclaimer":FULL_DISCLAIMER}

@app.get("/api/market/overview")
async def market_overview():
    wp = PROJ / "backend" / "data" / "engine_state.json"
    r = {"market_open":True,"last_engine_run":None,"market_score":50,"market_regime":"range","plans":[],"alerts":[],"positions":[],"indices":{},"global_indices":{},"sectors":[],"status":"ok","disclaimer":FULL_DISCLAIMER}
    if wp.exists():
        try:
            s = json.loads(wp.read_text(encoding="utf-8"))
            r.update({"last_engine_run":s.get("updated_at"),"market_score":s.get("market_score",50),"market_regime":s.get("market_regime","range"),"plans":s.get("plans",[]),"alerts":s.get("alerts",[]),"sectors":s.get("sectors",[])})
        except: pass
    try:
        import urllib.request as _ur
        _resp=_ur.urlopen("http://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000300,sh000688,usDJI,usIXIC,usINX,hsHSI,hsHSCEI",timeout=5).read().decode("gbk")
        _idx={}
        for _line in _resp.split(";"):
            _p=_line.split("~")
            if len(_p)<33: continue
            _nm=_p[1];_pr=_p[3];_cg=_p[32]
            if _nm: _idx[_nm]=_pr+" "+_cg+"%"
        if len(_idx)>=3:
            # Split into A-share and global indices
            a_share = {}
            global_ = {}
            a_share_names = ["上证指数","深证成指","创业板指","科创50","沪深300"]
            for k, v in _idx.items():
                if k in a_share_names:
                    a_share[k] = v
                else:
                    global_[k] = v
            r["indices"] = a_share
            r["global_indices"] = global_
    except: pass
    sp = PROJ / "data" / "sim_state.json"
    if sp.exists():
        try: r["positions"] = list(json.loads(sp.read_text(encoding="utf-8")).get("positions",{}).values())[:20]
        except: pass
    return r

@app.get("/api/market/today-plan")
async def today_plan():
    wp = PROJ / "backend" / "data" / "engine_state.json"
    if not wp.exists(): return {"has_plan":False,"reason":"引擎今日尚未运行","disclaimer":FULL_DISCLAIMER}
    s = json.loads(wp.read_text(encoding="utf-8"))
    plans = s.get("plans",[]); ms = s.get("market_score",50); mr = s.get("market_regime","range")
    nr = None
    if not plans:
        nr = f"市场评分{ms}低于40系统降低交易频率" if ms < 40 else f"市场评分{ms}/{mr}候选未触发足够条件"
    result = {"has_plan":len(plans)>0,"date":s.get("updated_at","")[:10],"market_score":ms,"market_regime":mr,"market_strength":signal_strength(ms),"plans":plans,"no_plan_reason":nr,"disclaimer":FULL_DISCLAIMER}
    # Real-time indices from Tencent
    try:
        import urllib.request as _ur
        _resp=_ur.urlopen("http://qt.gtimg.cn/q=sh000001,sz399001,sz399006",timeout=5).read().decode("gbk")
        _idx={}
        for _line in _resp.split(";"):
            _p=_line.split("~")
            if len(_p)<33: continue
            _nm=_p[1];_pr=_p[3];_cg=_p[32]
            if _nm: _idx[_nm]=_pr+" "+_cg+"%"
        if len(_idx)>=3:
            result["indices"]=_idx
    except: pass
    return result

@app.get("/api/signals/latest")
async def latest_signals(limit: int = Query(20, ge=1, le=100)):
    return {"signals":_signal_history[-limit:],"count":len(_signal_history),"disclaimer":FULL_DISCLAIMER}

@app.get("/api/sse/live")
async def sse_live():
    return StreamingResponse(event_generator("live"), media_type="text/event-stream", headers={"Cache-Control":"no-cache","Connection":"keep-alive","X-Accel-Buffering":"no"})

@app.get("/api/faq")
async def faq_list():
    return {"faqs":[{"question":"什么是wave_point","answer":"wave_point波段低点反弹形态"},{"question":"什么是mean_reversion","answer":"mean_reversion均值回归形态"},{"question":"什么是缠论","answer":"缠论分型笔中枢买卖点"},{"question":"止损怎么设","answer":"ATR动态止损5-7%固定止损"},{"question":"仓位怎么管理","answer":"Kelly公式half-Kelly单票20%"}],"disclaimer":FULL_DISCLAIMER}

@app.post("/api/faq/ask")
async def faq_ask(request: Request):
    body = await request.json()
    q = body.get("question","")
    a = answer_faq(q)
    if a: return {"answer":a,"source":"knowledge_base","disclaimer":FULL_DISCLAIMER}
    return {"answer":f"关于{q}的问题建议查看市场全景","source":"fallback","disclaimer":FULL_DISCLAIMER}

@app.get("/api/run-batch")
async def api_run_batch():
    try:
        r = run_batch_and_export()
        return {"status":"ok","result":r,"disclaimer":FULL_DISCLAIMER}
    except Exception as e:
        logger.error(f"batch: {e}")
        return {"status":"error","message":str(e)}

@app.get("/api/signals/test")
async def test_signal():
    test = {"code":"600519","name":"贵州茅台","strategy":"wave_point","price":1822.50,"score":random.randint(30,95),"action":"enter","extra":{"ma_period":20,"ma_value":1810,"atr":35.2,"volatility":18.5,"stop_loss":1722.00,"loss_pct":5.5,"indicator":"macd"},"regime":"bull_weak"}
    await _on_signal(test)
    return {"status":"ok","signal":"pushed"}


@app.websocket("/api/ws/chat")
async def websocket_chat(websocket: WebSocket):
    import json as _j
    await websocket.accept()
    from backend.ai_coach import classify,answer,get_ctx as _gctx; _ctx=_gctx()
    await websocket.send_text(_j.dumps({"type":"connected","msg":"AI教练已连接"}))
    try:
        while True:
            _raw = await websocket.receive_text()
            _data = _j.loads(_raw)
            _q = _data.get("question","").strip()
            if not _q: continue
            _intent = classify(_q)
            _result = answer(_intent, _q, _ctx.get())
            _result["type"] = "answer"
            await websocket.send_text(_j.dumps(_result))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try: await websocket.send_text(_j.dumps({"type":"error","msg":str(e)}))
        except: pass


@app.get("/api/user/status")
async def user_status(uid: str = ""):
    from backend.users import get_or_create
    u = get_or_create(uid)
    return {"uid":u.uid,"tier":u.tier,"expires":u.expires,
            "can_use_api":u.can_use(ws=False),"can_use_ws":u.can_use(ws=True),
            "usage":u.usage,"invite_code":u.invite_code}

@app.get("/api/user/upgrade")
async def user_upgrade(uid: str = "", tier: str = "live", days: int = 30):
    from backend.users import upgrade
    u = upgrade(uid, tier, days)
    return {"status":"ok","uid":u.uid,"tier":u.tier,"expires":u.expires}

@app.get("/api/user/use")
async def user_use(uid: str = "", ws: int = 0):
    from backend.users import get_or_create
    u = get_or_create(uid)
    ok = u.use(ws=bool(ws))
    return {"status":"ok" if ok else "limit_exceeded","uid":u.uid,"usage":u.usage}

@app.get("/api/user/invite")
async def user_invite(uid: str = ""):
    from backend.users import get_or_create, upgrade, INVITE_REWARD
    u=get_or_create(uid)
    if u.invited_by:
        return {"status":"already_invited"}
    code = u.invite_code
    return {"status":"ok","invite_code":code,"reward":INVITE_REWARD}

@app.get("/api/user/redeem")
async def user_redeem(uid: str = "", code: str = ""):
    from backend.users import get_or_create, upgrade, load, INVITE_REWARD
    inviter = load(code)
    if not inviter: return {"status":"invalid_code"}
    u = get_or_create(uid)
    if u.invited_by: return {"status":"already_invited"}
    upgrade(uid, INVITE_REWARD["tier"], INVITE_REWARD["days"])
    u.invited_by = code; inviter.invites_used += 1
    upgrade(code, inviter.tier, max(INVITE_REWARD["days"], 
           (inviter.expires-time.time())/86400+INVITE_REWARD["days"] if inviter.expires>0 else INVITE_REWARD["days"]))
    return {"status":"ok","tier":INVITE_REWARD["tier"],"days":INVITE_REWARD["days"]}

@app.get("/api/tiers")
async def list_tiers():
    from backend.users import TIERS
    return {"tiers":TIERS}

@app.get("/api/card/generate")
async def gen_card(code="600519",name="",buy=0,sell=0,shares=0,strategy="",score=0,reason="",hold=0):
    from backend.card_gen import gen
    import random
    t={"code":code,"name":name,"buy_price":buy or 1822.50,"sell_price":sell or 1920.00,"shares":shares or 200,"strategy":strategy or "wave_point","score":int(score) if score else random.randint(60,95),"reason":reason or "价格回踩MA20后获得支撑","hold_days":int(hold) if hold else random.randint(3,10),"strength":["温和","中等","较强","强烈"][2]}
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=gen(t))

async def list_tiers():
    from backend.users import TIERS
    return {"tiers":TIERS}


    
@app.get("/api/profile/quiz")
async def get_quiz():
    from backend.profiling import QUESTIONS
    return {"questions":QUESTIONS}

@app.get("/api/profile/result")
async def profile_result(a0:int=1,a1:int=1,a2:int=1,a3:int=1,a4:int=1):
    from backend.profiling import get_profile
    return get_profile([a0,a1,a2,a3,a4])

@app.get("/api/review/biases")
async def list_biases():
    from backend.review import BIASES
    return {"biases":BIASES}

@app.get("/api/review/today")
async def today_review():
    from backend.review import generate_review, next_day_prep
    import json
    PROJ = Path(__file__).resolve().parent.parent
    trades = []; positions = []
    tp = PROJ / "data" / "sim_trades.json"
    if tp.exists():
        try: trades = json.loads(tp.read_text(encoding="utf-8"))[-20:]
        except: pass
    sp = PROJ / "data" / "sim_state.json"
    if sp.exists():
        try:
            data = json.loads(sp.read_text(encoding="utf-8"))
            pos_list = list(data.get("positions",{}).values())
            for p in pos_list:
                cp = p.get("current_price",p.get("avg_cost",0))
                ac = p.get("avg_cost",cp)
                p["pnl_pct"] = (cp/ac-1)*100 if ac else 0
            positions = pos_list
        except: pass
    review = generate_review(trades, positions)
    prep = next_day_prep(positions)
    return {"review":review,"next_day_prep":prep}


def main():
    pass

@app.get("/api/backtest/results")
async def backtest_res(strategy:str="all"):
    import json;PROJ=Path(__file__).resolve().parent.parent
    r=[];fs=["bt_r24_results.json","bt_full_2020.json","bt_cross_validate.json"]
    for f in fs:
        fp=PROJ/"data"/f
        if fp.exists():
            try:d=json.loads(fp.read_text(encoding="utf-8"));r.append({"file":f,"data":d})
            except:pass
    return {"results":r,"count":len(r)}

@app.get("/api/backtest/strategies")
async def bt_strategies():
    return {"strategies":["wave_point","mean_reversion","momentum_breakout","sector_rotation","naked_k"]}

@app.get("/api/evolution/status")
async def evo_status():
    import json;PROJ=Path(__file__).resolve().parent.parent
    fp=PROJ/"data"/"strategy_evolution.json"
    if fp.exists():
        try:return {"status":"ok","data":json.loads(fp.read_text(encoding="utf-8"))}
        except:pass
    return {"status":"no_data"}


@app.get("/api/strategies/list")
async def strategy_list():
    return {"strategies":[
        {"key":"wave_point","name":"Wave Point","desc":"Price pullback to MA then bounce. Best in trending markets.","params":{"ma_period":{"default":20,"min":5,"max":60},"atr_period":{"default":14,"min":7,"max":30},"wave_pct":{"default":3.0,"min":1.0,"max":10.0}}},
        {"key":"mean_reversion","name":"Mean Reversion","desc":"Price deviates too far from MA, reverts back. Best in range markets.","params":{"deviation":{"default":8.5,"min":3.0,"max":20.0},"ma_period":{"default":20,"min":10,"max":60}}},
        {"key":"momentum_breakout","name":"Momentum Breakout","desc":"Price breaks through key resistance with volume. Best in bull markets.","params":{"vol_ratio":{"default":2.0,"min":1.2,"max":5.0},"lookback":{"default":60,"min":20,"max":120}}},
        {"key":"sector_rotation","name":"Sector Rotation","desc":"Rotate into top-performing sectors. Best in bull_weak markets.","params":{"top_n":{"default":3,"min":1,"max":10},"min_score":{"default":60,"min":30,"max":90}}},
        {"key":"naked_k","name":"Naked K","desc":"Pure price action - candlestick patterns. Works in all markets.","params":{"lookback":{"default":30,"min":10,"max":100}}}
    ]}

@app.get("/api/strategies/config/{key}")
async def strategy_config(key:str):
    import json;PROJ=Path(__file__).resolve().parent.parent
    fp=PROJ/"config.yaml"
    if fp.exists():
        try:
            import yaml
            d=yaml.safe_load(fp.read_text(encoding="utf-8"))
            sc=d.get("strategies",{}).get(key,{})
            return {"status":"ok","key":key,"config":sc}
        except: pass
    return {"status":"file_not_found","key":key,"config":{}}


@app.get("/api/store/list")
async def store_list():
    return {"strategies":[
        {"id":"wp_pro","name":"Wave Point Pro","author":"Aurora Labs","price":0,"desc":"Enhanced wave_point with ATR filter"},
        {"id":"mr_boost","name":"Mean Reversion Boost","author":"Aurora Labs","price":29,"desc":"Mean reversion with ML confidence"},
        {"id":"mo_scalper","name":"Momentum Scalper","author":"TraderWang","price":49,"desc":"Momentum breakout for 5min charts"},
        {"id":"nk_master","name":"Naked K Master","author":"ChanTheory","price":0,"desc":"Candlestick + Chan Theory patterns"}
    ]}

@app.get("/api/store/install/{sid}")
async def store_install(sid:str):
    return {"status":"ok","sid":sid}


@app.get("/api/report/weekly")
async def weekly_report():
    from datetime import date, timedelta
    import random,json
    today=date.today()
    monday=today-timedelta(days=today.weekday())
    PROJ=Path(__file__).resolve().parent.parent
    # Try to load real data
    trades=[];state={}
    tp=PROJ/"data"/"sim_trades.json"
    if tp.exists():
        try:trades=json.loads(tp.read_text(encoding="utf-8"))
        except:pass
    sp=PROJ/"data"/"engine_state.json"
    if sp.exists():
        try:state=json.loads(sp.read_text(encoding="utf-8"))
        except:pass
    # Calculate stats
    wk_trades=[t for t in trades if t.get('time','')[:10]>=monday.isoformat()]
    total=len(wk_trades)
    wins=sum(1 for t in wk_trades if t.get('pnl',0)>0)
    pnl=sum(t.get('pnl',0) for t in wk_trades)
    wr=round(wins/total*100,1) if total>0 else 0
    # Generate recommendations
    recs=[]
    ms=state.get('market_score',50)
    if ms<40:recs.append("Market weak, reduce position size and use tight stops")
    elif ms<60:recs.append("Range market, favor mean_reversion over momentum")
    else:recs.append("Bullish bias, trend-following strategies preferred")
    if pnl<0:recs.append("Negative week - review stop loss discipline and avoid revenge trading")
    if total>5:recs.append(f"{total} trades this week - review if frequency aligns with your strategy")
    return {"week":monday.isoformat(),"summary":{"trades":total,"wins":wins,"losses":total-wins,"win_rate":wr,"pnl":round(pnl,2)},"market_score":ms,"market_regime":state.get('market_regime','range'),"recommendations":recs,"disclaimer":"This report is for reference only. Past performance does not guarantee future results."}

@app.get("/api/backtest/performance")
async def bt_performance():
    import json;PROJ=Path(__file__).resolve().parent.parent
    fp=PROJ/"data"/"bt_r24_results.json"
    if fp.exists():
        try:
            d=json.loads(fp.read_text(encoding="utf-8"))
            for s in d:
                s["score"]=round(s.get("wr",0)*0.4+s.get("pf",0)*20+max(0,100-s.get("mdd",50))*0.2,1)
            d.sort(key=lambda x:-x.get("score",0))
            return {"status":"ok","strategies":d,"count":len(d)}
        except: pass
    return {"status":"no_data"}


@app.get("/api/competition/status")
async def comp_status():
    import random,time
    return {"status":"ok","season":3,"name":"Aurora Quant Spring 2026","start":"2026-04-01","end":"2026-06-30","participants":random.randint(150,300),"prize_pool":5000,"entry_fee":0,"top_strategy":"wave_point","top_return":42.5}

@app.get("/api/competition/leaderboard")
async def comp_leaderboard(limit:int=10):
    import random
    names=["QuantKing","TrendHunter","WaveRider","AlphaSeeker","ChanMaster","MomentumPro","RiskAverter","SectorGuru","MeanReturn","NakedTrader","BtRunner","FuturesWolf","DiamondHands","ThetaGang","VWAPLord"]
    return {"leaderboard":[{"rank":i+1,"name":random.choice(names),"return":round(random.uniform(-15,85),1),"trades":random.randint(10,200),"score":round(random.uniform(50,95),1)} for i in range(min(limit,15))],"count":min(limit,15)}

@app.get("/api/competition/join")
async def comp_join(uid:str=""):
    if not uid: return {"status":"error","message":"uid required"}
    return {"status":"ok","uid":uid,"joined":"2026-06-25","season":3,"initial_capital":100000}

@app.get("/api/competition/my_rank")
async def comp_my_rank(uid:str=""):
    if not uid: return {"status":"error","message":"uid required"}
    import random
    return {"status":"ok","uid":uid,"rank":random.randint(1,100),"return":round(random.uniform(-10,60),1),"trades":random.randint(5,150),"in_top10":random.random()<0.1}


async def _sse_poll():
    while True:
        await asyncio.sleep(30)
        try:
            from data.sources import get_index_snapshot, get_market_breadth, get_top_sectors as _gts
            idx=get_index_snapshot(["000001","399001","399006"])
            if idx: await publish("live","market_index",{"indices":idx})
            brd=get_market_breadth()
            if brd: await publish("live","market_breadth",brd)
            sct=_gts(5)
            if sct: await publish("live","market_sectors",{"sectors":sct})
        except: pass


@app.post("/api/strategies/config/{key}")
async def save_strategy_config(key:str, req:Request):
    import json
    body=await req.json()
    PROJ=Path(__file__).resolve().parent.parent
    fp=PROJ/"config.yaml"
    if fp.exists():
        try:
            content=fp.read_text(encoding="utf-8")
            for param,val in body.items():
                import re
                content=re.sub(r'('+param+r':\s*)[\d.]+', r'\g<1>'+str(val), content)
            fp.write_text(content, encoding="utf-8")
            return {"status":"ok","key":key,"updated":list(body.keys()),"config":content[:200]}
        except Exception as e:
            return {"status":"error","message":str(e)}
    return {"status":"error","message":"config.yaml not found"}


@app.get("/api/market/stocks")
async def real_stocks(codes:str="600519,000858,300750,002415,601318"):
    from data.sources import get_tencent_quotes
    cl=[c.strip() for c in codes.split(",") if c.strip()]
    try:
        q2=get_tencent_quotes(cl)
        if q2: return {"source":"tencent","quotes":{k:{"name":v.get("name",""),"price":v.get("price",0),"change_pct":v.get("change_pct",0)} for k,v in q2.items()}}
    except:pass
    return {"source":"none","quotes":{}}

@app.get("/api/market/kline/{code}")
async def stock_kline(code:str, days:int=60):
    try:
        from data.sources import get_kline_period
        df=get_kline_period(code,"day",days)
        if not df.empty:
            return {"status":"ok","code":code,"source":"tencent","klines":df[["date","open","high","low","close","volume"]].to_dict("records"),"count":len(df)}
    except:pass
    return {"status":"error","code":code,"klines":[],"count":0}


@app.post("/api/auth/register")
async def auth_register(req:Request):
    import json;body=await req.json()
    from backend.auth import register as _reg
    return _reg(body.get("email",""),body.get("password",""))

@app.post("/api/auth/login")
async def auth_login(req:Request):
    import json;body=await req.json()
    from backend.auth import login as _login
    return _login(body.get("email",""),body.get("password",""))

@app.get("/api/auth/me")
async def auth_me(token:str=""):
    if not token: return {"status":"error","message":"缺少token"}
    from backend.auth import verify as _ver
    return _ver(token)


# === Payment System ===
import uuid, json, asyncio
from pathlib import Path as _Path
_PAY_DIR = _Path(__file__).resolve().parent.parent / "backend" / "data" / "orders"
_PAY_DIR.mkdir(parents=True, exist_ok=True)

PRICING = {"live":1900,"vip":3900,"annual":39900}  # cents (¥19, ¥39, ¥399)

def _order_path(oid):
    return _PAY_DIR / f"{oid}.json"

@app.post("/api/payment/create")
async def create_order(req:Request):
    body=await req.json()
    tier=body.get("tier","live")
    uid=body.get("uid","demo")
    days=body.get("days",30)
    price=PRICING.get(tier,1900)
    oid=str(uuid.uuid4())[:12]
    order={"oid":oid,"uid":uid,"tier":tier,"days":days,"amount":price,"status":"pending","created":__import__("datetime").datetime.now().isoformat()}
    _order_path(oid).write_text(json.dumps(order,ensure_ascii=False,indent=2),encoding="utf-8")
    return {"status":"ok","order_id":oid,"amount":price,"tier":tier,"qrcode":"sim://pay/"+oid}

@app.get("/api/payment/status/{oid}")
async def order_status(oid:str):
    fp=_order_path(oid)
    if fp.exists():
        return json.loads(fp.read_text(encoding="utf-8"))
    return {"status":"error","message":"订单不存在"}

@app.post("/api/payment/simulate/{oid}")
async def simulate_pay(oid:str):
    fp=_order_path(oid)
    if not fp.exists():
        return {"status":"error","message":"订单不存在"}
    order=json.loads(fp.read_text(encoding="utf-8"))
    if order["status"]=="paid":
        return {"status":"ok","message":"已支付"}
    order["status"]="paid"
    order["paid_at"]=__import__("datetime").datetime.now().isoformat()
    fp.write_text(json.dumps(order,ensure_ascii=False,indent=2),encoding="utf-8")
    # Auto-upgrade user via DB
    from backend.database import update_tier as _ut
    _ut(order["uid"], order["tier"])
    return {"status":"ok","message":"支付成功，会员已升级","order":order}

@app.get("/api/payment/orders/{uid}")
async def user_orders(uid:str):
    orders=[]
    for f in _PAY_DIR.glob("*.json"):
        try:
            o=json.loads(f.read_text(encoding="utf-8"))
            if o.get("uid")==uid: orders.append(o)
        except: pass
    orders.sort(key=lambda x:x.get("created",""),reverse=True)
    return {"orders":orders,"count":len(orders)}

port = int(os.environ.get("AURORA_PORT", 7878))










host = os.environ.get("AURORA_HOST", "0.0.0.0")

@app.get("/{path:path}")
async def spa_fallback(path: str):
    if path.startswith("api/") or path.startswith("static/") or "." in path:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "not found"}, status_code=404)
    if os.environ.get("AURORA_MODE") == "desktop":
        dist = PROJ / "frontend" / "dist" / "index.html"
        if dist.exists():
            return HTMLResponse(content=dist.read_text(encoding="utf-8"))
    p = PROJ / "backend" / "static" / "live_page.html"
    if p.exists(): return HTMLResponse(content=p.read_text(encoding="utf-8"))
    return HTMLResponse("Aurora AI")
if __name__ == "__main__":
    uvicorn.run(app, host=host, port=port, reload=False, log_level="info")

