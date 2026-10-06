import json
import os
import sys

sys.path.insert(0, r"D:\Hermes Agent CN Desktop\hunter-v2\backend")
try:
    import trading_calendar as tc
    fns = [n for n in dir(tc) if "trading" in n.lower() or "is_" in n]
    print("trading_calendar 公开函数:", fns)
    for d in ("2026-09-24", "2026-09-25", "2026-09-26", "2026-09-27"):
        out = []
        for n in ("is_trading_day", "is_trading", "is_trade_day"):
            f = getattr(tc, n, None)
            if callable(f):
                try:
                    out.append("%s(%s)=%s" % (n, d, f(d)))
                except Exception as e:
                    out.append("%s err %s" % (n, type(e).__name__))
        print(d, "|", " ".join(out) or "(无可用函数)")
except Exception as e:
    print("import trading_calendar failed:", type(e).__name__, e)

print("\n=== 引擎状态文件 ===")
base = r"D:\Hermes Agent CN Desktop\hunter-v2\data"
for fn in ("auto_trader_state.json", "prevclose15_state.json", "chan_trade_state.json"):
    p = os.path.join(base, fn)
    if not os.path.exists(p):
        print(fn, "缺失")
        continue
    mt = __import__("datetime").datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M:%S")
    d = json.load(open(p, encoding="utf-8"))
    print("%-26s mtime=%s running=%s day=%s last_tick=%s trades=%s positions=%s" % (
        fn, mt, d.get("running"), d.get("day"), d.get("last_tick"),
        len(d.get("trades") or []), len(d.get("positions") or {})))
