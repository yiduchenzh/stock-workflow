import sqlite3
con = sqlite3.connect(r"file:D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db?mode=ro", uri=True)
cur = con.cursor()
print("distinct code sample (hunter qfq):")
for r in cur.execute("SELECT code, COUNT(*) FROM kline_daily_qfq GROUP BY code ORDER BY code LIMIT 15"):
    print("  ", r)
print("indices present?:")
for pat in ['sh000001','000001','sz399001','sh000300','399006','sh000905']:
    n = cur.execute("SELECT COUNT(*) FROM kline_daily_qfq WHERE code=?", (pat,)).fetchone()[0]
    print(f"   {pat}: {n}")
print("date range:", cur.execute("SELECT MIN(date),MAX(date) FROM kline_daily_qfq").fetchone())
print("300319 rows:", cur.execute("SELECT COUNT(*),MIN(date),MAX(date) FROM kline_daily_qfq WHERE code='300319'").fetchone())
con.close()

con2 = sqlite3.connect(r"file:D:\MarketData\market.db?mode=ro", uri=True)
c2 = con2.cursor()
print("\nmarket.db kline_daily code sample:")
for r in c2.execute("SELECT code, COUNT(*) FROM kline_daily GROUP BY code ORDER BY code LIMIT 10"):
    print("  ", r)
for pat in ['sh000001','000001','sz399001']:
    n = c2.execute("SELECT COUNT(*) FROM kline_daily WHERE code=?", (pat,)).fetchone()[0]
    print(f"   {pat}: {n}")
print("date range:", c2.execute("SELECT MIN(ts),MAX(ts) FROM kline_daily").fetchone())
con2.close()
