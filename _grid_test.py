# -*- coding: utf-8 -*-
"""九宫格实证 v2 — 位置×结构 × 持有期(20/60/120日) 超额 + 平均最大浮亏"""
import sqlite3, numpy as np
from numpy.lib.stride_tricks import sliding_window_view

DB = r"file:D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db?mode=ro"
LV = ["低","中","高"]; ST = ["上升","区间","下降"]
HZ = [20, 60, 120]
KEY = lambda a,b: LV.index(a)*3 + ST.index(b)

cnt=[np.zeros(9) for _ in HZ]; exc=[np.zeros(9) for _ in HZ]
winr=[np.zeros(9) for _ in HZ]; mae=[np.zeros(9) for _ in HZ]

def flush(buf):
    if len(buf) < 380: return
    a=np.array(buf,float); h,l,c=a[:,0],a[:,1],a[:,2]
    if np.any(c<=0): return
    n=len(c); cs=np.cumsum(c)
    rmax=sliding_window_view(h,250).max(axis=1)
    rmin=sliding_window_view(l,250).min(axis=1)
    i0,i1=250,n-121
    if i1<=i0: return
    I=np.arange(i0,i1)
    pos=(c[I]-rmin[I-249])/(rmax[I-249]-rmin[I-249]+1e-9)*100
    m20=(cs[I]-cs[I-20])/20; m60=(cs[I]-cs[I-60])/60
    m120=(cs[I]-cs[I-120])/120; m250=(cs[I]-cs[I-250])/250
    up=(m20>m60)&(m60>m120)&(c[I]>m250); dn=(m20<m60)&(m60<m120)&(c[I]<m250)
    key=(np.where(pos<30,0,np.where(pos<70,1,2)))*3+np.where(up,0,np.where(dn,2,1))
    fmin=sliding_window_view(c,121).min(axis=1)
    for j,H in enumerate(HZ):
        r=c[I+H]/c[I]-1; e=r-r.mean()
        np.add.at(cnt[j],key,1); np.add.at(exc[j],key,e)
        np.add.at(winr[j],key,(r>0).astype(float))
        np.add.at(mae[j],key,fmin[I]/c[I]-1)

con=sqlite3.connect(DB,uri=True)
cur=con.execute("SELECT code,high,low,close FROM kline_daily_qfq "
                "WHERE code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]' ORDER BY code,date")
prev=None; buf=[]
for code,hi,lo,cl in cur:
    if code!=prev:
        if buf: flush(buf)
        buf=[]; prev=code
    buf.append((hi,lo,cl))
if buf: flush(buf)
con.close()

for j,H in enumerate(HZ):
    print("="*92)
    print(f"持有 {H} 日    (总样本 {int(cnt[j].sum()):,})")
    print(f"{'位置\\结构':<9}{'上升':>27}{'区间':>27}{'下降':>27}")
    print("-"*92)
    for ai,a in enumerate(LV):
        cells=[]
        for bi,b in enumerate(ST):
            k=KEY(a,b); n=int(cnt[j][k])
            if n<100: cells.append(f"{'样本不足':>27}"); continue
            cells.append(f"超{exc[j][k]/n*100:+5.1f}% 胜{winr[j][k]/n*100:3.0f}% 浮亏{mae[j][k]/n*100:+5.1f}%")
        print(f"{a}位{'':<4}{cells[0]:>27}{cells[1]:>27}{cells[2]:>27}")
print("="*92)
print("超=超额(后H日收益−该股基线) 胜=正收益比例 浮亏=窗口内平均最大回落")
