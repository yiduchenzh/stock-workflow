# -*- coding: utf-8 -*-
"""合力黄金格 — 大盘低×个股低×缩量 : 历史实证 + 当前清单"""
import sqlite3, numpy as np
from numpy.lib.stride_tricks import sliding_window_view

H = r"file:D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db?mode=ro"
h=sqlite3.connect(H,uri=True)

rows=h.execute("SELECT date,high,low,close FROM kline_daily_qfq WHERE code='sh000001' ORDER BY date").fetchall()
dd=[r[0] for r in rows]; hh=np.array([r[1] for r in rows],float)
ll=np.array([r[2] for r in rows],float); cc=np.array([r[3] for r in rows],float)
rmax=sliding_window_view(hh,250).max(axis=1); rmin=sliding_window_view(ll,250).min(axis=1)
mk={dd[i]:(cc[i]-rmin[i-249])/(rmax[i-249]-rmin[i-249]+1e-9)*100 for i in range(250,len(cc))}
print(f"大盘位置 {len(mk)} 天, 最新 {dd[-1]} 分位 {mk[dd[-1]]:.1f}%")

VL=["缩量<0.7","正常","放量>1.5"]
cnt=np.zeros(3); exc=np.zeros(3); winr=np.zeros(3); mae=np.zeros(3)
cur_list=[]

def flush(code,dates,buf):
    a=np.array(buf,float); H2,L2,C2,V2=a[:,0],a[:,1],a[:,2],a[:,3]
    if len(C2)<270 or np.any(C2<=0): return
    n=len(C2); rmax=sliding_window_view(H2,250).max(axis=1); rmin=sliding_window_view(L2,250).min(axis=1)
    vma=sliding_window_view(V2,21).mean(axis=1); fmin=sliding_window_view(C2,121).min(axis=1)
    # 当前状态
    pos_now=(C2[-1]-rmin[n-250])/(rmax[n-250]-rmin[n-250]+1e-9)*100
    vr_now=V2[-1]/(vma[n-21]+1e-9)
    if pos_now<30 and vr_now<0.7 and dates[-1]>='2026-09-01':
        cur_list.append((code,round(pos_now,1),round(vr_now,2),round(C2[-1],2)))
    i0,i1=250,n-121
    if i1<=i0: return
    I=np.arange(i0,i1)
    pos=(C2[I]-rmin[I-249])/(rmax[I-249]-rmin[I-249]+1e-9)*100
    vr=V2[I]/(vma[I-1]+1e-9)
    r120=C2[I+120]/C2[I]-1; base=r120.mean(); e=r120-base
    for k,i in enumerate(I):
        m=mk.get(dates[i])
        if m is None or m>=30: continue      # 仅大盘低位
        if pos[k]>=30: continue              # 仅个股低位
        vi=0 if vr[k]<0.7 else (1 if vr[k]<=1.5 else 2)
        cnt[vi]+=1; exc[vi]+=e[k]; winr[vi]+= (1.0 if r120[k]>0 else 0.0)
        mae[vi]+= fmin[i]/C2[i]-1

cur=h.execute("SELECT code,date,high,low,close,volume FROM kline_daily_qfq "
              "WHERE code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]' ORDER BY code,date")
prev=None; dates=[]; buf=[]
for code,d,hi,lo,cl,vo in cur:
    if code!=prev:
        if buf: flush(prev,dates,buf)
        dates=[]; buf=[]; prev=code
    dates.append(d); buf.append((hi,lo,cl,float(vo or 0)))
if buf: flush(prev,dates,buf)
h.close()

print("\n【历史实证】大盘低位(分位<30%) + 个股低位(分位<30%) 下, 按量比分组 (后120日)")
print("="*70)
for vi in range(3):
    n=int(cnt[vi])
    if n<50: print(f"  {VL[vi]:<10} 样本不足"); continue
    print(f"  {VL[vi]:<10} 超{exc[vi]/n*100:+5.1f}%  胜{winr[vi]/n*100:3.0f}%  浮亏{mae[vi]/n*100:5.1f}%  ({n:,})")
print("="*70)
print(f"\n【当前清单 {dd[-1]}】大盘低位, 个股低位+缩量的股票 (共{len(cur_list)}只, 列前30):")
cur_list.sort(key=lambda x:x[1])
for c,p,v,px in cur_list[:30]:
    print(f"  {c}  位置分位{p:5.1f}%  量比{v:4.2f}  现价{px}")
