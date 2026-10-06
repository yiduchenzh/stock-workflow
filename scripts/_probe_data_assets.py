# -*- coding: utf-8 -*-
"""现有本地数据资产体检: market.db / fundamentals.db / hunter.db 的表、行数、时间覆盖"""
import os
import sqlite3

TARGETS = [
    ("共享历史库 D:/MarketData/market.db", r"D:\MarketData\market.db"),
    ("stock-workflow data/fundamentals.db", r"D:\Hermes Agent CN Desktop\stock-workflow\data\fundamentals.db"),
    ("stock-workflow data/hunter.db", r"D:\Hermes Agent CN Desktop\stock-workflow\data\hunter.db"),
    ("hunter-v2 backend/data/hunter.db", r"D:\Hermes Agent CN Desktop\hunter-v2\backend\data\hunter.db"),
    ("hunter-v2 data/hunter.db", r"D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db"),
]

for label, path in TARGETS:
    print("=" * 92)
    print("%s" % label)
    print("=" * 92)
    if not os.path.exists(path):
        print("  (不存在)\n")
        continue
    size = os.path.getsize(path) / 1024 / 1024
    try:
        con = sqlite3.connect("file:%s?mode=ro" % path.replace("\\", "/"), uri=True, timeout=8)
        con.execute("PRAGMA busy_timeout=8000")
        tabs = [r[0] for r in con.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
        print("  大小 %.1f MB | 表 %d: %s" % (size, len(tabs), tabs))
        for t in tabs:
            try:
                n = con.execute("select count(*) from %s" % t).fetchone()[0]
                cols = [r[1] for r in con.execute("pragma table_info(%s)" % t)]
                span = ""
                for cand in ("ts", "day", "date", "trade_date", "updated_at"):
                    if cand in cols:
                        try:
                            lo, hi = con.execute("select min(%s), max(%s) from %s" % (cand, cand, t)).fetchone()
                            span = " | %s: %s ~ %s" % (cand, lo, hi)
                        except Exception:
                            pass
                        break
                nc = ""
                for cand in ("code", "symbol"):
                    if cand in cols:
                        try:
                            nc = " | code.nunique=%d" % con.execute("select count(distinct %s) from %s" % (cand, t)).fetchone()[0]
                        except Exception:
                            pass
                        break
                print("   %-22s %10d 行  %s%s%s" % (t, n, cols[:8], span, nc))
            except Exception as e:
                print("   %-22s ERR %s" % (t, str(e)[:70]))
        con.close()
    except Exception as e:
        print("  打开失败: %s" % str(e)[:120])
    print()
