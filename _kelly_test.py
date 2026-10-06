# -*- coding: utf-8 -*-
"""数学化 — 状态→(凯利仓位, 最优持有期) 的最大化期望"""
import sqlite3, numpy as np
from numpy.lib.stride_tricks import sliding_window_view

H = r"file:D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db?mode=ro"
h=sqlite3.connect(H,uri=True)
rows=h.execute("SELECT date,high,low,close FROM kline_daily_qfq WHERE code='sh000001' ORDER BY date").fetchall()
dd=[r[0] for r in rows]; hh=np.array([r[1] for r in rows],float)
ll=np.array([r[2] for r in rows],float); cc=np.array([r[3] for r in rows],float)
rmax=sliding_window_view(hh,250).max(axis=1); rmin=sliding_window_view(ll,250).min(axis=1)
mk={dd[i]:(cc[i]-rmin[i-249])/(rmax[i-249]-rmin[i-249]+1e-9)*100 for i in range(250,len(cc))}

HZ=[20,60,120]
# 每格每H: pos_sum,pos_cnt,neg_sum,neg_cnt
S={}
def cell(k,j): return S.setdefault((k,j),[0.0,0,0.0,0])
# 黄金格多H
GOLD=[5,10,20,40,60,90,120,180,250]
SG={j:[0.0,0,0.0,0] for j in GOLD}

def flush(dates,buf):
    a=np.array(buf,float); H2,L2,C2,V2=a[:,0],a[:,1],a[:,2],a[:,3]
    if len(C2)<520 or np.any(C2<=0): return
    n=len(C2)
    rmax=sliding_window_view(H2,250).max(axis=1); rmin=sliding_window_view(L2,250).min(axis=1)
    vma=sliding_window_view(V2,21).mean(axis=1)
    i0,i1=250,n-251
    if i1<=i0: return
    I=np.arange(i0,i1)
    pos=(C2[I]-rmin[I-249])/(rmax[I-249]-rmin[I-249]+1e-9)*100
    vr=V2[I]/(vma[I-1]+1e-9)
    lvc=np.where(pos<30,0,np.where(pos<70,1,2))
    vc=np.where(vr<0.7,0,np.where(vr<=1.5,1,2))
    for k,i in enumerate(I):
        m=mk.get(dates[i])
        if m is None: continue
        mc=0 if m<30 else (1 if m<70 else 2)
        key=mc*9+lvc[k]*3+vc[k]
        for j,Hh in enumerate(HZ):
            r=C2[i+Hh]/C2[i]-1
            c=cell(key,j)
            c[0 if r>0 else 2]+=r; c[1 if r>0 else 3]+=1
        if mc==0 and lvc[k]==0 and vc[k]==0:      # 黄金格
            for Hh in GOLD:
                r=C2[i+Hh]/C2[i]-1
                g=SG[Hh]; g[0 if r>0 else 2]+=r; g[1 if r>0 else 3]+=1

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

def stats(c):
    ps,pc,ns,nc=c
    n=pc+nc
    if n<50 or pc==0 or nc==0: return None
    p=pc/n; aw=ps/pc; al=abs(ns/nc); b=aw/al
    kelly=p-(1-p)/b
    E=(ps+ns)/n
    return n,p,b,kelly,E

Lv=["低","中","高"]
print("凯利仓位表 (持有120日, 绝对收益)  f*=(p·b−q)/b")
print("="*88)
print(f"{'个股\\大盘':<6}{'大盘低':>27}{'大盘中':>27}{'大盘高':>27}")
for lv in range(3):
    cells=[]
    for mc in range(3):
        out=[]
        for vc in range(3):
            st=stats(cell(mc*9+lv*3+vc,2))
            if st: out.append(st)
        if not out: cells.append(f"{'—':>27}"); continue
        n=sum(x[0] for x in out); k=np.mean([x[3] for x in out]); p=np.mean([x[1] for x in out]); E=np.mean([x[4] for x in out])
        cells.append(f"f*{k*100:4.0f}% p{p*100:3.0f}% E{E*100:+5.1f}%")
    print(f"{Lv[lv]}位{'':<2}{cells[0]:>27}{cells[1]:>27}{cells[2]:>27}")
print("="*88)
print("\n黄金格(大盘低+个股低+缩量) 最优持有期:")
print(f"{'持有期':>6}{'样本':>10}{'胜率':>8}{'盈亏比b':>9}{'期望':>9}{'凯利f*':>9}")
for Hh in GOLD:
    st=stats(SG[Hh])
    if st: print(f"{Hh:>6}{st[0]:>10,}{st[1]*100:>7.0f}%{st[2]:>9.2f}{st[4]*100:>+8.1f}%{st[3]*100:>+8.0f}%")
