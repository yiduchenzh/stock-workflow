import json
from collections import Counter
from pathlib import Path

P = Path(r"D:\Hermes Agent CN Desktop\hunter-v2\data\prevclose15_state.json")
d = json.loads(P.read_text(encoding="utf-8"))
print("顶层键:", list(d.keys()))
print("running=%s | cash=%s | stats=%s" % (d.get("running"), d.get("cash"), d.get("stats")))
cfg = d.get("cfg") or {}
print("\ncfg 关键参数:", {k: cfg.get(k) for k in ("capital", "pos_up", "stop_pct", "gap_stop_pct",
      "max_positions", "max_total_pos", "max_per_stock_pct", "dd_stop_pct", "auto_select", "pool_size")})

tr = d.get("trades") or []
print("\n=== 全部 %d 笔 ===" % len(tr))
for t in tr:
    print("%-17s %-5s %-7s %-7s px=%-8s sh=%-6s amt=%-9s pnl%%=%-8s %s"
          % (t.get("ts", ""), t.get("action", ""), t.get("code", ""), (t.get("name") or "")[:6],
             t.get("price"), t.get("shares"), t.get("amount"), t.get("pnl_pct"),
             (t.get("reason") or "")[:34]))

acts = Counter(t.get("action") for t in tr)
print("\n动作分布:", dict(acts))

sells = [t for t in tr if str(t.get("action", "")).upper() in ("SELL", "卖出", "清仓", "止损")]
print("卖出笔数:", len(sells))
if sells:
    pcts = [float(t.get("pnl_pct") or 0) for t in sells]
    wins = [p for p in pcts if p > 0]
    print("盈利笔=%d 亏损笔=%d 胜率=%.1f%%" % (len(wins), len(pcts) - len(wins), len(wins) / len(pcts) * 100))
    print("均值=%.2f%% 最好=%.2f%% 最差=%.2f%%" % (sum(pcts) / len(pcts), max(pcts), min(pcts)))
    print("合计已实现≈%.2f 元 (Σ amount×pnl%%/100 = %.2f)"
          % (sum(float(t.get("pnl_pct") or 0) for t in sells),
             sum(float(t.get("amount") or 0) * float(t.get("pnl_pct") or 0) / 100 for t in sells)))
    # 坏价嫌疑: 成交价 < 1 元 或 与 amount/shares 不一致
    print("\n坏价嫌疑(price<1 或 price*shares != amount):")
    for t in tr:
        px, sh, amt = t.get("price"), t.get("shares"), t.get("amount")
        try:
            px, sh, amt = float(px), float(sh), float(amt)
        except (TypeError, ValueError):
            continue
        if px < 1.0 or (sh and amt and abs(px * sh - amt) > max(1.0, amt * 0.02)):
            print("   ⚠️", t.get("ts"), t.get("code"), t.get("name"), "px=", px, "sh=", sh, "amt=", amt,
                  "px*sh=%.2f" % (px * sh))

print("\n=== 当前持仓 ===", len(d.get("positions") or {}))
for c, p in (d.get("positions") or {}).items():
    print(" ", c, (p.get("name") or ""), "cost=", p.get("cost"), "price=", p.get("price"),
          "buy_day=", p.get("buy_day"), "shares=", p.get("shares"))
print("\n=== notes 尾部 ===")
for n in (d.get("notes") or [])[-8:]:
    print("  ", n)
