# -*- coding: utf-8 -*-
"""稳健性审计 — 黄金格样本的'时期集中度' (是否只是某一段行情的运气)"""
import sqlite3, numpy as np
from collections import defaultdict
from numpy.lib.stride_tricks import sliding_window_view

H = r"file:D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db?mode=ro"
h=sqlite3.connect(H,uri=True)
rows=h.execute("SELECT date,high,low,close FROM kline_daily_qfq WHERE code='sh000001' ORDER BY date").fetchall()
dd=[r[0] for r in rows]; hh=np.array([r[1] for r in rows],float)
ll=np.array([r[2] for r in rows],float); cc=np.array([r[3] for r in rows],float)
rmax=sliding_window_view(hh,250).max(axis=1); rmin=sliding_window_view(ll,250).min(axis=1)
mk={dd[i]:(cc[i]-rmin[i-249])/(rmax[i-249]-rmin[i-249]+1e-9)*100 for i in range(250,len(cc))}

by_q=defaultdict(lambda:[0,0.0,0])      # 季度 -> [n, sum_r120, wins]
all_q=defaultdict(lambda:[0,0.0,0])

def flush(dates,buf):
    a=np.array(buf,float); H2,L2,C2,V2=a[:,0],a[:,1],a[:,2],a[:,3]
    if len(C2)<400 or np.any(C2<=0): return
    n=len(C2)
    rmax=sliding_window_view(H2,250).max(axis=1); rmin=sliding_window_view(L2,250).min(axis=1)
    vma=sliding_window_view(V2,21).mean(axis=1)
    i0,i1=250,n-121
    if i1<=i0: return
    I=np.arange(i0,i1)
    pos=(C2[I]-rmin[I-249])/(rmax[I-249]-rmin[I-249]+1e-9)*100
    vr=V2[I]/(vma[I-1]+1e-9)
    for k,i in enumerate(I):
        m=mk.get(dates[i])
        if m is None: continue
        r120=C2[i+120]/C2[i]-1
        q=dates[i][:4]+"Q"+str((int(dates[i][5:7])-1)//3+1)
        a2=all_q[q]; a2[0]+=1; a2[1]+=r120; a2[2]+= (1 if r120>0 else 0)
        if m<30 and pos[k]<30 and vr[k]<0.7:
            b=by_q[q]; b[0]+=1; b[1]+=r120; b[2]+= (1 if r120>0 else 0)

cur=h.execute("SELECT code,date,high,low,close,volume FROM kline_daily_qfq "
              "WHERE code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]' ORDER BY code,date")
prev=None; dates=[]; buf=[]
for code,d,hi,lo,cl,vo in cur:
    if code!=prev:
        if buf: flush(dates,buf)
        dates=[]; buf=[]; prev=code
    dates.append(d); buf.append((hi,lo,cl,float(vo or 0)))
if buf: flush(dates,buf)
h.close()

print("黄金格(大低+个低+缩量) 的'时期集中度' — 后120日 (只列有样本的季度)")
print("="*78)
print(f"{'季度(入场)':<12}{'黄金格样本':>12}{'黄金格均值':>12}{'黄金格胜率':>12}{'全市场均值':>12}{'超额':>10}")
for q in sorted(by_q):
    b=by_q[q]; a2=all_q[q]
    gm=b[1]/b[0]; am=a2[1]/a2[0]
    print(f"{q:<12}{b[0]:>12,}{gm*100:>+11.1f}%{b[2]/b[0]*100:>11.0f}%{am*100:>+11.1f}%{(gm-am)*100:>+9.1f}%")
tot=sum(b[0] for b in by_q.values())
print("="*78)
print(f"黄金格总样本 {tot:,} ; 其中最大季度占比 {max(b[0] for b in by_q.values())/tot*100:.0f}%")
