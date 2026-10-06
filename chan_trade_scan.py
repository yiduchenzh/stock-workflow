# -*- coding: utf-8 -*-
"""多周期缠论买卖点扫描引擎 v3
大盘环境 → 热点板块 → 低位股 → 日线/30min笔段 + MACD背离 + 均线拐头 → 信号
"""
import sqlite3, numpy as np
from collections import defaultdict

H = r"file:D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db?mode=ro"
M = r"file:D:\MarketData\market.db?mode=ro"

def ema(x,n):
    a=2.0/(n+1); o=np.empty(len(x)); o[0]=x[0]
    for i in range(1,len(x)): o[i]=a*x[i]+(1-a)*o[i-1]
    return o
def macd_dif(c): return ema(c,12)-ema(c,26)

def ma_turn(c,w):
    """+1 拐头向上, -1 拐头向下, 0 无"""
    if len(c)<w+2: return 0
    m=c[-w:].mean(); m1=c[-w-1:-1].mean(); m2=c[-w-2:-2].mean()
    if m>m1 and m1<=m2: return 1
    if m<m1 and m1>=m2: return -1
    return 0

def merge_k(h,l):
    mh=[float(h[0])]; ml=[float(l[0])]; src=[0]; d=1
    for i in range(1,len(h)):
        if (h[i]<=mh[-1] and l[i]>=ml[-1]) or (h[i]>=mh[-1] and l[i]<=ml[-1]):
            if d>0: mh[-1]=max(h[i],mh[-1]); ml[-1]=max(l[i],ml[-1])
            else:   mh[-1]=min(h[i],mh[-1]); ml[-1]=min(l[i],ml[-1])
            src[-1]=i
        else:
            mh.append(float(h[i])); ml.append(float(l[i])); src.append(i)
            d=1 if mh[-1]>mh[-2] else -1
    return np.array(mh),np.array(ml),np.array(src)

def fractals(mh,ml,src):
    pts=[]
    for i in range(1,len(mh)-1):
        if mh[i]>mh[i-1] and mh[i]>mh[i+1] and ml[i]>ml[i-1] and ml[i]>ml[i+1]: pts.append((int(src[i]),'top',float(mh[i])))
        elif ml[i]<ml[i-1] and ml[i]<ml[i+1] and mh[i]<mh[i-1] and mh[i]<mh[i+1]: pts.append((int(src[i]),'bot',float(ml[i])))
    clean=[]
    for p in pts:
        if clean and clean[-1][1]==p[1]:
            if (p[1]=='top' and p[2]>=clean[-1][2]) or (p[1]=='bot' and p[2]<=clean[-1][2]): clean[-1]=p
        else: clean.append(p)
    return clean

def build_bis(pts,gap=4):
    bis=[]
    for i in range(1,len(pts)):
        a,b=pts[i-1],pts[i]
        if a[1]!=b[1] and abs(b[0]-a[0])>=gap:
            bis.append({'dir':'up' if b[1]=='top' else 'down','s':a[0],'e':b[0]})
    return bis

def analysis(hh,ll,cc):
    c=np.array(cc,float); dif=macd_dif(c)
    mh,ml,src=merge_k(hh,ll); pts=fractals(mh,ml,src); bis=build_bis(pts)
    tops=[p for p in pts if p[1]=='top']; bots=[p for p in pts if p[1]=='bot']
    db=dt=False
    if len(bots)>=2:
        j,j0=bots[-1][0],bots[-2][0]; db=(c[j]<c[j0]) and (dif[j]>dif[j0])
    if len(tops)>=2:
        j,j0=tops[-1][0],tops[-2][0]; dt=(c[j]>c[j0]) and (dif[j]<dif[j0])
    lp=pts[-1] if pts else None
    return {'last_bi':bis[-1] if bis else None,'last_pt':lp,
            'bot_conf':(lp is not None and lp[1]=='bot' and lp[0]<len(c)-1),
            'top_conf':(lp is not None and lp[1]=='top' and lp[0]<len(c)-1),
            'div_bot':db,'div_top':dt,'ma20':ma_turn(c,20),'ma60':ma_turn(c,60)}

def load_map():
    m=sqlite3.connect(M,uri=True); ss=defaultdict(list); mem=defaultdict(list); nm={}
    for code,sid in m.execute("SELECT code,sector_id FROM stock_sector"): ss[code].append(sid); mem[sid].append(code)
    for sid,name,tp in m.execute("SELECT sector_id,name,type FROM sector"): nm[sid]=(name,tp)
    m.close(); return ss,mem,nm

