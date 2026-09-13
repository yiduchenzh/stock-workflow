"""R24 Full Backtest — 2020-2026, all strategies, SimAccount fees, per-strategy analysis"""
import sys, os, json, time
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))

S="2024-01-01"; E=datetime.now().strftime("%Y-%m-%d")
CAP=1000000; MP=100; MXP=5; STOP=0.07; RR=2.8

CD=["000001","000002","000333","000568","000651","000858",
    "002304","002415","002475","300059","600036","600276",
    "600887","601166","601318","601899","600030","600585"]

ALL_STRATS = ["wave_point", "momentum_breakout", "mean_reversion"]

# ------------------------------------------------------------------ 结果缓存开关
# CACHE_ENABLED=True 时,run_strategy 会首先查询结果级缓存,命中直接返回缓存结果,
# 避免同参回测全量重跑。改参数后 key 会变化,自动 MISSED 重跑;无需手动清缓存。
# BUST_CACHE=True 时强制忽略已有缓存、全量重跑,并覆写缓存条目(显式失效)。
CACHE_ENABLED = True
BUST_CACHE = False

# 模块级单例缓存;默认落盘到 data/bt_result_cache.json
from data.result_cache import ResultCache, make_bt_key  # noqa: E402
_BT_CACHE = ResultCache()

def load_data(days=600):
    from data.sources import get_kline as tk
    kc={};ok=0
    for co in CD:
        df=tk(co, days)
        if df is not None and not df.empty:
            df["date"]=pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            kc[co]=df;ok+=1
    print(f"[Data] {ok}/{len(CD)} loaded"); return kc

def get_price(kc, co, dt):
    df=kc.get(co)
    if df is None: return None
    r=df[df["date"]==dt]
    if r.empty:
        m=df[df["date"]<=dt]
        if m.empty: return None
        r=m.iloc[-1:]
    return float(r["close"].iloc[-1]) if not r.empty else None

def get_kline_up_to(kc, co, dt, n=120):
    df=kc.get(co)
    if df is None: return pd.DataFrame()
    s=df[df["date"]<=dt].tail(n).copy()
    return s if len(s)>=30 else pd.DataFrame()

def get_market_regime(kc, dt):
    """Simple market regime from index data"""
    idx=kc.get("000001")
    if idx is None: return "range",50
    m=idx[idx["date"]<=dt].tail(60)
    if len(m)<20: return "range",50
    c=m["close"].values;ma20=np.mean(c[-20:])
    ma60=np.mean(c[-min(60,len(c)):]) if len(c)>=60 else np.mean(c)
    sc=50
    for cond in[c[-1]>ma20,c[-1]>ma60,ma20>ma60]: sc+=10 if cond else 0
    if len(c)>=5 and c[-1]>c[-5]: sc+=10
    if len(c)>=20 and c[-1]==max(c[-20:]): sc+=10
    sc=min(100,max(0,sc))
    if sc>=75: return "bull_strong",sc
    if sc>=55: return "bull_weak",sc
    if sc>=45: return "range",sc
    if sc>=25: return "bear_weak",sc
    return "bear_strong",sc

def make_strategy_params(name):
    """构造包含全部确定性回测参数的 params dict,用于缓存 key.

    任何能影响回测结果的确定性参数都必须进 key,否则改参后仍归老结果(错误)。
    包含: 策略名、时间窗 S->E、账户 CAP、单笔 MP、最大持仓 MXP、止损 STOP、
    盈亏比 RR、CD 标的池(已排序,稳定)。
    """
    return {
        "name": name,
        "S": S,
        "E": E,
        "CAP": CAP,
        "MP": MP,
        "MXP": MXP,
        "STOP": STOP,
        "RR": RR,
        "CD": sorted(CD),  # 排序保证标的池顺序不影响 key
        "n_strats": sorted(ALL_STRATS),  # analyze_all 涉及策略集合
    }


