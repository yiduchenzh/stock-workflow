# -*- coding: utf-8 -*-
"""P0-4 量测②: 本周 22 笔买入的"追高"特征
对每笔 buy: 用当日日K 算 买入价相对前收涨幅 / 日内位置 / 距60日高回撤
判定: 买点 prev_close_B 是否在"已大涨"位置接盘
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, '.')
from data.sources import get_kline          # noqa: E402

D = Path(r"D:\Hermes Agent CN Desktop\stock-workflow\data")
W0, W1 = "2026-09-21", "2026-09-25"


def rows_of(k):
    out = []
    try:
        if hasattr(k, "iterrows"):
            for idx, r in k.iterrows():
                out.append((str(r.get("date") or r.get("day") or idx)[:10],
                            float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])))
        else:
            for r in k:
                if isinstance(r, dict):
                    out.append((str(r.get("day") or r.get("date"))[:10], float(r.get("open") or 0),
                                float(r.get("high") or 0), float(r.get("low") or 0), float(r.get("close") or 0)))
    except Exception as e:
        print("  rows err:", e)
    return sorted(out)


buys = []
for td in sorted(D.glob("agent_*/trades.json")):
    nm = td.parent.name.replace("agent_", "")
    try:
        rows = json.loads(td.read_text(encoding="utf-8"))
    except Exception:
        continue
    for t in rows:
        d = str(t.get("time") or "")[:10]
        if W0 <= d < W1 and str(t.get("action", "")).lower() == "buy":
            ctx = t.get("buy_context") or t.get("context") or {}
            buys.append((nm, d, str(t.get("code")), float(t.get("price") or 0), str(ctx.get("strategy") or "")))

print("=== 本周买入 %d 笔: 追高诊断 ===" % len(buys))
print("  %-8s %-11s %-8s %8s %8s %8s %8s %7s %7s  %s"
      % ("账户", "日期", "代码", "买入价", "前收", "当日%", "日内位%", "距60高%", "20日%", "战法"))
stats = {"chase5": 0, "chase3": 0, "near_high": 0, "n": 0}
detail = []
for nm, d, code, px, strat in buys:
    k = get_kline(code, 90)
    rr = rows_of(k) if k is not None else []
    days = [x[0] for x in rr]
    if d not in days or px <= 0:
        print("  %-8s %-11s %-8s %8.2f  (无K线数据)" % (nm, d, code, px))
        continue
    i = days.index(d)
    _, o, h, l, c = rr[i]
    prev = rr[i - 1][4] if i > 0 else c
    chg = (px / prev - 1) * 100 if prev else 0
    rng = (px - l) / (h - l) * 100 if h > l else 0
    hi60 = max(x[2] for x in rr[max(0, i - 59): i + 1])
    dd60 = (px / hi60 - 1) * 100 if hi60 else 0
    c20 = rr[i - 20][4] if i >= 20 else rr[0][4]
    chg20 = (px / c20 - 1) * 100 if c20 else 0
    stats["n"] += 1
    if chg > 5:
        stats["chase5"] += 1
    if chg > 3:
        stats["chase3"] += 1
    if dd60 > -5:
        stats["near_high"] += 1
    detail.append(chg)
    print("  %-8s %-11s %-8s %8.2f %8.2f %+8.2f %8.1f %+8.2f %+7.1f  %s"
          % (nm, d, code, px, prev, chg, rng, dd60, chg20, strat))

print("\n=== 汇总(n=%d) ===" % stats["n"])
print("  买入当日涨幅 >5%%(追高): %d 笔 (%.0f%%)" % (stats["chase5"], stats["chase5"] / max(1, stats["n"]) * 100))
print("  买入当日涨幅 >3%%       : %d 笔 (%.0f%%)" % (stats["chase3"], stats["chase3"] / max(1, stats["n"]) * 100))
print("  距60日高 <5%%(贴高位)    : %d 笔 (%.0f%%)" % (stats["near_high"], stats["near_high"] / max(1, stats["n"]) * 100))
if detail:
    print("  买入当日涨幅 均值%+.2f%% 中位%+.2f%% 最大%+.2f%% 最小%+.2f%%"
          % (sum(detail) / len(detail), sorted(detail)[len(detail) // 2], max(detail), min(detail)))
