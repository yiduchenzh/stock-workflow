# -*- coding: utf-8 -*-
"""阶段定位检验 — 波动状态(收缩/扩张) 是否区分'起点 vs 终点'"""
import sqlite3, numpy as np
from numpy.lib.stride_tricks import sliding_window_view

H = r"file:D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db?mode=ro"
LVl=["低","中","高"]; SL=["收缩<0.85(蓄势)","正常","扩张>1.15(派发/恐慌)"]

cnt=np.zeros(9); exc=np.zeros(9); winr=np.zeros(9)

def flush(buf):
    if len(buf)<380: return
    a=np.array(buf,float); hh,ll,cc=a[:,0],a[:,1],a[:,2]
    if np.any(cc<=0): return
    n=len(cc)
    tr=hh-ll
    rmax=sliding_window_view(hh,250).max(axis=1)
    rmin=sliding_window_view(ll,250).min(axis=1)
    atr20=sliding_window_view(tr,20).mean(axis=1)
    atr60=sliding_window_view(tr,60).mean(axis=1)
    i0,i1=270,n-121
    if i1<=i0: return
    I=np.arange(i0,i1)
    pos=(cc[I]-rmin[I-249])/(rmax[I-249]-rmin[I-249]+1e-9)*100
    lvc=np.where(pos<30,0,np.where(pos<70,1,2))
    vc_ratio=atr20[I-19]/(atr60[I-59]+1e-9)
    sc=np.where(vc_ratio<0.85,0,np.where(vc_ratio<=1.15,1,2))
    r120=cc[I+120]/cc[I]-1
    base=r120.mean(); e=r120-base
    key=lvc*3+sc
    np.add.at(cnt,key,1); np.add.at(exc,key,e)
    np.add.at(winr,key,(r120>0).astype(float))

h=sqlite3.connect(H,uri=True)
cur=h.execute("SELECT code,high,low,close FROM kline_daily_qfq "
              "WHERE code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]' ORDER BY code,date")
prev=None; buf=[]
for code,hi,lo,cl in cur:
    if code!=prev:
        if buf: flush(buf)
        buf=[]; prev=code
    buf.append((hi,lo,cl))
if buf: flush(buf)
h.close()

tot=cnt.sum()
print(f"样本 {int(tot):,} 时点 (全历史, 持有120日)")
print("="*92)
print(f"{'位置\\波动':<10}{'收缩(蓄势)':>27}{'正常':>27}{'扩张(派发)':>27}")
print("-"*92)
for ai,a in enumerate(LVl):
    cells=[]
    for si in range(3):
        k=ai*3+si; n=int(cnt[k])
        cells.append(f"{'样本不足':>27}" if n<100 else
                     f"超{exc[k]/n*100:+5.1f}% 胜{winr[k]/n*100:3.0f}% ({n:>7,})")
    print(f"{a}位{'':<4}{cells[0]:>27}{cells[1]:>27}{cells[2]:>27}")
print("="*92)
print("波动系数=ATR20/ATR60。<0.85=波动收缩(蓄势), >1.15=扩张(派发/恐慌)")
