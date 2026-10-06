import sqlite3
H = r"file:D:\Hermes Agent CN Desktop\hunter-v2\data\hunter.db?mode=ro"
M = r"file:D:\MarketData\market.db?mode=ro"

h = sqlite3.connect(H, uri=True)
print("=== market_trend (大盘情绪) 最近10条 ===")
for r in h.execute("SELECT * FROM market_trend ORDER BY date DESC LIMIT 10"):
    print("  ", r)
print("  范围:", h.execute("SELECT MIN(date),MAX(date),COUNT(*) FROM market_trend").fetchone())

print("\n=== battle_plan / decision_log ===")
print("  bp:", h.execute("SELECT date,market_switch,position_pct,max_trades FROM battle_plan ORDER BY date DESC LIMIT 3").fetchall())
h.close()

m = sqlite3.connect(M, uri=True)
print("\n=== sector 类型分布 ===")
for r in m.execute("SELECT type, COUNT(*) FROM sector GROUP BY type"):
    print("  ", r)
print("=== sector 样例 ===")
for r in m.execute("SELECT sector_id,name,type,src FROM sector LIMIT 8"):
    print("  ", r)
print("\n=== sector_daily 样例 ===")
for r in m.execute("SELECT * FROM sector_daily ORDER BY ts DESC LIMIT 5"):
    print("  ", r)
print("  sector_daily 范围:", m.execute("SELECT MIN(ts),MAX(ts),COUNT(DISTINCT sector_id) FROM sector_daily").fetchone())
print("\n=== stock_sector 时点化样例 ===")
for r in m.execute("SELECT * FROM stock_sector WHERE code='300319' LIMIT 8"):
    print("  ", r)
print("  stock_sector 范围:", m.execute("SELECT MIN(valid_from),MAX(valid_from),COUNT(*) FROM stock_sector").fetchone())
m.close()
