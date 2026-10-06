# -*- coding: utf-8 -*-
"""维度增量检验 — 大盘情绪 是否在'位置'之上提供增量 alpha"""
import sqlite3, numpy as np
from numpy.lib.stride_tricks import sliding_window_view

H = r"file:D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db?mode=ro"
LVl=["低","中","高"]; EL=["弱(<0.4)","中(0.4-0.6)","强(>0.6)"]

h=sqlite3.connect(H,uri=True)
emo={}
for d,adv,dec in h.execute("SELECT date,advance,decline FROM market_trend"):
    t=adv+dec
    emo[d]=adv/t if t else 0.5
print(f"情绪日期 {len(emo)} 天  ({min(emo)} ~ {max(emo)})")

cnt=np.zeros(9); exc=np.zeros(9); winr=np.zeros(9)

def flush(dates, buf):
    if len(buf)<380: return
    a=np.array(buf,float); hh,ll,cc=a[:,0],a[:,1],a[:,2]
    if np.any(cc<=0): return
    n=len(cc)
    rmax=sliding_window_view(hh,250).max(axis=1)
    rmin=sliding_window_view(ll,250).min(axis=1)
    i0,i1=250,n-121
    if i1<=i0: return
    I=np.arange(i0,i1)
    pos=(cc[I]-rmin[I-249])/(rmax[I-249]-rmin[I-249]+1e-9)*100
    lvc=np.where(pos<30,0,np.where(pos<70,1,2))
    r120=cc[I+120]/cc[I]-1
    base=r120.mean(); e=r120-base
    for k,i in enumerate(I):
        ds=dates[i]
        if ds not in emo: continue
        ev=emo[ds]
        ec=0 if ev<0.4 else (1 if ev<0.6 else 2)
        key=lvc[k]*3+ec
        cnt[key]+=1; exc[key]+=e[k]; winr[key]+= (1.0 if r120[k]>0 else 0.0)

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

tot=cnt.sum()
print(f"\n匹配样本 {int(tot):,} 个时点 (仅2023-04后, 有情绪的日期)")
print("="*84)
print(f"{'位置\\大盘情绪':<14}{'弱':>23}{'中':>23}{'强':>23}")
print("-"*84)
for ai,a in enumerate(LVl):
    cells=[]
    for ei in range(3):
        k=ai*3+ei; n=int(cnt[k])
        cells.append(f"{'样本不足':>23}" if n<100 else
                     f"超{exc[k]/n*100:+5.1f}% 胜{winr[k]/n*100:3.0f}% ({n:>7,})")
    print(f"{a}位{'':<8}{cells[0]:>23}{cells[1]:>23}{cells[2]:>23}")
print("="*84)
print("超额 = 后120日收益 − 该股全历史基线。若同一位置行内三列差异小 → 情绪无增量")
