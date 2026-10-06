import json
import urllib.request
from pathlib import Path

d = json.loads(Path(r"D:\Hermes Agent CN Desktop\hunter-v2\data\prevclose15_state.json").read_text(encoding="utf-8"))
print("=== 15分K 引擎状态字段 ===")
for k in ("cash", "net", "peak_net", "cur_dd", "last_select_day", "last_tick", "last_bar_key", "positions_updated"):
    print("  %-18s %s" % (k, d.get(k)))
print("  universe            = %s 只" % len(d.get("universe") or []))
print("  universe_meta       =", json.dumps(d.get("universe_meta"), ensure_ascii=False)[:200])
print("  signals 条数        =", len(d.get("signals") or []))

st = d.get("stats") or {}
print("\n=== stats 原样 ===", json.dumps(st, ensure_ascii=False))

# 逐笔回合重算（引擎未记 pnl_pct, 只能按 建仓/加仓 → 清仓 配对）
tr = d.get("trades") or []
book = {}
rounds = []
for t in tr:
    c = t.get("code")
    sh = float(t.get("shares") or 0)
    amt = float(t.get("amount") or 0)
    act = t.get("action")
    if act in ("建仓", "加仓", "BUY"):
        b = book.setdefault(c, {"sh": 0.0, "amt": 0.0, "name": t.get("name")})
        b["sh"] += sh
        b["amt"] += amt
    elif act in ("清仓", "止损", "SELL"):
        b = book.get(c)
        if not b:
            continue
        avg = b["amt"] / b["sh"] if b["sh"] else 0
        pnl = amt - b["amt"]
        rounds.append({
            "code": c, "name": (b.get("name") or t.get("name") or ""),
            "shares": b["sh"], "cost": round(b["amt"], 2), "proceeds": round(amt, 2),
            "avg_cost": round(avg, 3), "sell_px": float(t.get("price") or 0),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl / b["amt"] * 100, 2) if b["amt"] else None,
            "exit_reason": (t.get("reason") or "")[:30],
        })
        book.pop(c, None)

print("\n=== 回合重算（建仓+加仓 → 清仓）===")
tot = 0.0
for r in rounds:
    tot += r["pnl"]
    print("  %-7s %-7s %5.0f股 成本%9.2f 卖出%9.2f  盈亏%+9.2f (%s%%)  %s"
          % (r["code"], r["name"][:6], r["shares"], r["cost"], r["proceeds"],
             r["pnl"], r["pnl_pct"], r["exit_reason"]))
wins = [r for r in rounds if r["pnl"] > 0]
print("  回合数=%d 盈利=%d 胜率=%.1f%% 合计盈亏=%+.2f 元 (引擎 stats.realized=%s)"
      % (len(rounds), len(wins), len(wins) / len(rounds) * 100 if rounds else 0, tot, st.get("realized")))
print("  未平仓:", {c: round(b['amt'], 2) for c, b in book.items()})

try:
    with urllib.request.urlopen("http://127.0.0.1:8000/api/v1/prevclose15/status", timeout=40) as r:
        api = json.loads(r.read().decode("utf-8", "ignore"))
    print("\n=== API /prevclose15/status ===")
    for k in ("running", "cash", "net", "peak_net", "cur_dd", "last_tick", "positions_updated"):
        print("  %-18s %s" % (k, api.get(k)))
    print("  stats =", json.dumps(api.get("stats"), ensure_ascii=False))
except Exception as e:
    print("\nAPI 未取到:", type(e).__name__, e)
