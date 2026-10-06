# -*- coding: utf-8 -*-
"""合力检验 — 大盘位置(环境) 是否改变个股'起点格'的表现"""
import sqlite3, numpy as np
from numpy.lib.stride_tricks import sliding_window_view

H = r"file:D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db?mode=ro"
h=sqlite3.connect(H,uri=True)

# 大盘位置序列
rows=h.execute("SELECT date,high,low,close FROM kline_daily_qfq WHERE code='sh000001' ORDER BY date").fetchall()
dd=[r[0] for r in rows]; hh=np.array([r[1] for r in rows],float)
ll=np.array([r[2] for r in rows],float); cc=np.array([r[3] for r in rows],float)
rmax=sliding_window_view(hh,250).max(axis=1); rmin=sliding_window_view(ll,250).min(axis=1)
mk={}
for i in range(250,len(cc)):
    mk[dd[i]]=(cc[i]-rmin[i-249])/(rmax[i-249]-rmin[i-249]+1e-9)*100
print(f"大盘位置序列 {len(mk)} 天 ({min(mk)} ~ {max(mk)})")

LVl=["低","中","高"]; ML=["大盘低","大盘中","大盘高"]
cnt=np.zeros(9); exc=np.zeros(9); winr=np.zeros(9); mae=np.zeros(9)

def flush(dates,buf):
    if len(buf)<380: return
    a=np.array(buf,float); H2,L2,C2=a[:,0],a[:,1],a[:,2]
    if np.any(C2<=0): return
    n=len(C2)
    rmax=sliding_window_view(H2,250).max(axis=1); rmin=sliding_window_view(L2,250).min(axis=1)
    fmin=sliding_window_view(C2,121).min(axis=1)
    i0,i1=250,n-121
    if i1<=i0: return
    I=np.arange(i0,i1)
    pos=(C2[I]-rmin[I-249])/(rmax[I-249]-rmin[I-249]+1e-9)*100
    r120=C2[I+120]/C2[I]-1; base=r120.mean(); e=r120-base
    for k,i in enumerate(I):
        m=mk.get(dates[i])
        if m is None: continue
        mc=0 if m<30 else (1 if m<70 else 2)
        lvc=0 if pos[k]<30 else (1 if pos[k]<70 else 2)
        key=lvc*3+mc
        cnt[key]+=1; exc[key]+=e[k]; winr[key]+= (1.0 if r120[k]>0 else 0.0)
        mae[key]+= fmin[i]/C2[i]-1

cur=h.execute("SELECT code,date,high,low,close FROM kline_daily_qfq "
              "WHERE code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]' ORDER BY code,date")
prev=None; dates=[]; buf=[]
for code,d,hi,lo,cl in cur:
    if code!=prev:
        if buf: flush(dates,buf)
        dates=[]; buf=[]; prev=code
    dates.append(d); buf.append((hi,lo,cl))
if buf: flush(dates,buf)
h.close()

print(f"\n匹配 {int(cnt.sum()):,} 时点")
print("="*92)
print(f"{'个股位置\\大盘环境':<14}{'大盘低':>25}{'大盘中':>25}{'大盘高':>25}")
print("-"*92)
for ai,a in enumerate(LVl):
    cells=[]
    for mi in range(3):
        k=ai*3+mi; n=int(cnt[k])
        cells.append(f"{'样本不足':>25}" if n<100 else
                     f"超{exc[k]/n*100:+5.1f}% 胜{winr[k]/n*100:3.0f}% 亏{mae[k]/n*100:5.1f}%")
    print(f"{a}位{'':<8}{cells[0]:>25}{cells[1]:>25}{cells[2]:>25}")
print("="*92)
print("行内三列差异大 → 大盘位置有增量(合力有效); 差异小 → 无效")
