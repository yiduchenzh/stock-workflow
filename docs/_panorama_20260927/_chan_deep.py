import json
from collections import Counter
from pathlib import Path

d = json.load(open(r"D:\Hermes Agent CN Desktop\hunter-v2\data\chan_trade_state.json", encoding="utf-8"))
tr = d.get("trades") or []
print("③缠论 trades =", len(tr))
print("动作分布:", dict(Counter(t.get("action") for t in tr)))

# 按 reason 归类
def cat(r):
    r = str(r or "")
    if "全清" in r or "清仓" in r:
        return "清仓级"
    if "减仓" in r:
        return "减仓级"
    if "止损" in r:
        return "止损"
    if "BUY" in r or "买" in r or "建" in r:
        return "买入"
    return "其他"

print("\n原因分类:", dict(Counter(cat(t.get("reason")) for t in tr)))

# 买入笔数
buys = [t for t in tr if str(t.get("action")).upper() == "BUY"]
sells = [t for t in tr if str(t.get("action")).upper() == "SELL"]
print("\n买入 %d 笔 / 卖出 %d 笔" % (len(buys), len(sells)))

# 卖出原因分布（这才是回合口径的关键）
print("\n卖出 reason 模式 (前 8):")
for r, c in Counter(str(t.get("reason"))[:34] for t in sells).most_common(8):
    print("   %-38s %d 笔" % (r, c))

# 每笔卖出金额分布 → 看是否大量小额减仓
amts = sorted(float(t.get("amount") or 0) for t in sells)
if amts:
    print("\n卖出金额: 最小 %.0f / 中位 %.0f / 最大 %.0f" % (amts[0], amts[len(amts) // 2], amts[-1]))
    small = [a for a in amts if a < 3000]
    print("   小额(<3000元)卖出 = %d 笔 (%.0f%%)" % (len(small), len(small) / len(amts) * 100))

# pnl_pct 分布（引擎自己记的）
pcts = [float(t.get("pnl_pct") or 0) for t in sells]
if pcts:
    pcts_sorted = sorted(pcts)
    print("\n卖出 pnl_pct: 均值 %.2f%% / 中位 %.2f%% / 最差 %.2f%% / 最好 %.2f%%"
          % (sum(pcts) / len(pcts), pcts_sorted[len(pcts) // 2], pcts_sorted[0], pcts_sorted[-1]))
    print("   亏损笔 %d / 盈利笔 %d" % (len([p for p in pcts if p < 0]), len([p for p in pcts if p > 0])))
    print("   0 附近(|p|<0.2%%) = %d 笔" % len([p for p in pcts if abs(p) < 0.2]))

print("\n=== 当前持仓 ===")
for c, p in (d.get("positions") or {}).items():
    print("  %s %s shares=%s cost=%s last=%s pnl%%=%s" % (c, (p.get("name") or "")[:6], p.get("shares"),
                                                          p.get("cost"), p.get("last") or p.get("price"), p.get("pnl_pct")))
