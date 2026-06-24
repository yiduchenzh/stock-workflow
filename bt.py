"""Unified backtest -- parameterized"""
import sys, os, json, time
from datetime import datetime
from pathlib import Path
import pandas as pd
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))

def run(name, stocks, period_start, period_end, capital=1000000, max_price=100, max_pos=5):
    from data.sources import get_kline as tk
    from strategies.runner import analyze_all
    from executor.sim_account import SimAccount
    kc = {}
    for co in stocks:
        df = tk(co, 1000)
        if df is not None and not df.empty:
            df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
            kc[co] = df
    print('[{}] {}/{} loaded'.format(name, len(kc), len(stocks)))
    al = set()
    for df in kc.values():
        if 'date' in df.columns: al.update(df['date'].values)
    al = sorted([d for d in al if period_start <= d <= period_end])
    print('[{}] {} days'.format(name, len(al)))

    acc = SimAccount(capital)
    trades = []
    for dt in al:
        for co in list(acc.positions.keys()):
            df = kc.get(co)
            if df is None: continue
            r = df[df['date']==dt]
            if r.empty:
                m = df[df['date']<=dt]
                if m.empty: continue
                r = m.iloc[-1:]
            if r.empty: continue
            cp = float(r['close'].iloc[-1])
            p = acc.positions[co]
            ep = p.get('avg_cost', cp)
            if cp <= ep*0.93:
                res = acc.sell(co, cp, p['shares'], 'stop')
                if res: trades.append(res['trade'])
                continue
            if cp >= ep*1.196:
                res = acc.sell(co, cp, p['shares'], 'tp')
                if res: trades.append(res['trade'])
                continue
            ed = p.get('entry_date')
            if ed:
                ed_dt = datetime.strptime(str(ed)[:10], '%Y-%m-%d')
                if (datetime.strptime(dt,'%Y-%m-%d')-ed_dt).days > 60:
                    res = acc.sell(co, cp, p['shares'], 'time')
                    if res: trades.append(res['trade'])
                    continue
        if len(acc.positions) >= max_pos: continue
        for co in stocks:
            if co in acc.positions: continue
            df = kc.get(co)
            if df is None: continue
            k = df[df['date']<=dt].tail(120).copy()
            if len(k) < 30: continue
            px = float(k['close'].iloc[-1])
            if px<=0 or px>max_price: continue
            dummy = [{'code':co,'name':co,'price':px}]
            rr = analyze_all(dummy, kline_override={co:k})
            if rr and rr[0].get('signal'):
                rps = px*0.07
                sh = max(100, int(acc.cash*0.01/rps/100)*100)
                if sh*px < acc.cash: acc.buy(co, px, sh, name)
    for co in list(acc.positions.keys()):
        p = acc.positions[co]
        cur = float(kc[co]['close'].iloc[-1]) if kc.get(co) is not None else p.get('avg_cost',0)
        res = acc.sell(co, cur, p['shares'], 'end')
        if res: trades.append(res['trade'])
    n = len(trades)
    wins = [t for t in trades if t.get('pnl',0) > 0]
    losses = [t for t in trades if t.get('pnl',0) <= 0]
    wr = len(wins)/n*100 if n>0 else 0
    tp = sum(t.get('pnl',0) for t in trades)
    gp = sum(t.get('pnl',0) for t in wins)
    gl = abs(sum(t.get('pnl',0) for t in losses))
    pf = gp/gl if gl>0 else 0
    return {'strategy':name,'n':n,'wr':round(wr,1),'pf':round(pf,2),'pnl':round(tp,0)}

if __name__=='__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--strategies', nargs='+', default=['wave_point'])
    p.add_argument('--start', default='2024-01-01')
    p.add_argument('--end', default=datetime.now().strftime('%Y-%m-%d'))
    p.add_argument('--stocks', nargs='+', default=['000001','000002','000333','000568','000651','000858','002304','002415','002475','300059','600036','600276','600887','601166','601318','601899','600030','600585'])
    args = p.parse_args()
    t0 = time.time()
    results = []
    for sn in args.strategies:
        r = run(sn, args.stocks, args.start, args.end)
        results.append(r)
        s = '+' if r['pnl']>0 else ''
        print('  {:20s} {:3d}tr WR={:5.1f}% PF={:5.2f} P&L {:s}{:.0f}'.format(sn, r['n'], r['wr'], r['pf'], s, r['pnl']))
    json.dump(results, open(Path(__file__).parent/'data'/'bt_unified.json','w'), indent=2)
    print('[Saved] data/bt_unified.json')
    print('Time: {:.1f}s'.format(time.time()-t0))