def run_strategy(name, kc):
    from strategies.runner import analyze_all
    from executor.sim_account import SimAccount

    # ---------------- 结果级缓存: 命中直接返回,避免全量重跑 ----------------
    params = make_strategy_params(name)
    if CACHE_ENABLED:
        key = make_bt_key(params)
        if BUST_CACHE:
            print(f"[Cache] BUST (强制重跑并覆写 {name}) key={key}")
        else:
            cached = _BT_CACHE.get(key)
            if cached is not None:
                print(f"[Cache] HIT {name} key={key} 耗时 ~0s (命中磁盘缓存)")
                return cached
            print(f"[Cache] MISSED {name} key={key}")
    else:
        key = None
        print(f"[Cache] DISABLED {name}")

    al=set()
    for df in kc.values():
        if "date" in df.columns: al.update(df["date"].values)
    al=sorted([d for d in al if S<=d<=E])
    print(f"[{name}] {len(al)} days")

    acc=SimAccount(CAP)
    trades=[]

    for di,dt in enumerate(al):
        if di%120==0: print(f"  [{name}] {di}/{len(al)} {dt}")
        rg,ms=get_market_regime(kc,dt)
        if rg=="bear_strong" or ms<30:
            # Close all positions in bear market
            for co in list(acc.positions.keys()):
                cp=get_price(kc,co,dt)
                if cp: acc.sell(co,cp,acc.positions[co]["shares"],"bear_close")
            continue

        # Update existing positions
        for co in list(acc.positions.keys()):
            cp=get_price(kc,co,dt)
            if cp is None: continue
            p=acc.positions[co]
            ep=p.get("avg_cost",cp)
            if cp<=ep*(1-STOP):
                res=acc.sell(co,cp,p["shares"],"stop")
                if res and res.get("trade"): trades.append(res["trade"]); continue
            if cp>=ep*(1+RR*STOP):
                res=acc.sell(co,cp,p["shares"],"tp")
                if res and res.get("trade"): trades.append(res["trade"]); continue
            ed=p.get("entry_date")
            if ed:
                try:
                    ed_dt=datetime.strptime(str(ed)[:10],"%Y-%m-%d")
                    nd=datetime.strptime(dt,"%Y-%m-%d")
                    if (nd-ed_dt).days>60:
                        res=acc.sell(co,cp,p["shares"],"time")
                        if res and res.get("trade"): trades.append(res["trade"]); continue
                except: pass

        if len(acc.positions)>=MXP: continue

        # Find new signals
        for co in CD:
            if co in acc.positions: continue
            k=get_kline_up_to(kc,co,dt)
            if k.empty: continue
            px=float(k["close"].iloc[-1])
            if px<=0 or px>MP: continue
            dummy=[{"code":co,"name":co,"price":px}]
            rr=analyze_all(dummy, kline_override={co:k}, market_regime=rg)
            if rr and rr[0].get("signal"):
                rps=px*STOP
                sh=max(100,int(acc.cash*0.01/rps/100)*100)
                if sh*px<acc.cash: 
                    res=acc.buy(co,px,sh,name)
                    if res: 
                        strat=rr[0].get("best_strategy","?")
                        trades.append({"code":co,"entry":px,"shares":sh,"strategy":strat,"date":dt,"action":"buy"})

    # Close remaining
    for co in list(acc.positions.keys()):
        cp=get_price(kc,co,E)
        if cp:
            res=acc.sell(co,cp,acc.positions[co]["shares"],"end")
            if res and res.get("trade"): trades.append(res["trade"])

    # Calculate detailed stats
    close_trades=[t for t in trades if t.get("action")=="sell" or t.get("pnl") is not None]
    n=len(close_trades);wins=[t for t in close_trades if t.get("pnl",0)>0]
    losses=[t for t in close_trades if t.get("pnl",0)<=0]
    wr=len(wins)/n*100 if n>0 else 0
    tp=sum(t.get("pnl",0) for t in close_trades)
    gp=sum(t.get("pnl",0) for t in wins)
    gl=abs(sum(t.get("pnl",0) for t in losses))
    pf=gp/gl if gl>0 else 0
    avg_win=gp/len(wins) if wins else 0
    avg_loss=gl/len(losses) if losses else 0
    rr_actual=(avg_win/max(avg_loss,1)) if avg_loss>0 else 0

    # MaxDD
    peak=CAP;cum=CAP;mdd=0
    for t in close_trades:
        cum+=t.get("pnl",0)
        if cum>peak: peak=cum
        dd=(peak-cum)/peak*100
        if dd>mdd: mdd=dd
    total_days=(datetime.strptime(E,"%Y-%m-%d")-datetime.strptime(S,"%Y-%m-%d")).days
    ann=(cum/CAP-1)*100/max(total_days/365.25,1) if total_days>0 else 0

    # Per-strategy breakdown
    strat_stats={}
    for t in close_trades:
        s=t.get("strategy","?")
        if s not in strat_stats: strat_stats[s]={"n":0,"w":0,"pnl":0}
        strat_stats[s]["n"]+=1
        if t.get("pnl",0)>0: strat_stats[s]["w"]+=1
        strat_stats[s]["pnl"]+=t.get("pnl",0)

    result = {
        "strategy":name,"period":f"{S}~{E}","n":n,"wr":round(wr,1),
        "pf":round(pf,2),"pnl":round(tp,0),"ret_pct":round((cum/CAP-1)*100,2),
        "ann":round(ann,2),"mdd":round(mdd,2),
        "avg_win":round(avg_win,0),"avg_loss":round(avg_loss,0),"rr":round(rr_actual,2),
        "per_strategy":strat_stats,
    }

    # ---------------- 结果级缓存: 未命中则写入,供同参二次直接命中 ----------------
    if CACHE_ENABLED and key is not None:
        _BT_CACHE.set(key, result)
        print(f"[Cache] SET {name} key={key} 已写入磁盘缓存")

    return result

