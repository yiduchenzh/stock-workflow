# -*- coding: utf-8 -*-
"""P0-3 量测: 本周(09-21~09-24) 各战法实际产信号/成交分布
判定 '100% 同质化' 是权重配置问题(已否) 还是 信号源问题
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

D = Path(r"D:\Hermes Agent CN Desktop\stock-workflow\data")
W0, W1 = "2026-09-21", "2026-09-25"
STRATS = ["prev_close_A", "prev_close_B", "momentum_breakout", "chan_buy1", "chan_buy3",
          "ma_breakout", "wave_point", "first_board", "sector_rotation", "mean_reversion",
          "naked_pinbar", "naked_engulf", "williams_r", "orb", "pullback", "123_rule"]

# ① 成交端: 各账户本周 trades 的 strategy 分布
print("=== ① 成交端 strategy 分布(本周) ===")
cnt = Counter()
for td in sorted(D.glob("agent_*/trades.json")):
    try:
        rows = json.loads(td.read_text(encoding="utf-8"))
    except Exception:
        continue
    nm = td.parent.name.replace("agent_", "")
    per = Counter()
    for t in rows:
        d = str(t.get("time") or "")[:10]
        if W0 <= d < W1:
            per[str(t.get("strategy") or "(空)")] += 1
            cnt[str(t.get("strategy") or "(空)")] += 1
    if per:
        print("  %-8s %s" % (nm, dict(per)))
print("  合计:", dict(cnt))

# ② 信号端: 日志中各战法名出现次数(本周) + 粗分类上下文
print("\n=== ② 日志端 各战法名出现次数(本周) ===")
log = D / "aurora.log"
lines = [l for l in log.read_text(encoding="utf-8", errors="replace").splitlines()
         if W0 <= l[:10] < W1]
print("  本周日志行:", len(lines))
hit = Counter()
for l in lines:
    for s in STRATS:
        if re.search(r"\b%s\b" % re.escape(s), l):
            hit[s] += 1
for s, c in hit.most_common():
    print("  %-20s %d" % (s, c))

# ③ 关键管线标记
print("\n=== ③ 管线关键标记(本周) ===")
for pat in ["[Strategy]", "confirmed", "[Plan]", "入选", "候选", "[Signal]", "prefer",
            "[Step5]", "[Step4]", "[Auction]", "StrategyWeight", "信号权重"]:
    n = sum(1 for l in lines if pat in l)
    print("  %-16s %d" % (pat, n))

# ④ 看 confirmed/plan 行长什么样(样本)
print("\n=== ④ 样本行(strategy/plan 相关, 末 12 条) ===")
samp = [l for l in lines if ("confirmed" in l or "[Plan]" in l or "[Strategy]" in l)]
for l in samp[-12:]:
    print("  " + l[:190])

# ⑤ candidate_history 本周战法分布
print("\n=== ⑤ candidate_history 分布 ===")
ch = D / "candidate_history.json"
if ch.exists():
    try:
        cd = json.loads(ch.read_text(encoding="utf-8"))
        if isinstance(cd, dict):
            ks = list(cd.keys())[:6]
            print("  type=dict keys=%s" % ks)
            for k in ks[:3]:
                v = cd[k]
                print("    %s -> %s" % (k, json.dumps(v, ensure_ascii=False)[:220]))
        else:
            print("  type=%s len=%s" % (type(cd).__name__, len(cd)))
            wk = [x for x in cd if W0 <= str(x.get("date") or x.get("time") or "")[:10] < W1]
            print("  本周条目:", len(wk))
            sc = Counter(str(x.get("strategy")) for x in wk)
            print("  strategy 分布:", dict(sc))
    except Exception as e:
        print("  读取失败:", e)
else:
    print("  (无 candidate_history.json)")
