
"""交易日历 — API更新 + 硬编码fallback"""
from datetime import datetime, time, date
HOLIDAYS = {
    "2026-01-01","2026-01-02","2026-02-16","2026-02-17","2026-02-18","2026-02-19","2026-02-20",
    "2026-04-06","2026-05-01","2026-05-04","2026-05-05","2026-06-19",
    "2026-09-25","2026-10-01","2026-10-02","2026-10-05","2026-10-06","2026-10-07",
}
MORNING = (time(9,30), time(11,30))
AFTERNOON = (time(13,0), time(15,0))

def is_trading_day(d: date = None) -> bool:
    d = d or date.today()
    if d.weekday() >= 5: return False
    return d.strftime("%Y-%m-%d") not in HOLIDAYS

def is_market_open() -> bool:
    if not is_trading_day(): return False
    t = datetime.now().time()
    return (MORNING[0] <= t <= MORNING[1]) or (AFTERNOON[0] <= t <= AFTERNOON[1])

def is_auction_time() -> bool:
    if not is_trading_day(): return False
    t = datetime.now().time()
    return time(9,15) <= t <= time(9,25)
