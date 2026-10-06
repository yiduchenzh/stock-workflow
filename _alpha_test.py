# -*- coding: utf-8 -*-
"""真alpha — 市场调整超额(个股−同期上证) + 最优持有期 + 凯利"""
import sqlite3, numpy as np
from numpy.lib.stride_tricks import sliding_window_view

H = r"file:D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db?mode=ro"
h=sqlite3.connect(H,uri=True)
rows=h.execute("SELECT date,high,low,close FROM kline_daily_qfq WHERE code='sh000001' ORDER BY date").fetchall()
dd=[r[0] for r in rows]; hh=np.array([r[1] for r in rows],float)
ll=np.array([r[2] for r in rows],float); cc=np.array([r[3] for r in rows],float)
pos_idx=np.arange(len(cc))
rmax=sliding_window_view(hh,250).max(axis=1); rmin=sliding_window_view(ll,250).min(axis=1)
mk={}; didx={}
for i in range(250,len(cc)):
    mk[dd[i]]=(cc[i]-rmin[i-249])/(rmax[i-249]-rmin[i-249]+1e-9)*100
    didx[dd[i]]=i
def idx_ret(date,Hh):
    j=didx.get(date)
    if j is None or j+Hh>=len(cc): return None
    return cc[j+Hh]/cc[j]-1

HZ=[5,10,20,40,60,90,120,180]
G={Hh:[0.0,0,0.0,0] for Hh in HZ}          # 黄金格 市场调整超额
MM={Hh:[0.0,0,0.0,0] for Hh in HZ}         # 大盘高+个股低 对照

def flush(dates,buf):
    a=np.array(buf,float); H2,L2,C2,V2=a[:,0],a[:,1],a[:,2],a[:,3]
    if len(C2)<520 or np.any(C2<=0): return
    n=len(C2)
    rmax=sliding_window_view(H2,250).max(axis=1); rmin=sliding_window_view(L2,250).min(axis=1)
    vma=sliding_window_view(V2,21).mean(axis=1)
    i0,i1=250,n-181
    if i1<=i0: return
    I=np.arange(i0,i1)
    pos=(C2[I]-rmin[I-249])/(rmax[I-249]-rmin[I-249]+1e-9)*100
    vr=V2[I]/(vma[I-1]+1e-9)
    for k,i in enumerate(I):
        m=mk.get(dates[i])
        if m is None: continue
        gold=(m<30 and pos[k]<30 and vr[k]<0.7)
        bad =(m>70 and pos[k]<30)
        if not(gold or bad): continue
        for Hh in HZ:
            ir=idx_ret(dates[i],Hh)
            if ir is None: continue
            e=C2[i+Hh]/C2[i]-1-ir          # 市场调整超额
            t=G if gold else MM
            d=t[Hh]; d[0 if e>0 else 2]+=e; d[1 if e>0 else 3]+=1

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

def show(name,t):
    print(f"\n{name}  (市场调整超额 = 个股 − 同期上证)")
    print(f"{'持有期':>6}{'样本':>10}{'超额胜率':>10}{'平均超额':>10}{'盈亏比b':>9}{'凯利f*':>9}")
    for Hh in HZ:
        ps,pc,ns,nc=t[Hh]; n=pc+nc
        if n<50 or pc==0 or nc==0: print(f"{Hh:>6}   样本不足"); continue
        p=pc/n; b=(ps/pc)/abs(ns/nc); f=p-(1-p)/b; E=(ps+ns)/n
        print(f"{Hh:>6}{n:>10,}{p*100:>9.0f}%{E*100:>+9.1f}%{b:>9.2f}{f*100:>+8.0f}%")
show("黄金格(大盘低+个股低+缩量)", G)
show("对照(大盘高+个股低)", MM)
