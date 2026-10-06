# -*- coding: utf-8 -*-
"""P0-4 量测: 本周 mtf_close(三级共振卖出) 到底卖对了吗?

对每笔 sell(reason 含 mtf_close) 拉该票日K, 算卖出后 1/3/5 日涨跌:
  后续继续跌 -> 卖出正确(及时离场)
  后续反弹   -> 卖早了(买强卖弱口径不匹配的证据)
同时统计: 持有天数 / 卖出时盈亏 / 卖出价相对当日收盘位置
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, '.')

D = Path(r"D:\Hermes Agent CN Desktop\stock-workflow\data")
WS, WE = 1, 5   # 卖出后观察窗口(交易日)

try:
    from data.sources import get_kline
except Exception:
    try:
        from datafeed import get_kline          # noqa
    except Exception:
        get_kline = None
print("[src] get_kline =", get_kline)


def kl(code):
    if get_kline is None:
        return None
    for args in ((code, 60), (code, 120)):
        try:
            k = get_kline(*args)
            if k is not None and len(k) > 0:
                return k
        except Exception:
            continue
    return None


def rows_of(k):
    """归一成 [(day, close), ...] 升序"""
    out = []
    try:
        if hasattr(k, "iterrows"):
            for idx, r in k.iterrows():
                d = str(r.get("date") or r.get("day") or idx)[:10]
                out.append((d, float(r["close"])))
        else:
            for r in k:
                if isinstance(r, dict):
                    out.append((str(r.get("day") or r.get("date"))[:10], float(r.get("close") or 0)))
                elif isinstance(r, (list, tuple)) and len(r) >= 5:
                    out.append((str(r[0])[:10], float(r[4])))
    except Exception as e:
        print("   rows_of err:", e)
    return sorted(out)


print("\n=== 本周 mtf_close 卖出笔: 卖出后走势 ===")
tot_after = {1: [], 3: [], 5: []}
detail = []
for td in sorted(D.glob("agent_*/trades.json")):
    nm = td.parent.name.replace("agent_", "")
    try:
        rows = json.loads(td.read_text(encoding="utf-8"))
    except Exception:
        continue
    for t in rows:
        d = str(t.get("time") or "")[:10]
        if not ("2026-09-21" <= d < "2026-09-25"):
            continue
        if str(t.get("action", "")).lower() != "sell":
            continue
        reason = str(t.get("reason") or "")
        if "mtf_close" not in reason:
            continue
        code = str(t.get("code"))
        px = float(t.get("price") or 0)
        pnl = float(t.get("pnl") or 0)
        hold = t.get("holding_days")
        k = kl(code)
        rr = rows_of(k) if k is not None else []
        days = [x[0] for x in rr]
        after = {}
        if d in days and px > 0:
            i = days.index(d)
            for n in (1, 3, 5):
                if i + n < len(rr):
                    rp = rr[i + n][1]
                    after[n] = round((rp / px - 1) * 100, 2)
        for n, v in after.items():
            tot_after[n].append(v)
        detail.append((nm, d, code, px, pnl, hold, after, len(rr)))
        print("  %-8s %s %s 卖@%.2f pnl=%+8.0f 持有%s天 K线%s根 后1/3/5日=%s"
              % (nm, d, code, px, pnl, hold, len(rr), after or "(无后续数据)"))

print("\n=== 汇总: 卖出后继续跌(卖对) vs 反弹(卖早) ===")
for n in (1, 3, 5):
    v = tot_after[n]
    if not v:
        print("  后%d日: 无样本" % n)
        continue
    neg = [x for x in v if x < 0]
    pos = [x for x in v if x > 0]
    avg = sum(v) / len(v)
    print("  后%d日: n=%d 均值%+.2f%% | 继续跌 %d 笔(卖对) | 反弹 %d 笔(卖早) | 均值反弹%+.2f%%"
          % (n, len(v), avg, len(neg), len(pos),
             (sum(pos) / len(pos) if pos else 0)))

print("\n=== 卖出时点盈亏分布 ===")
pnls = [x[4] for x in detail]
print("  n=%d 合计%+.0f 均值%+.0f 最好%+.0f 最差%+.0f"
      % (len(pnls), sum(pnls), sum(pnls) / len(pnls) if pnls else 0,
         max(pnls) if pnls else 0, min(pnls) if pnls else 0))
print("  持有天数分布:", dict(Counter(x[5] for x in detail)))
