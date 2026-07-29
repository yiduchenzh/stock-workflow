"""多数据源交叉验证 — 腾讯 vs TDX TCP 同一策略对比"""
import sys, os, json, time
from datetime import datetime
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent.parent))
from data.sources import get_kline as tencent_kline
from strategies.runner import _check_wave_point
from strategies.momentum_breakout import check_momentum_breakout
from strategies.mean_reversion import check_mean_reversion
S = "2024-01-01"
E = datetime.now().strftime("%Y-%m-%d")
CAP = 1000000; MP = 100; MXP = 5; STOP = 0.07; RR = 2.8
CD = ["000001","000002","000333","000568","000651","000858",
      "002304","002415","002475","300059","600036","600276",
      "600887","601166","601318","601899","600030","600585"]
STRATS = [
    ("wave_point", lambda df: _check_wave_point(df) if len(df)>=30 else 0),
    ("momentum_breakout", lambda df: check_momentum_breakout(df)["score"]
     if len(df)>=30 else 0),
    ("mean_reversion", lambda df: check_mean_reversion(df)["score"]*2
     if len(df)>=30 else 0),
]
class XVal:
    def __init__(self, name, loader): self.name=name;self.loader=loader;self.kc={}
    def load(self, codes, days=500):
        import pandas as pd
        ok=0
        for co in codes:
            try:
                df=self.loader(co, days)
                if df is not None and not df.empty:
                    df["date"]=pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
                    self.kc[co]=df; ok+=1
            except: pass
        print(f"[{self.name}] {ok}/{len(codes)}")
        return ok
    def run(self, name, fn):
        import pandas as pd
        al=set()
        for df in self.kc.values():
            if "date" in df.columns: al.update(df["date"].values)
        al=sorted([d for d in al if S<=d<=E])
        if not al: return {"trades":0,"pnl":0,"wr":0,"pf":0}
        cash=CAP; pos={}; trades=[]
        for dt in al:
            for co in list(pos.keys()):
                p=pos[co]; df=self.kc.get(co)
                if df is None: continue
                r=df[df["date"]==dt]
                if r.empty:
                    m=df[df["date"]<=dt]
                    if m.empty: continue
                    r=m.iloc[-1:]
                if r.empty: continue
                cp=float(r["close"].iloc[-1])
                if cp<=p["stop"]:
                    pnl=(cp-p["entry"])*p["shares"];cash+=cp*p["shares"]
                    trades.append({"pnl":pnl,"reason":"stop"}); del pos[co]; continue
                tp=p["entry"]*(1+RR*STOP)
                if cp>=tp:
                    pnl=(cp-p["entry"])*p["shares"];cash+=cp*p["shares"]
                    trades.append({"pnl":pnl,"reason":"tp"}); del pos[co]; continue
                ed=datetime.strptime(p["date"],"%Y-%m-%d")
                nd=datetime.strptime(dt,"%Y-%m-%d")
                if (nd-ed).days>60:
                    pnl=(cp-p["entry"])*p["shares"];cash+=cp*p["shares"]
                    trades.append({"pnl":pnl,"reason":"time"}); del pos[co]; continue
            if len(pos)>=MXP: continue
            cans=[]
            for co in CD:
                if co in pos: continue
                df=self.kc.get(co)
                if df is None: continue
                k=df[df["date"]<=dt].tail(120).copy()
                if len(k)<30: continue
                c2=k["close"].values; cur=float(c2[-1])
                if cur<=0 or cur>MP: continue
                sc=fn(k)
                if sc>=55:
                    h,l,cl=k["high"].values,k["low"].values,k["close"].values
                    tr=[max(h[i]-l[i],abs(h[i]-cl[i-1]),abs(l[i]-cl[i-1])) for i in range(1,min(15,len(cl)))]
                    atr=np.mean(tr) if tr else cur*0.02
                    cans.append({"co":co,"sc":sc,"px":cur,"sl":cur-2*atr})
            if not cans: continue
            cans.sort(key=lambda x:-x["sc"])
            for ca in cans:
                if len(pos)>=MXP: break
                co=ca["co"]
                if co in pos: continue
                rps=ca["px"]-ca["sl"]
                if rps<=0: continue
                rsh=int(cash*0.01/rps/100)*100;psh=int(cash*0.20/ca["px"]/100)*100
                sh=max(100,min(psh,rsh) if rsh>0 else psh)
                cost=sh*ca["px"]
                if cost>cash:
                    sh=int(cash/ca["px"]/100)*100
                    if sh<100: continue; cost=sh*ca["px"]
                pos[co]={"entry":ca["px"],"shares":sh,"stop":ca["sl"],"date":dt}; cash-=cost
        for co,p in list(pos.items()):
            df=self.kc.get(co)
            last=float(df["close"].iloc[-1]) if df is not None else p["entry"]
            pnl=(last-p["entry"])*p["shares"];cash+=last*p["shares"]
            trades.append({"pnl":pnl,"reason":"end"})
        n=len(trades);wins=[t for t in trades if t["pnl"]>0];losses=[t for t in trades if t["pnl"]<=0]
        wr=len(wins)/n*100 if n>0 else 0;tp=sum(t["pnl"] for t in trades)
        gp=sum(t["pnl"] for t in wins);gl=abs(sum(t["pnl"] for t in losses))
        pf=gp/gl if gl>0 else 0
        return {"trades":n,"wr":round(wr,1),"pf":round(pf,2),"pnl":round(tp,0),"ret":round((cash-CAP)/CAP*100,2) if abs(cash-CAP)>0 else 0}
if __name__=="__main__":
    import pandas as pd
    t0=time.time()
    print("="*60);print("  多数据源交叉验证");print("="*60)
    xt=XVal("tencent",tencent_kline);xt.load(CD)
    xw=None
    xw = None
    for name,fn in STRATS:
        print(f"\n--- {name} ---")
        rt=xt.run(name,fn)
        print(f"  Tencent: {rt['trades']:>3}tr WR={rt['wr']:>5.1f}% PF={rt['pf']:>5.2f} P&L={rt['pnl']:>+8.0f} Ret={rt['ret']:>+6.2f}%")
    print(f"\nTime: {time.time()-t0:.1f}s")