def main(topn=8,maxc=60):
    ss,mem,secnm=load_map()
    h=sqlite3.connect(H,uri=True)
    idx=h.execute("SELECT date,close FROM kline_daily_qfq WHERE code='sh000001' ORDER BY date").fetchall()
    days=[r[0] for r in idx]; ic=np.array([r[1] for r in idx],float)
    mkt=(ic[-1]-ic[-250:].min())/(ic[-250:].max()-ic[-250:].min()+1e-9)*100
    d3=set(days[-3:])
    print(f"最新 {days[-1]}  大盘250日分位 {mkt:.1f}%  → {'进攻' if mkt<30 else ('中性' if mkt<70 else '防守')}")
    start=days[-300] if len(days)>300 else days[0]
    lu=defaultdict(int); info={}; cur=None; D=[];HH=[];LL=[];CC=[]
    def flush(code,D,HH,LL,CC):
        n=len(CC)
        if n<60: return
        c=np.array(CC,float); rmax=c[-250:].max(); rmin=c[-250:].min()
        info[code]={'pos':(c[-1]-rmin)/(rmax-rmin+1e-9)*100,'close':c[-1],'last_date':D[-1]}
        thr=0.195 if code[:3] in ('300','688') else 0.098
        for k in range(1,n):
            if D[k] in d3 and c[k]/c[k-1]-1>=thr:
                for sid in ss.get(code,()): lu[(D[k],sid)]+=1
    for code,date,hi,lo,cl in h.execute("SELECT code,date,high,low,close FROM kline_daily_qfq WHERE date>=? AND code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]' ORDER BY code,date",(start,)):
        if code!=cur:
            if CC: flush(cur,D,HH,LL,CC)
            D=[];HH=[];LL=[];CC=[]; cur=code
        D.append(date); HH.append(float(hi)); LL.append(float(lo)); CC.append(float(cl))
    if CC: flush(cur,D,HH,LL,CC)
    hot=[s for s in mem if all(lu.get((d,s),0)>=3 for d in days[-3:])]
    hot=sorted(hot,key=lambda s:-sum(lu.get((d,s),0) for d in days[-3:]))
    print(f"热点板块 {len(hot)} 个: "+", ".join(secnm.get(s,('?',))[0] for s in hot[:topn]))
    cand={}
    for sid in set(hot):
        for code in mem[sid]:
            if code.startswith(('688','920','8','4')): continue
            i=info.get(code)
            if i and i['pos']<30 and i['last_date']>=days[-3] and i['close']>2.0: cand[code]=i
    print(f"候选(热点板块内 位置<30%, 价>2元): {len(cand)} 只\n")
    print(f"{'代码':<8}{'位置':>6}{'现价':>8} {'日线':<13}{'30min':<13}{'背离':<8}{'均线拐头':<10}{'信号'}")
    print("-"*108)
    sig=[]
    for code,inf in sorted(cand.items(),key=lambda x:x[1]['pos'])[:maxc]:
        r=h.execute("SELECT date,high,low,close FROM kline_daily_qfq WHERE code=? ORDER BY date",(code,)).fetchall()
        A=analysis(np.array([x[1] for x in r],float),np.array([x[2] for x in r],float),np.array([x[3] for x in r],float))
        r30=h.execute("SELECT date,high,low,close FROM kline_30min WHERE code=? ORDER BY date",(code,)).fetchall()[-1200:]
        if len(r30)<100: continue
        B=analysis(np.array([x[1] for x in r30],float),np.array([x[2] for x in r30],float),np.array([x[3] for x in r30],float))
        bd=A['last_bi']['dir'] if A['last_bi'] else '-'; pd_=A['last_pt'][1] if A['last_pt'] else '-'
        b3=B['last_bi']['dir'] if B['last_bi'] else '-'; p3=B['last_pt'][1] if B['last_pt'] else '-'
        dv=('底背离 ' if A['div_bot'] else '')+('顶背离! ' if A['div_top'] else '')
        mt=[]
        if A['ma20']>0: mt.append('MA20↑')
        if A['ma60']>0: mt.append('MA60↑')
        if A['ma20']<0: mt.append('MA20↓')
        if A['ma60']<0: mt.append('MA60↓')
        mts=' '.join(mt) if mt else '—'
        bp=''
        if B['bot_conf'] and inf['pos']<30:
            score=(1 if A['div_bot'] else 0)+(1 if (A['ma20']>0 or A['ma60']>0) else 0)+(1 if (A['bot_conf'] or bd=='up') else 0)
            if A['div_bot']: bp='★★强买(底背离'
            elif A['bot_conf'] or bd=='up': bp='★买(日线共振'
            elif b3=='up': bp='买(小周期转up'
            else: bp='观察('
            bp+=f',均线{sum(1 for x in [A["ma20"],A["ma60"]] if x>0)}/2'+')'
        if A['div_top'] and not bp: bp='⚠顶背离(持仓离场)'
        elif (A['ma20']<0 and A['ma60']<0) and not bp: bp='⚠均线双下拐(减仓)'
        if bp: sig.append((code,inf,dv,mts,bp))
        print(f"{code:<8}{inf['pos']:>5.0f}%{inf['close']:>8.2f} 日线:{bd}/{pd_:<7} 30m:{b3}/{p3:<7} {dv:<8}{mts:<11}{bp}")
    h.close()
    print("-"*108)
    print(f"信号 {len(sig)} 只:")
    for code,inf,dv,mts,bp in sig: print(f"  {code} 位置{inf['pos']:.0f}% 价{inf['close']:.2f}  {dv}{mts}  {bp}")

if __name__=="__main__": main()
