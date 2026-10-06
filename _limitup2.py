# -*- coding: utf-8 -*-
"""涨停后策略对比 — 追高(次日买) vs 回调缩量低吸(等1买)"""
import sqlite3, numpy as np

H = r"file:D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db?mode=ro"
h=sqlite3.connect(H,uri=True)
rows=h.execute("SELECT date,close FROM kline_daily_qfq WHERE code='sh000001' ORDER BY date").fetchall()
dd=[r[0] for r in rows]; cc0=np.array([r[1] for r in rows],float); didx={d:i for i,d in enumerate(dd)}
def iret(d,N):
    j=didx.get(d)
    if j is None or j+N>=len(cc0): return None
    return cc0[j+N]/cc0[j]-1

NH=[1,3,5,10,20]
A={N:[0.0,0,0] for N in NH}     # 追高: 涨停次日开盘买
B={N:[0.0,0,0] for N in NH}     # 低吸: 涨停后回调+缩量 买
C={N:[0.0,0,0] for N in NH}     # 低吸+大盘低
GAP={N:[0.0,0] for N in NH}     # 统计: 回调幅度

def flush(code,dates,o_,c_,v_):
    n=len(c_)
    if n<130: return
    thr = 0.195 if code[:3] in ('300','688') else 0.098
    pct=c_[1:]/c_[:-1]-1
    lu=np.where(pct>=thr)[0]+1
    cs=np.cumsum(v_)
    vr=np.full(n,np.nan); vr[20:]=v_[20:]/((cs[20:]-cs[:-20])/20+1e-9)
    for i in lu:
        if i+2>=n: continue
        # A 追高: 次日开盘
        if o_[i+1]>0:
            for N in NH:
                if i+1+N<n:
                    ir=iret(dates[i+1],N)
                    if ir is not None:
                        e=c_[i+1+N]/o_[i+1]-1-ir; A[N][0]+=e; A[N][1]+=1; A[N][2]+=(e>0)
        # B 低吸: 之后20日内 缩量(量比<0.7) 且 回调(收<涨停收盘)
        for j in range(i+2, min(i+21,n-1)):
            if np.isnan(vr[j]): continue
            if vr[j]<0.7 and c_[j]<c_[i]:
                for N in NH:
                    if j+1+N<n:
                        ir=iret(dates[j+1],N)
                        if ir is not None:
                            e=c_[j+1+N]/o_[j+1]-1-ir
                            B[N][0]+=e; B[N][1]+=1; B[N][2]+=(e>0)
                            if j-i<=20: GAP[N][0]+= (c_[j]/c_[i]-1); GAP[N][1]+=0
                break
    return

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
    s=f"{name:<24}"
    for N in NH:
        d=t[N]; s+= f"{'—':>13}" if d[1]<80 else f"{d[0]/d[1]*100:+5.1f}%/{d[2]/d[1]*100:3.0f}%"
    print(s)
print("涨停次日开盘买(追高) vs 涨停后回调缩量买(低吸)  — 市场调整超额/胜率")
print(f"{'策略':<24}"+"".join(f"{'N='+str(N):>13}" for N in NH))
print("-"*82)
pr("A 追高(次日买)", A)
pr("B 低吸(回调+缩量)", B)
print("-"*82)
print("超额=个股−同期上证。低吸=涨停后20日内首次'量比<0.7且收<涨停收盘'的次日开盘买入")