if __name__=="__main__":
    t0=time.time()
    kc=load_data(1200)

    all_results={}
    for sn in ALL_STRATS:
        print(f"\n{'='*60}\n#  {sn}\n{'='*60}")
        r=run_strategy(sn, kc)
        all_results[sn]=r
        s="+" if r["pnl"]>0 else ""
        print(f"\n  {r['n']}trades | WR {r['wr']}% | PF {r['pf']} | P&L {s}{r['pnl']} | Ret {r['ret_pct']}% | Ann {r['ann']}% | MaxDD {r['mdd']}%")
        print(f"  AvgWin {r['avg_win']:.0f} | AvgLoss {r['avg_loss']:.0f} | RR {r['rr']}")
        print(f"  Per-strategy:")
        for sn2,st in sorted(r.get("per_strategy",{}).items(), key=lambda x:-x[1]["pnl"]):
            swr=st["w"]/st["n"]*100 if st["n"]>0 else 0
            print(f"    {sn2:20s} {st['n']:3d}tr WR={swr:5.1f}% P&L {st['pnl']:+8.0f}")

    print(f"\n{'='*60}")
    print(f"  R24 Full Backtest Summary: {S} ~ {E}")
    print(f"{'='*60}")
    for sn, r in sorted(all_results.items(), key=lambda x:-x[1]["pf"]):
        s="+" if r["pnl"]>0 else ""
        print(f"  {sn:20s} | {r['n']:4d}tr | WR {r['wr']:5.1f}% | PF {r['pf']:5.2f} | P&L {s}{r['pnl']:>+8.0f} | Ret {r['ret_pct']:>+6.2f}% | Ann {r['ann']:>+5.2f}% | MaxDD {r['mdd']:5.2f}%")

    json.dump(all_results, open(Path(__file__).parent/"data"/"bt_full_2020.json","w"), indent=2, ensure_ascii=False)
    print(f"\n[Saved] data/bt_full_2020.json")
    if CACHE_ENABLED:
        st = _BT_CACHE.stats()
        print(f"[Cache] 命中统计: hits={st['hits']} misses={st['misses']} hit_rate={st['hit_rate']}% (共{st['total']}次查询)")
    print(f"Time: {time.time()-t0:.1f}s")