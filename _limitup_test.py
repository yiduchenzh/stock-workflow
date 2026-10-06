# -*- coding: utf-8 -*-
"""涨停池实证 — 涨停次日买入的收益, 按 位置/大盘/连板 分组"""
import sqlite3, numpy as np
from collections import defaultdict
from numpy.lib.stride_tricks import sliding_window_view

H = r"file:D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db?mode=ro"
h=sqlite3.connect(H,uri=True)
rows=h.execute("SELECT date,high,low,close FROM kline_daily_qfq WHERE code='sh000001' ORDER BY date").fetchall()
dd=[r[0] for r in rows]; hh=np.array([r[1] for r in rows],float)
ll=np.array([r[2] for r in rows],float); cc=np.array([r[3] for r in rows],float)
rmax=sliding_window_view(hh,250).max(axis=1); rmin=sliding_window_view(ll,250).min(axis=1)
mk={}; didx={}
for i in range(250,len(cc)):
    mk[dd[i]]=(cc[i]-rmin[i-249])/(rmax[i-249]-rmin[i-249]+1e-9)*100; didx[dd[i]]=i
def iret(d,N):
    j=didx.get(d)
    if j is None or j+N>=len(cc): return None
    return cc[j+N]/cc[j]-1

N_HOLD=[1,3,5,20]
# key: (pos档, 连板0/1, mkt档) -> [sum_r, n, wins] per N
G={}
def g(k,N): return G.setdefault((k,N),[0.0,0,0])
ALL={N:[0.0,0,0] for N in N_HOLD}
LOW_SHRINK={N:[0.0,0,0] for N in N_HOLD}   # 对照: 非涨停的低位缩量

def flush(code,dates,buf):
    a=np.array(buf,float); H2,L2,C2,O2,V2=a[:,0],a[:,1],a[:,2],a[:,3],a[:,4]
    if len(C2)<400 or np.any(C2<=0): return
    n=len(C2)
    thr = 0.195 if (code.startswith('300') or code.startswith('688')) else 0.098
    rmax=sliding_window_view(H2,250).max(axis=1); rmin=sliding_window_view(L2,250).min(axis=1)
    vma=sliding_window_view(V2,21).mean(axis=1)
    for i in range(251, n-22):
        pct=C2[i]/C2[i-1]-1
        m=mk.get(dates[i])
        pos=(C2[i]-rmin[i-250])/(rmax[i-250]-rmin[i-250]+1e-9)*100
        pv=0 if pos<30 else (1 if pos<70 else 2)
        mv=(0 if m<30 else (1 if m<70 else 2)) if m is not None else None
        islu = pct>=thr
        lb = islu and (C2[i-1]/C2[i-2]-1)>=thr
        entry=O2[i+1]
        if entry<=0: continue
        if islu and mv is not None:
            for N in N_HOLD:
                if i+1+N>=n: continue
                r=C2[i+1+N]/entry-1
                ir=iret(dates[i+1],N)
                e = r-ir if ir is not None else r
                t=ALL[N]; t[0]+=e; t[1]+=1; t[2]+= (1 if e>0 else 0)
                k=(pv,1 if lb else 0,mv); gg=g(k,N); gg[0]+=e; gg[1]+=1; gg[2]+= (1 if e>0 else 0)
        # 对照: 低位+缩量 (非涨停)
        if not islu and pv==0 and V2[i]/(vma[i-1]+1e-9)<0.7:
            for N in N_HOLD:
                if i+1+N>=n: continue
                ir=iret(dates[i+1],N)
                if ir is None: continue
                e=C2[i+1+N]/entry-1-ir
                t=LOW_SHRINK[N]; t[0]+=e; t[1]+=1; t[2]+= (1 if e>0 else 0)

cur=h.execute("SELECT code,date,high,low,close,volume,open FROM kline_daily_qfq "
              "WHERE code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]' ORDER BY code,date")
prev=None; dates=[]; buf=[]
for code,d,hi,lo,cl,vo,op in cur:
    if code!=prev:
        if buf: flush(prev,dates,buf)
        dates=[]; buf=[]; prev=code
    dates.append(d); buf.append((hi,lo,cl,float(vo or 0),float(op or 0)))
if buf: flush(prev,dates,buf)
h.close()

def line(name,t):
    s=f"{name:<26}"
    for N in N_HOLD:
        d=t[N]; n=d[1]
        s += f"{'—':>14}" if n<80 else f"{d[0]/n*100:+6.1f}%/{d[2]/n*100:3.0f}%"
    print(s)

print("涨停次日开盘买入 → 持有N日 (市场调整超额 / 超额胜率)")
print(f"{'条件':<26}"+"".join(f"{'N='+str(N):>14}" for N in N_HOLD))
print("-"*84)
line("全部涨停(基准)", ALL)
L=['低','中','高']
for pv in range(3):
    for lb in (0,1):
        for mv in range(3):
            lx=("首板" if lb==0 else "连板")
            line(f"{L[pv]}位·{lx}·大盘{L[mv]}", {N:g((pv,lb,mv),N) for N in N_HOLD})
print("-"*84)
line("【对照】低位缩量(非涨停)", LOW_SHRINK)
print("-"*84)
print("超额=个股−同期上证; 涨停股按'次日开盘'买入(涨停当日买不进)")
