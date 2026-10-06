# -*- coding: utf-8 -*-
"""多级别共振 — 30min/日/周 的笔段方向传导"""
import sqlite3, sys, numpy as np
import _chan_grow as cg

H = r"file:D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db?mode=ro"

def weekly(dates,o,h,l,c):
    """按周聚合"""
    W=[]; cur=None; co=ch=cl=cc=None
    for i,d in enumerate(dates):
        key=d[:10]
        import datetime
        try: y,m,dd=map(int,key.split('-')); wk=datetime.date(y,m,dd).isocalendar()[1]
        except: wk=0
        k=(d[:7],wk)
        if cur is None: cur=k; co,ch,cl,cc=o[i],h[i],l[i],c[i]
        elif k==cur: ch=max(ch,h[i]); cl=min(cl,l[i]); cc=c[i]
        else: W.append((co,ch,cl,cc)); cur=k; co,ch,cl,cc=o[i],h[i],l[i],c[i]
    if co is not None: W.append((co,ch,cl,cc))
    return np.array([w[0] for w in W]),np.array([w[1] for w in W]),np.array([w[2] for w in W]),np.array([w[3] for w in W])

def level_state(dates,h,l,name):
    mh,ml,src=cg.merge_k(h,l)
    pts=cg.fractals(mh,ml,src)
    bis=cg.build_bis(pts)
    segs=cg.build_segs(bis)
    lb=bis[-1]['dir'] if bis else '-'
    ls=segs[-1]['dir'] if segs else '-'
    seg_desc=""
    if segs:
        s=segs[-1]; seg_desc=f"{dates[s['s']][:10]} {s['sp']:.2f}→{dates[s['e']][:10]} {s['ep']:.2f}"
    return name,len(bis),len(segs),lb,ls,seg_desc

code=sys.argv[1] if len(sys.argv)>1 else "300319"
nm=sys.argv[2] if len(sys.argv)>2 else ""
con=sqlite3.connect(H,uri=True)
# 30min
rows=con.execute("SELECT date,open,high,low,close FROM kline_30min WHERE code=? ORDER BY date",(code,)).fetchall()[-3000:]
d30=[r[0] for r in rows]; a30=np.array([r[1:] for r in rows],float)
# daily
rows=con.execute("SELECT date,open,high,low,close FROM kline_daily_qfq WHERE code=? ORDER BY date",(code,)).fetchall()
dD=[r[0] for r in rows]; aD=np.array([r[1:] for r in rows],float)
con.close()
wo,wh,wl,wc=weekly(dD,aD[:,0],aD[:,1],aD[:,2],aD[:,3])

res=[]
res.append(level_state(d30,a30[:,1],a30[:,2],"30min"))
res.append(level_state(dD,aD[:,1],aD[:,2],"日线 "))
res.append(level_state([str(i) for i in range(len(wc))],wh,wl,"周线 "))

print(f"【{code} {nm}】多级别共振")
print("="*80)
print(f"{'级别':<8}{'笔数':>6}{'段数':>6}{'最后笔':>8}{'最后段':>8}   最后一段")
for name,nb,ns,lb,ls,sd in res:
    print(f"{name:<8}{nb:>6}{ns:>6}{lb:>8}{ls:>8}   {sd}")
print("="*80)
print("小周期一段 ≈ 大周期一笔 → 数值上体现为'小级别段数 > 大级别笔数'")
