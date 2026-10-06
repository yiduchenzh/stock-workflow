# -*- coding: utf-8 -*-
"""维度增量检验 — 价量关系(量比) 是否在'位置'之上提供增量 alpha"""
import sqlite3, numpy as np
from numpy.lib.stride_tricks import sliding_window_view

H = r"file:D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db?mode=ro"
LVl=["低","中","高"]; VL=["缩量<0.7","正常0.7-1.5","放量>1.5"]

cnt=np.zeros(9); exc=np.zeros(9); winr=np.zeros(9)

def flush(buf):
    if len(buf)<380: return
    a=np.array(buf,float); hh,ll,cc,vv=a[:,0],a[:,1],a[:,2],a[:,3]
    if np.any(cc<=0): return
    n=len(cc)
    rmax=sliding_window_view(hh,250).max(axis=1)
    rmin=sliding_window_view(ll,250).min(axis=1)
    vmax=sliding_window_view(vv,21).max(axis=1)  # to guard zeros
    vma=sliding_window_view(vv,21).mean(axis=1)  # index j -> mean(v[j..j+20])
    i0,i1=270,n-121
    if i1<=i0: return
    I=np.arange(i0,i1)
    pos=(cc[I]-rmin[I-249])/(rmax[I-249]-rmin[I-249]+1e-9)*100
    lvc=np.where(pos<30,0,np.where(pos<70,1,2))
    # 量比 = 当日量 / 前20日均量
    vr=vv[I]/(vma[I-1]+1e-9)
    vc=np.where(vr<0.7,0,np.where(vr<=1.5,1,2))
    r120=cc[I+120]/cc[I]-1
    base=r120.mean(); e=r120-base
    key=lvc*3+vc
    np.add.at(cnt,key,1); np.add.at(exc,key,e)
    np.add.at(winr,key,(r120>0).astype(float))

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

tot=cnt.sum()
print(f"样本 {int(tot):,} 时点 (全历史, 持有120日)")
print("="*88)
print(f"{'位置\\量比':<12}{'缩量':>25}{'正常':>25}{'放量':>25}")
print("-"*88)
for ai,a in enumerate(LVl):
    cells=[]
    for vi in range(3):
        k=ai*3+vi; n=int(cnt[k])
        cells.append(f"{'样本不足':>25}" if n<100 else
                     f"超{exc[k]/n*100:+5.1f}% 胜{winr[k]/n*100:3.0f}% ({n:>7,})")
    print(f"{a}位{'':<6}{cells[0]:>25}{cells[1]:>25}{cells[2]:>25}")
print("="*88)
print("超额 = 后120日收益 − 该股全历史基线。若同一位置行内三列差异小 → 量比无增量")
