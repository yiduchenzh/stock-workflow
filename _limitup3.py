# -*- coding: utf-8 -*-
"""三路径同口径对比 — 追高 / 涨停回调低吸 / 全市场低位缩量"""
import sqlite3, numpy as np
from numpy.lib.stride_tricks import sliding_window_view

H = r"file:D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db?mode=ro"
h=sqlite3.connect(H,uri=True)
rows=h.execute("SELECT date,close FROM kline_daily_qfq WHERE code='sh000001' ORDER BY date").fetchall()
dd=[r[0] for r in rows]; cc0=np.array([r[1] for r in rows],float); didx={d:i for i,d in enumerate(dd)}
def iret(d,N):
    j=didx.get(d)
    if j is None or j+N>=len(cc0): return None
    return cc0[j+N]/cc0[j]-1

NH=[1,3,5,10,20]
A={N:[0.0,0,0] for N in NH}
B={N:[0.0,0,0] for N in NH}
C={N:[0.0,0,0] for N in NH}

def flush(code,dates,o_,c_,v_):
    n=len(c_)
    if n<300: return
    thr = 0.195 if code[:3] in ('300','688') else 0.098
    pct=c_[1:]/c_[:-1]-1
    lu=np.where(pct>=thr)[0]+1
    cs=np.cumsum(v_); vr=np.full(n,np.nan); vr[20:]=v_[20:]/((cs[20:]-cs[:-20])/20+1e-9)
    rmax=sliding_window_view(c_,60).max(axis=1); rmin=sliding_window_view(c_,60).min(axis=1)
    def rec(t,date_i,entry_idx,N,entry_px):
        for N2 in NH:
            if entry_idx+N2<n:
                ir=iret(date_i,N2)
                if ir is not None:
                    e=c_[entry_idx+N2]/entry_px-1-ir
                    t[N2][0]+=e; t[N2][1]+=1; t[N2][2]+=(e>0)
    # A 追高
    for i in lu:
        if i+1<n and o_[i+1]>0: rec(A,dates[i+1],i+1,None,o_[i+1])
    # B 涨停后回调缩量
    for i in lu:
        for j in range(i+2,min(i+21,n-1)):
            if not np.isnan(vr[j]) and vr[j]<0.7 and c_[j]<c_[i] and o_[j+1]>0:
                rec(B,dates[j+1],j+1,None,o_[j+1]); break
    # C 全市场 低位(60日分位<30)+缩量
    for i in range(61,n-1):
        if np.isnan(vr[i]) or vr[i]>=0.7: continue
        pos=(c_[i]-rmin[i-60])/(rmax[i-60]-rmin[i-60]+1e-9)*100
        if pos<30 and o_[i+1]>0:
            rec(C,dates[i+1],i+1,None,o_[i+1])

cur=h.execute("SELECT code,date,open,close,volume FROM kline_daily_qfq "
              "WHERE code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]' ORDER BY code,date")
prev=None; dates=[]; oo=[]; cl=[]; vv=[]
for code,d,op,c,v in cur:
    if code!=prev:
        if cl: flush(prev,dates,np.array(oo),np.array(cl),np.array(vv))
        dates=[]; oo=[]; cl=[]; vv=[]; prev=code
    dates.append(d); oo.append(float(op or 0)); cl.append(float(c)); vv.append(float(v or 0))
if cl: flush(prev,dates,np.array(oo),np.array(cl),np.array(vv))
h.close()

def pr(name,t):
    s=f"{name:<26}"
    for N in NH:
        d=t[N]; s+= f"{'—':>13}" if d[1]<80 else f"{d[0]/d[1]*100:+5.1f}%/{d[2]/d[1]*100:3.0f}%"
    print(s)
print("三路径同口径对比 (市场调整超额/超额胜率)")
print(f"{'策略':<26}"+"".join(f"{'N='+str(N):>13}" for N in NH))
print("-"*92)
pr("A 追涨停(次日买)", A)
pr("B 涨停后回调缩量买", B)
pr("C 全市场低位+缩量买", C)
print("-"*92)
print("C 用60日位置分位<30%(近250日口径见 reverse-position-analysis 技能)")
