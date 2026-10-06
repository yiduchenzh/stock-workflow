# -*- coding: utf-8 -*-
"""逆向看盘·处置引擎 — 位置×结构 → 处置方法/逻辑/可能结果"""
import sqlite3, sys, numpy as np

DB = r"file:D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db?mode=ro"

# ============ 处置矩阵: 位置档 × 结构档 ============
# 每格: (评级, 处置方法, 处置逻辑, 仓位上限, 止损锚, 结果倾向)
MATRIX = {
 ("低","上升"): ("⭐最佳", "分批建仓 3-3-4，首笔≤1/3仓",
   "赔率(下无套牢/上无压力)+方向(多头主导) 双优 → 期望最高", "80%",
   "最近结构低点", "向上为主，回撤是加仓机会"),
 ("低","区间"): ("🟡试探", "轻仓试探(≤1/5) 或等突破右侧",
   "赔率好但方向未定，用时间换确定性", "30%",
   "区间下沿-1.5%", "突破→转最佳；破位→等更低"),
 ("低","下降"): ("⚠️别接刀", "空仓等待，只看不动",
   "低位可能是'下跌中继'，赔率好是假象——没有结构就没有底", "0%",
   "以结构破坏(站上MA20+破前高)为入场前提", "大概率继续下探，抄底=接飞刀"),
 ("中","上升"): ("🟢顺势", "持有 / 回调到MA20加仓",
   "趋势中继段，方向明确、赔率中性，靠趋势赚钱", "60%",
   "MA20 或前一个HL", "延续为主，回调即机会"),
 ("中","区间"): ("🟡轻仓", "轻仓高抛低吸，或空仓等方向",
   "无赔率优势也无方向优势，纯波动博弈，性价比低", "20%",
   "区间边界", "震荡消耗，直到一方破局"),
 ("中","下降"): ("⚠️反弹减", "反弹到阻力位减仓，不新开",
   "下降趋势中继，反弹是逃命机会不是买点", "0-10%",
   "不设，以减仓为目标", "反弹后继续下行"),
 ("高","上升"): ("⚠️持不追", "持有+移动止盈，严禁新开仓",
   "方向仍多但赔率已差——获利盘随时兑现，风险收益比恶化", "≤50%且递减",
   "移动止盈(如跌破MA10/前低)", "趋势或延续，但一次回撤吃掉多日利润"),
 ("高","区间"): ("⚠️减仓", "主动减仓，等结构明朗",
   "高位横盘=派发嫌疑，多空在此换手，向下的概率大于向上", "≤30%",
   "跌破区间下沿即离场", "向下破位概率偏高"),
 ("高","下降"): ("🔴清仓", "清仓回避，绝不抄底",
   "赔率差+方向空=双杀区，任何反弹都是诱多", "0%",
   "无——不参与", "下跌为主，深套区"),
}

PRAISE = {"低":0,"中":1,"高":2}

def load(code):
    con = sqlite3.connect(DB, uri=True)
    rows = con.execute("SELECT date,high,low,close FROM kline_daily_qfq "
                       "WHERE code=? ORDER BY date", (code,)).fetchall()
    con.close()
    if len(rows) < 130: raise SystemExit(f"{code}: 数据不足 {len(rows)}")
    return ([r[0] for r in rows], np.array([r[1] for r in rows],float),
            np.array([r[2] for r in rows],float), np.array([r[3] for r in rows],float))

def classify(c, h, l):
    n=len(c); win=min(250,n)
    s=n-win
    pos=(c[-1]-l[s:].min())/(h[s:].max()-l[s:].min()+1e-9)*100
    m20,m60,m120 = c[-20:].mean(), c[-60:].mean(), c[-120:].mean()
    m250 = c[-min(250,n):].mean()
    if m20>m60>m120 and c[-1]>m250: st="上升"
    elif m20<m60<m120 and c[-1]<m250: st="下降"
    else: st="区间"
    lvl = "低" if pos<30 else ("中" if pos<70 else "高")
    return lvl, st, pos, (m20,m60,m120,m250)

