import re
from pathlib import Path

ENG = {
    "①昨收战法(auto_trader)": Path(r"D:\Hermes Agent CN Desktop\hunter-v2\backend\auto_trader.py"),
    "②昨收15分K(prevclose15)": Path(r"D:\Hermes Agent CN Desktop\hunter-v2\backend\prevclose15_auto.py"),
    "③缠论(chan_auto_trader)": Path(r"D:\Hermes Agent CN Desktop\hunter-v2\backend\chan_auto_trader.py"),
}

info = {}
for k, p in ENG.items():
    t = p.read_text(encoding="utf-8", errors="ignore")
    funcs = set(re.findall(r"^\s*def\s+([A-Za-z_]\w*)", t, re.M))
    info[k] = {
        "loc": len(t.splitlines()),
        "bytes": len(t.encode("utf-8")),
        "funcs": funcs,
        "tick": set(re.findall(r"TICK_SEC\s*=\s*([0-9.]+)", t)),
        "stop": set(re.findall(r"(?:STOP_PCT|stop_pct)\s*=\s*(-?[0-9.]+)", t)),
        "guard": "market_guard" in t,
        "mootdx": "mootdx" in t,
        "tencent": "gtimg" in t,
        "em": "push2" in t or "eastmoney" in t,
        "shareddb": "kline.db" in t or "market.db" in t,
        "t1": bool(re.search(r"locked|T\+1|sellable", t)),
        "fees": bool(re.search(r"_fees|fee_rate|佣金|印花税", t)),
        "limit_pct": bool(re.search(r"limit_pct|涨停|跌停", t)),
        "state": set(re.findall(r'"(state|cash|positions|trades|signals|stats|last_tick|pool)"', t)),
    }

print("=== 规模 ===")
for k, v in info.items():
    print("  %-26s %5d 行  %6.1f KB" % (k, v["loc"], v["bytes"] / 1024))
print("  合计 %d 行 / %.1f KB" % (sum(v["loc"] for v in info.values()),
                                 sum(v["bytes"] for v in info.values()) / 1024))

print("\n=== 盯盘节奏 / 风控参数 / 数据源 ===")
for k, v in info.items():
    print("  %-26s tick=%s stop=%s guard=%s | mootdx=%s 腾讯=%s 东财=%s 共享库=%s"
          % (k, "".join(v["tick"]) or "-", "".join(v["stop"]) or "-", v["guard"],
             v["mootdx"], v["tencent"], v["em"], v["shareddb"]))
print("\n=== 每个引擎都自己实现的横切能力（重复劳动） ===")
for k, v in info.items():
    print("  %-26s T+1锁定=%s 手续费=%s 涨跌停=%s" % (k, v["t1"], v["fees"], v["limit_pct"]))

print("\n=== 同名函数（三引擎各写一遍 = 可上提共享内核）===")
keys = list(info)
allf = set.union(*[info[k]["funcs"] for k in keys])
for f in sorted(allf):
    holders = [k for k in keys if f in info[k]["funcs"]]
    if len(holders) >= 2 and not f.startswith("__"):
        print("  %-28s ← %s" % (f, " / ".join(h.split("(")[0] for h in holders)))

print("\n=== 函数集合两两重叠（Jaccard）===")
for i in range(len(keys)):
    for j in range(i + 1, len(keys)):
        a, b = info[keys[i]]["funcs"], info[keys[j]]["funcs"]
        inter = a & b
        uni = a | b
        print("  %-22s ∩ %-22s = %2d 个同名 / 并集 %3d → Jaccard %.2f"
              % (keys[i].split("(")[0], keys[j].split("(")[0], len(inter), len(uni), len(inter) / len(uni)))
