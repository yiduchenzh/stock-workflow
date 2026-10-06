import sqlite3, os

for p in [r"D:\MarketData\market.db", r"D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db"]:
    print("="*70)
    print(p, os.path.getsize(p)//1024//1024, "MB")
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    cur = con.cursor()
    tabs = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    print("tables:", tabs[:40])
    for t in tabs[:40]:
        try:
            n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            cols = [c[1] for c in cur.execute(f"PRAGMA table_info({t})")]
            print(f"  [{t}] rows={n:,} cols={cols}")
        except Exception as e:
            print(f"  [{t}] ERR {e}")
    con.close()
