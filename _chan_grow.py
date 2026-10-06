# -*- coding: utf-8 -*-
"""缠论级别生长 — 分型→笔→段→更高级别, 用真实数据展示递归自同构"""
import sqlite3, sys, numpy as np

H = r"file:D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db?mode=ro"

def load(code, table="kline_daily_qfq", n=1200):
    con=sqlite3.connect(H,uri=True)
    rows=con.execute(f"SELECT date,open,high,low,close FROM {table} WHERE code=? ORDER BY date",(code,)).fetchall()
    con.close()
    rows=rows[-n:]
    return ([r[0] for r in rows],np.array([r[1] for r in rows],float),np.array([r[2] for r in rows],float),
            np.array([r[3] for r in rows],float),np.array([r[4] for r in rows],float))

def merge_k(h,l):
    """K线包含处理"""
    mh=[h[0]]; ml=[l[0]]; src=[0]; d=1
    for i in range(1,len(h)):
        if (h[i]<=mh[-1] and l[i]>=ml[-1]) or (h[i]>=mh[-1] and l[i]<=ml[-1]):
            if d>0: mh[-1]=max(h[i],mh[-1]); ml[-1]=max(l[i],ml[-1])
            else:   mh[-1]=min(h[i],mh[-1]); ml[-1]=min(l[i],ml[-1])
            src[-1]=i
        else:
            mh.append(h[i]); ml.append(l[i]); src.append(i)
            d = 1 if mh[-1]>mh[-2] else -1
    return np.array(mh),np.array(ml),src

def fractals(mh,ml,src):
    """分型: 返回交替的(源idx,类型,价格)"""
    pts=[]
    for i in range(1,len(mh)-1):
        if mh[i]>mh[i-1] and mh[i]>mh[i+1] and ml[i]>ml[i-1] and ml[i]>ml[i+1]:
            pts.append((src[i],'top',mh[i]))
        elif ml[i]<ml[i-1] and ml[i]<ml[i+1] and mh[i]<mh[i-1] and mh[i]<mh[i+1]:
            pts.append((src[i],'bot',ml[i]))
    # 去重: 相邻同类型取更极端
    clean=[]
    for p in pts:
        if clean and clean[-1][1]==p[1]:
            if (p[1]=='top' and p[2]>=clean[-1][2]) or (p[1]=='bot' and p[2]<=clean[-1][2]):
                clean[-1]=p
        else:
            clean.append(p)
    return clean

def build_bis(pts, min_gap=4):
    """笔: 相邻顶底 + 间隔>=min_gap (处理后K线)"""
    bis=[]
    for i in range(1,len(pts)):
        a,b=pts[i-1],pts[i]
        if a[1]!=b[1] and abs(b[0]-a[0])>=min_gap:
            bis.append({'dir':'up' if b[1]=='top' else 'down','s':a[0],'e':b[0],'sp':a[2],'ep':b[2]})
    return bis

def build_segs(bis):
    """段: 3笔聚合, 端点=首笔起点/末笔终点 (缠论近似: 约3笔成段)"""
    segs=[]
    for i in range(0,len(bis)-2,3):
        grp=bis[i:i+3]
        segs.append({'s':grp[0]['s'],'e':grp[-1]['e'],'sp':grp[0]['sp'],'ep':grp[-1]['ep'],
                     'dir':'up' if grp[-1]['ep']>grp[0]['sp'] else 'down','n_bi':len(grp)})
    return segs

def grow(code,name,table):
    dates,o,h,l,c=load(code,table)
    mh,ml,src=merge_k(h,l)
    pts=fractals(mh,ml,src)
    bis=build_bis(pts)
    segs=build_segs(bis)
    # 递归: 段端点再当笔
    dt2=[dates[0]]*0
    print("="*76)
    print(f"【{code} {name}】{table}  {len(c)}根  {dates[0]} ~ {dates[-1]}")
    print(f"  L0 原始K线 : {len(c)}")
    print(f"  L0 包含处理后: {len(mh)}")
    print(f"  L1 分型    : {len(pts)}   (顶{sum(1 for p in pts if p[1]=='top')} 底{sum(1 for p in pts if p[1]=='bot')})")
    print(f"  L2 笔      : {len(bis)}")
    print(f"  L3 段      : {len(segs)}  (3笔/段)")
    if segs:
        up=sum(1 for s in segs if s['dir']=='up')
        print(f"     段方向分布: 上{up} 下{len(segs)-up}")
        print(f"     最后一笔: {bis[-1]['dir']}  {dates[bis[-1]['s']]} {bis[-1]['sp']:.2f} → {dates[bis[-1]['e']]} {bis[-1]['ep']:.2f}")
        print(f"     最后一段: {segs[-1]['dir']}  {dates[segs[-1]['s']]} {segs[-1]['sp']:.2f} → {dates[segs[-1]['e']]} {segs[-1]['ep']:.2f}  (含{segs[-1]['n_bi']}笔)")
    # 生长比
    print(f"\n  生长比: 笔/分型={len(bis)/max(1,len(pts)):.2f}  段/笔={len(segs)/max(1,len(bis)):.2f}  "
          f"→ 每涨一级约聚合 {len(bis)/max(1,len(segs)):.1f} 笔")
    # 最近5笔展示
    print(f"\n  最近5笔:")
    for b in bis[-5:]:
        print(f"    {b['dir']:>4}  {dates[b['s']]} {b['sp']:7.2f} → {dates[b['e']]} {b['ep']:7.2f}")

if __name__=="__main__":
    code=sys.argv[1] if len(sys.argv)>1 else "300319"
    nm=sys.argv[2] if len(sys.argv)>2 else ""
    tb=sys.argv[3] if len(sys.argv)>3 else "kline_daily_qfq"
    grow(code,nm,tb)
