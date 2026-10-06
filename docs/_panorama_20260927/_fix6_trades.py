import json

d = json.load(open(r"D:\Hermes Agent CN Desktop\hunter-v2\data\auto_trader_state.json", encoding="utf-8"))
print("=== 全部 13 笔（按时间）===")
for t in d.get("trades") or []:
    print("%-19s %-4s %-8s %-8s px=%-8s sh=%-6s amt=%-10s pnl%%=%-7s %s"
          % (t.get("ts", ""), t.get("action", ""), t.get("code", ""), (t.get("name") or "")[:6],
             t.get("price"), t.get("shares"), t.get("amount"), t.get("pnl_pct"), (t.get("reason") or "")[:26]))
print("\n=== 当前持仓 ===")
for c, p in (d.get("positions") or {}).items():
    print(c, json.dumps(p, ensure_ascii=False)[:150])
print("\n=== notes 尾部 ===")
for n in (d.get("notes") or [])[-6:]:
    print(" ", n)
