# -*- coding: utf-8 -*-
"""验证 prev_close_play 板块差异化涨停判定"""
import sys, warnings
sys.path.insert(0, '.')
warnings.filterwarnings('ignore')
import pandas as pd, datetime as dt
from strategies.prev_close_play import check_prev_close
import numpy as np

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

def show(name, closes, code):
    r = check_prev_close(make_df(closes, code))
    print(f'{name}: signal={r["signal"]} type={r["type"]} desc={r["desc"][:45]}')
    return r

# 1. 创业板 +18% (20cm内) → 应可买B
r1 = show('创业板 +18%   ', [10.0] * 29 + [10.0, 11.8], '300319')
assert r1['signal'] and r1['type'] == 'B', '创业板18%应可买B'

# 2. 创业板 +19.5% (接近涨停) → 应排除
r2 = show('创业板 +19.5%  ', [10.0] * 29 + [10.0, 11.95], '300319')
assert r2['signal'] == False, '创业板19.5%应排除'

# 3. 主板 +9.5% (接近涨停) → 应排除
r3 = show('主板 +9.5%     ', [10.0] * 29 + [10.0, 10.95], '600519')
assert r3['signal'] == False, '主板9.5%应排除'

# 4. 主板 +7% (10cm内) → 应可买B
r4 = show('主板 +7%       ', [10.0] * 29 + [10.0, 10.7], '600519')
assert r4['signal'] and r4['type'] == 'B', '主板7%应可买B'

# 5. 科创板 +18.5% (20cm内, <19门槛) → 应可买B
r5 = show('科创板 +18.5%  ', [10.0] * 29 + [10.0, 11.85], '688001')
assert r5['signal'] and r5['type'] == 'B', '科创板18.5%应可买B'

# 6. 科创板 +19.5% (接近涨停) → 应排除
r6 = show('科创板 +19.5%  ', [10.0] * 29 + [10.0, 11.95], '688001')
assert r6['signal'] == False, '科创板19.5%应排除'

print()
print('=== prev_close_play 板块差异化涨停判定 全部通过 ===')
