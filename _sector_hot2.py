# -*- coding: utf-8 -*-
"""热点板块选股 v2 — 前3(强) vs 后3(回调) vs 低位 vs 低位缩量"""
import sqlite3, numpy as np
from collections import defaultdict

H=r"file:D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db?mode=ro"
M=r"file:D:\MarketData\market.db?mode=ro"

m=sqlite3.connect(M,uri=True)
ss=defaultdict(list)
for code,sid in m.execute("SELECT code,sector_id FROM stock_sector"):
    ss[code].append(sid)
m.close()

h=sqlite3.connect(H,uri=True)
alld=sorted(d for d, in h.execute("SELECT DISTINCT date FROM kline_daily_qfq WHERE code='sh000001'"))
dpos={d:i for i,d in enumerate(alld)}; ND=len(alld)
idxc={d:c for d,c in h.execute("SELECT date,close FROM kline_daily_qfq WHERE code='sh000001'")}
def iret(d,N):
    j=dpos.get(d)
    if j is None or j+N>=ND: return None
    return idxc[alld[j+N]]/idxc[alld[j]]-1

lu_cnt=defaultdict(int)
cur=h.execute("SELECT code,date,close FROM kline_daily_qfq WHERE code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]' ORDER BY code,date")
prev=None; ds=[]; cls=[]
def p1(code,ds,cls):
    c=np.array(cls,float); n=len(c)
    if n<10 or np.any(c<=0): return
    thr=0.195 if code[:3] in ('300','688') else 0.098
    pct=c[1:]/c[:-1]-1
    for k in (np.where(pct>=thr)[0]+1):
        if ds[k] not in dpos: continue
        for sid in ss.get(code,()): lu_cnt[(ds[k],sid)]+=1
for code,d,c in cur:
    if code!=prev:
        if cls: p1(prev,ds,cls)
        ds=[];cls=[];prev=code
    ds.append(d);cls.append(c)
if cls: p1(prev,ds,cls)

bysec=defaultdict(dict)
for (d,sid),cnt in lu_cnt.items(): bysec[sid][dpos[d]]=cnt
hot=set()
for sid,dd in bysec.items():
    for i in range(ND-2):
        if dd.get(i,0)>=3 and dd.get(i+1,0)>=3 and dd.get(i+2,0)>=3: hot.add((alld[i+2],sid))
hot_dates=set(d for d,_ in hot)
print(f"热点(日期,板块) {len(hot)}")

allc={}
pool=defaultdict(list)
cur=h.execute("SELECT code,date,close,volume FROM kline_daily_qfq WHERE code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]' ORDER BY code,date")
prev=None; ds=[]; cls=[]; vls=[]
def p2(code,ds,cls,vls):
    c=np.array(cls,float); allc[code]=c; n=len(c)
    if n<80: return
    v=np.array(vls,float); cv=np.cumsum(v)
    vr=np.full(n,np.nan); vr[20:]=v[20:]/((cv[20:]-cv[:-20])/20+1e-9)
    thr=0.195 if code[:3] in ('300','688') else 0.098
    sids=ss.get(code,())
    if not sids or n<61: return
    from numpy.lib.stride_tricks import sliding_window_view
    w=sliding_window_view(c,60); rmax60=w.max(axis=1); rmin60=w.min(axis=1)
    for i,d in enumerate(ds):
        if d not in hot_dates or i<65 or i+1>=n: continue
        if c[i]/c[i-1]-1>=thr: continue
        r5=c[i]/c[i-5]-1
        pos=(c[i]-rmin60[i-60])/(rmax60[i-60]-rmin60[i-60]+1e-9)*100
        for sid in sids:
            if (d,sid) in hot: pool[(d,sid)].append((code,i,r5,pos,vr[i]))
for code,d,c,vo in cur:
    if code!=prev:
        if cls: p2(prev,ds,cls,vls)
        ds=[];cls=[];vls=[];prev=code
    ds.append(d);cls.append(c);vls.append(float(vo or 0))
if cls: p2(prev,ds,cls,vls)
h.close()

NH=[1,3,5,10,20]
def newset(): return {N:[0.0,0,0] for N in NH}
TOP=newset(); BOT=newset(); ALL=newset(); LOW=newset(); LOWS=newset()
def add(t,code,i,d):
    c=allc[code]; n=len(c)
    for N in NH:
        if i+1+N<n:
            ir=iret(d,N)
            if ir is not None:
                e=c[i+1+N]/c[i+1]-1-ir
                t[N][0]+=e; t[N][1]+=1; t[N][2]+=(e>0)
for (d,sid),lst in pool.items():
    for code,i,pos,vr in ((x[0],x[1],x[3],x[4]) for x in lst): add(ALL,code,i,d)
    for code,i,r5,pos,vr in sorted(lst,key=lambda x:-x[2])[:3]: add(TOP,code,i,d)
    for code,i,r5,pos,vr in sorted(lst,key=lambda x:x[2])[:3]: add(BOT,code,i,d)
    for code,i,r5,pos,vr in lst:
        if pos<30: add(LOW,code,i,d)
        if pos<30 and (not np.isnan(vr)) and vr<0.7: add(LOWS,code,i,d)

def pr(name,t):
    s=f"{name:<28}"
    for N in NH:
        dd=t[N]; s+= f"{'—':>13}" if dd[1]<80 else f"{dd[0]/dd[1]*100:+5.1f}%/{dd[2]/dd[1]*100:3.0f}%"
    print(s)
print(f"{'策略':<28}"+"".join(f"{'N='+str(N):>13}" for N in NH))
print("-"*96)
pr("热点·全体(非涨停)", ALL)
pr("热点·前3(涨最猛)", TOP)
pr("热点·后3(回调最深)", BOT)
pr("热点·低位(60日分位<30)", LOW)
pr("热点·低位+缩量", LOWS)
print("-"*96)
print("超额=减同期上证; 买入=次日收盘持有N日")
