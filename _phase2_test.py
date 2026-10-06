# -*- coding: utf-8 -*-
"""低位细分 — 量比 × 波动 组合, 精确定义'波段起点'"""
import sqlite3, numpy as np
from numpy.lib.stride_tricks import sliding_window_view

H = r"file:D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db?mode=ro"
VL=["缩量<0.7","正常","放量>1.5"]; SL=["收缩<0.85","正常","扩张>1.15"]

cnt=np.zeros(9); exc=np.zeros(9); winr=np.zeros(9); mae=np.zeros(9)

def flush(buf):
    if len(buf)<380: return
    a=np.array(buf,float); hh,ll,cc=a[:,0],a[:,1],a[:,2]
    if np.any(cc<=0): return
    n=len(cc); tr=hh-ll
    rmax=sliding_window_view(hh,250).max(axis=1)
    rmin=sliding_window_view(ll,250).min(axis=1)
    atr20=sliding_window_view(tr,20).mean(axis=1)
    atr60=sliding_window_view(tr,60).mean(axis=1)
    vma=sliding_window_view(a[:,3],21).mean(axis=1)
    fmin=sliding_window_view(cc,121).min(axis=1)
    i0,i1=270,n-121
    if i1<=i0: return
    I=np.arange(i0,i1)
    pos=(cc[I]-rmin[I-249])/(rmax[I-249]-rmin[I-249]+1e-9)*100
    low=pos<30
    vc_ratio=atr20[I-19]/(atr60[I-59]+1e-9)
    vr=a[:,3][I]/(vma[I-1]+1e-9)
    sc=np.where(vc_ratio<0.85,0,np.where(vc_ratio<=1.15,1,2))
    vc=np.where(vr<0.7,0,np.where(vr<=1.5,1,2))
    r120=cc[I+120]/cc[I]-1
    base=r120.mean(); e=r120-base
    key=vc*3+sc
    np.add.at(cnt,key,low.astype(float)); np.add.at(exc,key,np.where(low,e,0))
    np.add.at(winr,key,np.where(low,(r120>0).astype(float),0))
    np.add.at(mae,key,np.where(low,fmin[I]/cc[I]-1,0))

h=sqlite3.connect(H,uri=True)
cur=h.execute("SELECT code,high,low,close,volume FROM kline_daily_qfq "
              "WHERE code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]' ORDER BY code,date")
prev=None; buf=[]
for code,hi,lo,cl,vo in cur:
    if code!=prev:
        if buf: flush(buf)
        buf=[]; prev=code
    buf.append((hi,lo,cl,float(vo or 0)))
if buf: flush(buf)
h.close()

print("仅'低位(pos<30%)'样本 — 量比 × 波动 (持有120日)")
print("="*94)
print(f"{'量比\\波动':<12}{'收缩(蓄势)':>27}{'正常':>27}{'扩张':>27}")
print("-"*94)
for vi in range(3):
    cells=[]
    for si in range(3):
        k=vi*3+si; n=int(cnt[k])
        cells.append(f"{'样本不足':>27}" if n<100 else
                     f"超{exc[k]/n*100:+5.1f}% 胜{winr[k]/n*100:3.0f}% 亏{mae[k]/n*100:5.1f}%")
    print(f"{VL[vi]:<12}{cells[0]:>27}{cells[1]:>27}{cells[2]:>27}")
print("="*94)
