# -*- coding: utf-8 -*-
"""行情逆向反推器 — 从'当前价'反推: 位置/结构/历史类比/未来推断"""
import sqlite3, sys, numpy as np

DB = r"file:D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db?mode=ro"

def load(code):
    con = sqlite3.connect(DB, uri=True)
    rows = con.execute(
        "SELECT date, high, low, close, volume FROM kline_daily_qfq "
        "WHERE code=? ORDER BY date", (code,)).fetchall()
    con.close()
    if not rows:
        raise SystemExit(f"no data for {code}")
    d = [r[0] for r in rows]
    h = np.array([r[1] for r in rows], float)
    l = np.array([r[2] for r in rows], float)
    c = np.array([r[3] for r in rows], float)
    v = np.array([float(r[4] or 0) for r in rows])
    return d, h, l, c, v

def swings(h, l, k=5):
    """分型摆动点: 左右各k根内极值"""
    sh, sl = [], []
    for i in range(k, len(h)-k):
        if h[i] == max(h[i-k:i+k+1]): sh.append(i)
        if l[i] == min(l[i-k:i+k+1]): sl.append(i)
    return sh, sl

def structure(sh, sl, c):
    """用最近摆动点判定 HH/HL, LH/LL, 区间"""
    if len(sh) < 2 or len(sl) < 2: return "数据不足", 0
    hs = [h for h in [sh[-1], sh[-2], sh[-3]] if h is not None]
    H = [c[i] for i in sh[-3:]]
    L = [c[i] for i in sl[-3:]]
    if len(H) >= 2 and len(L) >= 2:
        hh = H[-1] > H[-2]; hl = L[-1] > L[-2]
        lh = H[-1] < H[-2]; ll = L[-1] < L[-2]
        if hh and hl: return "上升结构 HH+HL", 1
        if lh and ll: return "下降结构 LH+LL", -1
    return "区间/转换中", 0

def ma(a, n):
    if len(a) < n: return np.nan
    return a[-n:].mean()

def feat(c, i, win=250):
    """时点i的位置特征"""
    s = max(0, i-win+1)
    seg_h, seg_l = c[s:i+1].max(), c[s:i+1].min()
    pos = (c[i]-seg_l)/(seg_h-seg_l+1e-9)*100
    mom20 = c[i]/c[i-20]-1 if i>=20 else 0.0
    mom60 = c[i]/c[i-60]-1 if i>=60 else 0.0
    return pos, mom20, mom60

def main(code, name=""):
    d, h, l, c, v = load(code)
    n = len(c)
    px = c[-1]
    print("="*72)
    print(f"【{code} {name}】 共{n}条  区间 {d[0]} → {d[-1]}   最新收盘 {px:.2f}")

    # ---------- 1. 位置 ----------
    print("\n① 位置（当前价在历史什么位置）")
    for win, lab in [(250,"近1年"),(500,"近2年"),(1250,"近5年"),(n,"全历史")]:
        s = max(0, n-win)
        hi, lo = h[s:].max(), l[s:].min()
        pos = (px-lo)/(hi-lo+1e-9)*100
        print(f"   {lab:6s} 区间 {lo:8.2f} ~ {hi:8.2f} | 现值分位 {pos:5.1f}% "
              f"| 距顶 {(px/hi-1)*100:+6.1f}% | 距底 {(px/lo-1)*100:+7.1f}%")

    # ---------- 2. 结构 ----------
    print("\n② 结构（趋势是什么）")
    sh, sl = swings(h, l, 5)
    st, sig = structure(sh, sl, c)
    m20, m60, m120, m250 = ma(c,20), ma(c,60), ma(c,120), ma(c,250)
    order = "多头排列" if m20>m60>m120 else ("空头排列" if m20<m60<m120 else "均线缠绕")
    print(f"   摆动结构: {st}")
    print(f"   均线: MA20={m20:.2f} MA60={m60:.2f} MA120={m120:.2f} MA250={m250:.2f} → {order}")
    print(f"   现价 vs 年线: {(px/m250-1)*100:+.1f}%")
    # 最近摆动点
    last_sh = [(d[i], round(c[i],2)) for i in sh[-3:]]
    last_sl = [(d[i], round(c[i],2)) for i in sl[-3:]]
    print(f"   近3个高点: {last_sh}")
    print(f"   近3个低点: {last_sl}")

    # ---------- 3. 历史类比 ----------
    print("\n③ 历史类比（过去出现'位置+动量'相同状态时，后来怎么走）")
    cur = feat(c, n-1)
    best = []
    for i in range(260, n-130):          # 留出未来130日
        f = feat(c, i)
        dist = abs(f[0]-cur[0])/20 + abs(f[2]-cur[2])/0.15
        best.append((dist, i))
    best.sort()
    picks = [i for _, i in best[:40]]
    # 去重（间隔>30日）
    sel = []
    for i in picks:
        if all(abs(i-j) > 30 for j in sel): sel.append(i)
    sel = sel[:12]
    r20 = [c[i+20]/c[i]-1 for i in sel]
    r60 = [c[i+60]/c[i]-1 for i in sel]
    r120 = [c[i+120]/c[i]-1 for i in sel]
    print(f"   当前特征: 位置分位={cur[0]:.1f}%  60日动量={cur[2]*100:+.1f}%")
    print(f"   匹配到 {len(sel)} 个历史时点:")
    for i in sel:
        print(f"     {d[i]}  (位置{feat(c,i)[0]:.0f}%)  → 后20日 {(c[i+20]/c[i]-1)*100:+6.1f}%  "
              f"后60日 {(c[i+60]/c[i]-1)*100:+6.1f}%  后120日 {(c[i+120]/c[i]-1)*100:+7.1f}%")

    # ---------- 4. 未来推断 ----------
    print("\n④ 未来推断（基于历史类比的概率分布）")
    def stat(r, lab):
        r = np.array(r)
        print(f"   {lab}: 胜率{(r>0).mean()*100:4.0f}%  中位{r.mean()*100:+6.1f}%  "
              f"最好{r.max()*100:+7.1f}%  最差{r.min()*100:+7.1f}%  "
              f"区间[{np.percentile(r,25)*100:+.0f}%, {np.percentile(r,75)*100:+.0f}%]")
    stat(r20, "未来20日 ")
    stat(r60, "未来60日 ")
    stat(r120,"未来120日")

if __name__ == "__main__":
    code = sys.argv[1] if len(sys.argv) > 1 else "sh000001"
    name = sys.argv[2] if len(sys.argv) > 2 else ""
    main(code, name)