# ============ 全市场扫描 ============
def scan():
    con = sqlite3.connect(DB, uri=True)
    print("拉取全市场近1年日K ...")
    cur = con.execute(
        "SELECT code,date,high,low,close FROM kline_daily_qfq "
        "WHERE date>='2025-03-01' AND code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]' "
        "ORDER BY code,date")
    from collections import defaultdict
    buf = defaultdict(lambda: [[],[],[]])
    for code,dt,hi,lo,cl in cur:
        b=buf[code]; b[0].append(hi); b[1].append(lo); b[2].append(cl)
    grid=defaultdict(list); total=0
    for code,(hi,lo,cl) in buf.items():
        if len(cl)<120: continue
        h=np.array(hi,float); l=np.array(lo,float); c=np.array(cl,float)
        try: lvl,st,pos,mas=classify(c,h,l)
        except Exception: continue
        grid[(lvl,st)].append((code,pos,c[-1])); total+=1
    print(f"\n有效样本 {total} 只")
    print("="*78)
    print(f"{'位置\\结构':<8}{'上升 HH+HL':>22}{'区间/转换':>22}{'下降 LH+LL':>22}")
    print("-"*78)
    for lvl in ["低","中","高"]:
        row=f"{lvl}位({['0-30%','30-70%','70-100%'][PRAISE[lvl]]})"
        cells=[]
        for st in ["上升","区间","下降"]:
            g=grid.get((lvl,st),[])
            pct=len(g)/total*100 if total else 0
            cells.append(f"{len(g):>5}只 ({pct:4.1f}%)")
        print(f"{lvl:>8}  {cells[0]:>22}{cells[1]:>22}{cells[2]:>22}")
    print("="*78)
    for lvl in ["低","中","高"]:
        for st in ["上升","区间","下降"]:
            g=sorted(grid.get((lvl,st),[]), key=lambda x:-x[1])
            reps=[f"{cc}({p:.0f}%)" for cc,p,_ in g[:4]]
            print(f"  [{lvl}位·{st}] {MATRIX[(lvl,st)][0]}  例: {', '.join(reps)}")

# ============ 单股处置卡 ============
def playbook(code, name=""):
    d,h,l,c = load(code)
    lvl,st,pos,mas = classify(c,h,l)
    rating,method,logic,cap,stop,outcome = MATRIX[(lvl,st)]
    m20,m60,m120,m250 = mas
    # 历史类比
    def feat(i,win=250):
        s=max(0,i-win+1)
        return ((c[i]-c[s:i+1].min())/(c[s:i+1].max()-c[s:i+1].min()+1e-9)*100,
                c[i]/c[i-60]-1 if i>=60 else 0)
    n=len(c); cur=feat(n-1); best=[]
    for i in range(260,n-130):
        f=feat(i); best.append((abs(f[0]-cur[0])/20+abs(f[1]-cur[1])/0.15,i))
    best.sort(); sel=[]
    for _,i in best[:300]:
        if all(abs(i-j)>20 for j in sel): sel.append(i)
    sel=sel[:30]
    allr=[c[i+120]/c[i]-1 for i in range(260,n-130)]
    base=float(np.mean(allr))
    r=[c[i+120]/c[i]-1 for i in sel]
    print("="*72)
    print(f"【{code} {name}】 现价 {c[-1]:.2f}  ({d[-1]})")
    print(f"  位置: 近250日分位 {pos:.1f}%  → {lvl}位")
    print(f"  结构: MA20={m20:.2f} MA60={m60:.2f} MA120={m120:.2f} MA250={m250:.2f} → {st}")
    print(f"  ▶ 评级 {rating}")
    print(f"  ▶ 处置方法: {method}")
    print(f"  ▶ 处置逻辑: {logic}")
    print(f"  ▶ 仓位上限: {cap}   止损锚: {stop}")
    print(f"  ▶ 结果倾向: {outcome}")
    if sel:
        r=np.array(r); exc=r-base
        print(f"\n  无条件基线(该股任意时点后120日): {base*100:+.1f}%")
        print(f"  历史类比({len(sel)}点,位置{cur[0]:.0f}%): 胜率{(r>0).mean()*100:.0f}%  "
              f"中位{r.mean()*100:+.1f}%  → 超额{exc.mean()*100:+.1f}%")
        print(f"    四分位: 25%{np.percentile(r,25)*100:+.1f}% / 75%{np.percentile(r,75)*100:+.1f}%  "
              f"最差{r.min()*100:+.1f}%")
        print(f"    情景: 🟢乐观{np.percentile(r,75)*100:+.0f}%  ⚪中性{r.mean()*100:+.0f}%  "
              f"🔴悲观{np.percentile(r,25)*100:+.0f}% (最差{r.min()*100:+.0f}%)")

if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]=="scan": scan()
    else:
        code=sys.argv[1] if len(sys.argv)>1 else "sh000001"
        nm=sys.argv[2] if len(sys.argv)>2 else ""
        playbook(code,nm)
