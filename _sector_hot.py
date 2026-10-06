# -*- coding: utf-8 -*-
"""热点板块选股验证 — 板块连续3天涨停>=3家, 取板块内回调/强势股"""
import sqlite3, numpy as np
from collections import defaultdict

H=r"file:D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db?mode=ro"
M=r"file:D:\MarketData\market.db?mode=ro"

m=sqlite3.connect(M,uri=True)
ss=defaultdict(list)
for code,sid in m.execute("SELECT code,sector_id FROM stock_sector"):
    ss[code].append(sid)
m.close()
print(f"映射股数 {len(ss)}")

h=sqlite3.connect(H,uri=True)
alld=sorted(d for d, in h.execute("SELECT DISTINCT date FROM kline_daily_qfq WHERE code='sh000001'"))
dpos={d:i for i,d in enumerate(alld)}; ND=len(alld)
idxc={d:c for d,c in h.execute("SELECT date,close FROM kline_daily_qfq WHERE code='sh000001'")}
def iret(d,N):
    j=dpos.get(d)
    if j is None or j+N>=ND: return None
    return idxc[alld[j+N]]/idxc[alld[j]]-1

# ---- 第一遍: 涨停计数 ----
lu_cnt=defaultdict(int)
cur=h.execute("SELECT code,date,close FROM kline_daily_qfq WHERE code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]' ORDER BY code,date")
prev=None; ds=[]; cls=[]
def p1(code,ds,cls):
    c=np.array(cls,float); n=len(c)
    if n<10 or np.any(c<=0): return
    thr=0.195 if code[:3] in ('300','688') else 0.098
    pct=c[1:]/c[:-1]-1
    for k in (np.where(pct>=thr)[0]+1):
        if ds[k] not in dpos: continue      # 限定在与指数同日期间
        for sid in ss.get(code,()):
            lu_cnt[(ds[k],sid)]+=1
for code,d,c in cur:
    if code!=prev:
        if cls: p1(prev,ds,cls)
        ds=[];cls=[];prev=code
    ds.append(d);cls.append(c)
if cls: p1(prev,ds,cls)
print(f"涨停(日,板块)条目 {len(lu_cnt)}")

bysec=defaultdict(dict)
for (d,sid),cnt in lu_cnt.items():
    bysec[sid][dpos[d]]=cnt
hot=set()
for sid,dd in bysec.items():
    for i in range(ND-2):
        if dd.get(i,0)>=3 and dd.get(i+1,0)>=3 and dd.get(i+2,0)>=3:
            hot.add((alld[i+2],sid))
hot_dates=set(d for d,_ in hot)
print(f"热点(日期,板块) {len(hot)}  涉及日期 {len(hot_dates)}")

# ---- 第二遍: 收集热点板块成员 ----
allc={}
pool=defaultdict(list)   # (date,sid) -> [(code, i, ret5)]
cur=h.execute("SELECT code,date,close FROM kline_daily_qfq WHERE code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]' ORDER BY code,date")
prev=None; ds=[]; cls=[]
def p2(code,ds,cls):
    c=np.array(cls,float); allc[code]=c; n=len(c)
    if n<10: return
    thr=0.195 if code[:3] in ('300','688') else 0.098
    sids=ss.get(code,())
    if not sids: return
    for i,d in enumerate(ds):
        if d not in hot_dates: continue
        if i<6 or i+1>=n: continue
        if c[i]/c[i-1]-1>=thr: continue      # 排除当日涨停(买不进)
        r5=c[i]/c[i-5]-1
        for sid in sids:
            if (d,sid) in hot: pool[(d,sid)].append((code,i,r5))
for code,d,c in cur:
    if code!=prev:
        if cls: p2(prev,ds,cls)
        ds=[];cls=[];prev=code
    ds.append(d);cls.append(c)
if cls: p2(prev,ds,cls)
h.close()

# ---- 第三遍: 每热点取前3, 看后续 ----
NH=[1,3,5,10,20]
TOP={N:[0.0,0,0] for N in NH}
ALLM={N:[0.0,0,0] for N in NH}
sigs=0
for (d,sid),lst in pool.items():
    lst=sorted(lst,key=lambda x:-x[2])
    for code,i,r5 in lst[:3]:
        c=allc[code]; n=len(c)
        for N in NH:
            if i+1+N<n:
                ir=iret(d,N)
                if ir is not None:
                    e=c[i+1+N]/c[i+1]-1-ir
                    TOP[N][0]+=e; TOP[N][1]+=1; TOP[N][2]+=(e>0)
        sigs+=1
    for code,i,r5 in lst:      # 板块全体(非涨停)对照
        c=allc[code]; n=len(c)
        for N in NH:
            if i+1+N<n:
                ir=iret(d,N)
                if ir is not None:
                    e=c[i+1+N]/c[i+1]-1-ir
                    ALLM[N][0]+=e; ALLM[N][1]+=1; ALLM[N][2]+=(e>0)

def pr(name,t):
    s=f"{name:<26}"
    for N in NH:
        dd=t[N]; s+= f"{'—':>13}" if dd[1]<80 else f"{dd[0]/dd[1]*100:+5.1f}%/{dd[2]/dd[1]*100:3.0f}%"
    print(s)
print(f"\n信号数(板块×日) {len(pool)}, 前3选股样本 {sigs}")
print(f"{'策略':<26}"+"".join(f"{'N='+str(N):>13}" for N in NH))
print("-"*92)
pr("热点板块 前3(非涨停)买", TOP)
pr("热点板块 全体(非涨停)买", ALLM)
print("-"*92)
print("热点=某板块连续3个交易日, 每日涨停家数>=3; 买入=次日收盘价持有N日; 超额=减同期上证")
