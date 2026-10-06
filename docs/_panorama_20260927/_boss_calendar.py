import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Hermes Agent CN Desktop\hunter-v2\backend")
import trading_calendar as tc  # noqa

print("TradingCalendar 方法:", [m for m in dir(tc.TradingCalendar) if not m.startswith("_")])
cal = tc.TradingCalendar()
for d in ("2026-09-23", "2026-09-24", "2026-09-25", "2026-09-26", "2026-09-27", "2026-09-28"):
    try:
        print(d, "is_trading_day =", cal.is_trading_day(d))
    except TypeError:
        print(d, "is_trading_day() =", cal.is_trading_day())
        break

# 交易日历库
p = Path(r"D:\Hermes Agent CN Desktop\hunter-v2\data\trade_calendar.db")
if p.exists():
    con = sqlite3.connect(str(p))
    tabs = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    print("\ntrade_calendar.db 表:", tabs)
    for t in tabs:
        cols = [r[1] for r in con.execute("PRAGMA table_info(%s)" % t)]
        print(" ", t, cols)
        rows = con.execute("SELECT * FROM %s WHERE CAST(%s AS TEXT) LIKE '%%2026-09-2%%' LIMIT 8"
                           % (t, cols[0] if cols else "1")).fetchall()
        print("   2026-09-2x 行:", rows[:8])
    con.close()
