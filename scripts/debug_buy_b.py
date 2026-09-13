# -*- coding: utf-8 -*-
"""内省 check_prev_close 为什么 创业板+18% 不触发买B"""
import sys, warnings
sys.path.insert(0, '.')
warnings.filterwarnings('ignore')
import pandas as pd, datetime as dt
import numpy as np
from strategies import prev_close_play as pcp

def make_df(closes, code):
    n = len(closes)
    opens = [c for c in closes]
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    vols = [100000] * n
    dates = [(dt.date(2026, 1, 1) + dt.timedelta(days=i)).strftime('%Y-%m-%d') for i in range(n)]
    df = pd.DataFrame({'date': dates, 'open': opens, 'high': highs, 'low': lows,
                       'close': closes, 'volume': vols})
    df.attrs['code'] = code
    return df

closes = [10.0] * 29 + [10.0, 11.8]
kdf = make_df(closes, '300319')

# 手动复算
close = np.asarray(kdf['close'].values, dtype=float)
open_ = np.asarray(kdf['open'].values, dtype=float)
low = np.asarray(kdf['low'].values, dtype=float)
high = np.asarray(kdf['high'].values, dtype=float)
vol = np.asarray(kdf['volume'].values, dtype=float)
prev_close = close[-2]
o, c, l, h = open_[-1], close[-1], low[-1], high[-1]
chg_pct = (c - prev_close) / prev_close * 100
print(f'prev_close={prev_close} o={o} c={c} l={l} chg_pct={chg_pct:.2f}')
print(f'len(close)={len(close)}')

trend = pcp._trend_state(close)
print(f'trend={trend} target_pct={pcp._trend_target_pct(trend)}')

# 复算 buy_A / buy_B 条件
from limitup_system.datafeed import limit_pct
lp = limit_pct('300319')
print(f'limit_pct(300319)={lp}')
buy_A = (o < prev_close) and (l < prev_close) and (c > prev_close) and trend != 'down'
limit_up = chg_pct >= (lp - 0.5) and o == c
buy_B = (o >= prev_close) and (l >= prev_close) and (c > prev_close) \
        and (chg_pct < lp - 1.0) and not limit_up
print(f'buy_A={buy_A}')
print(f'limit_up={limit_up} (chg>=19.5?{chg_pct>=19.5}, o==c?{o==c})')
print(f'buy_B 各条件: o>=prev={o>=prev_close}, l>=prev={l>=prev_close}, '
      f'c>prev={c>prev_close}, chg<19={chg_pct<19}, not limit_up={not limit_up}')

# 完整调用
r = pcp.check_prev_close(kdf)
print()
print('check_prev_close 返回:', r)
