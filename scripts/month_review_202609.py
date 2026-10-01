# -*- coding: utf-8 -*-
"""Aurora/stock-workflow 全周期复盘（2026-08-13 上线 ~ 2026-09-30）
用法: ./.venv/Scripts/python.exe scripts/month_review_202609.py > out.txt 2>&1
"""
import io
import json
import os
import sqlite3
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
START = "2026-08-13"
AGENTS = ["上班族中短线", "价值投资者", "新手入门", "短线狙击手", "趋势跟踪者"]


def load(p, default=None):
    try:
        return json.load(io.open(os.path.join(ROOT, p), encoding="utf-8"))
    except Exception:
        return default


def trades_of(path):
    t = load(path, [])
    if isinstance(t, dict):
        t = t.get("trades", [])
    return t


def d10(r):
    return str(r.get("date") or r.get("time") or r.get("ts") or "")[:10]


def pnl_of(r):
    for k in ("pnl", "pnl_amount", "realized"):
        if r.get(k) is not None:
            try:
                return float(r[k])
            except Exception:
                pass
    return 0.0


def pct_of(r):
    for k in ("pnl_pct", "pnl_percent"):
        if r.get(k) is not None:
            try:
                return float(r[k])
            except Exception:
                pass
    return None


print("=" * 84)
print("A. 账户层：全周期总览（%s ~ 2026-09-30）" % START)
print("=" * 84)
agg = load("data/agent_aggregate.json", {}) or {}
CAP = 1_000_000.0

rows = []
for name in AGENTS:
    t = [r for r in trades_of("data/agent_%s/trades.json" % name) if d10(r) >= START]
    buys = [r for r in t if str(r.get("action")) == "buy"]
    sells = [r for r in t if str(r.get("action")) == "sell"]
    real = sum(pnl_of(r) for r in sells)
    wins = [r for r in sells if pnl_of(r) > 0]
    pcts = [pct_of(r) for r in sells if pct_of(r) is not None]
    st = load("data/agent_%s/state.json" % name, {}) or {}
    tv = float(st.get("total_value") or st.get("total") or 0) or \
        float((agg.get("agents", {}).get(name) or {}).get("total_value") or 0)
    pos = st.get("positions") or {}
    pos_cost = 0.0
    if isinstance(pos, dict) and pos:
        for c, v in pos.items():
            if isinstance(v, dict):
                pos_cost += float(v.get("shares") or 0) * float(v.get("avg_cost") or v.get("cost") or 0)
    rows.append({
        "name": name, "n": len(t), "buy": len(buys), "sell": len(sells),
        "real": real, "wr": (100.0 * len(wins) / len(sells)) if sells else 0.0,
        "E_pct": (sum(pcts) / len(pcts)) if pcts else 0.0,
        "tv": tv, "ret": (tv / CAP * 100 - 100) if tv else 0.0,
        "expo": (100.0 * pos_cost / tv) if tv else 0.0, "pos": len(pos) if isinstance(pos, dict) else 0,
        "avgw": (sum(pnl_of(r) for r in wins) / len(wins)) if wins else 0.0,
        "avgl": (sum(pnl_of(r) for r in sells if pnl_of(r) <= 0) / max(1, len(sells) - len(wins))),
    })

# 主 sim
ts = [r for r in trades_of("data/sim_trades.json") if d10(r) >= "2026-08-12"]
sst = load("data/sim_state.json", {}) or {}
s_tv = float(sst.get("total_value") or sst.get("total") or 0)
s_sells = [r for r in ts if str(r.get("action")) == "sell"]
s_wins = [r for r in s_sells if pnl_of(r) > 0]

print("%-14s %4s %4s %4s %12s %7s %8s %10s %8s %6s %9s %9s" %
      ("账户", "笔数", "买", "卖", "已实现", "胜率", "E/笔%", "期末总资产", "收益率", "暴露%", "平均盈", "平均亏"))
tot_real = 0.0
tot_val = 0.0
for r in rows:
    tot_real += r["real"]; tot_val += r["tv"]
    print("%-14s %4d %4d %4d %12.2f %6.1f%% %8.2f %11.0f %8.2f%% %6.1f %9.0f %9.0f" %
          (r["name"], r["n"], r["buy"], r["sell"], r["real"], r["wr"], r["E_pct"], r["tv"], r["ret"], r["expo"], r["avgw"], r["avgl"]))
print("%-14s %4d %4d %4d %12.2f %6.1f%% %8.2f %11.0f %8.2f%%" %
      ("主sim", len(ts), len([r for r in ts if r.get("action") == "buy"]), len(s_sells),
       sum(pnl_of(r) for r in s_sells), (100.0 * len(s_wins) / len(s_sells)) if s_sells else 0,
       (sum([pct_of(r) for r in s_sells if pct_of(r) is not None] or [0]) / max(1, len([1 for r in s_sells if pct_of(r) is not None]))),
       s_tv, (s_tv / CAP * 100 - 100) if s_tv else 0))
print("-" * 84)
print("5 画像合计: 期末 %,.0f / 本金 5,000,000 → %+.2f%% | 已实现合计 %,.2f".replace(",", "")
      % (tot_val, (tot_val / 5_000_000 * 100 - 100), tot_real))

print()
print("=" * 84)
print("B. 分段：8月 vs 9月（月度已实现盈亏 / 笔数）")
print("=" * 84)
print("%-14s %22s %22s" % ("账户", "8月(13~31)", "9月(01~30)"))
for name in AGENTS + ["主sim"]:
    f = "data/sim_trades.json" if name == "主sim" else "data/agent_%s/trades.json" % name
    t = trades_of(f)
    for lab, lo, hi in (("8月(13~31)", "2026-08-13", "2026-09-01"), ("9月(01~30)", "2026-09-01", "2026-10-01")):
        pass
    def seg(lo, hi):
        ss = [r for r in t if str(r.get("action")) == "sell" and lo <= d10(r) < hi]
        return len(ss), sum(pnl_of(r) for r in ss)
    a = seg("2026-08-13", "2026-09-01"); b = seg("2026-09-01", "2026-10-01")
    print("%-14s %8d笔 %12.0f %8d笔 %12.0f" % (name, a[0], a[1], b[0], b[1]))

print()
print("=" * 84)
print("C. 策略层（beliefs.json: alpha/beta/trades）+ 退出路径")
print("=" * 84)
b = load("data/beliefs.json", {}) or {}
print("%-22s %7s %7s %8s %s" % ("策略", "alpha", "beta", "trades", "最后更新"))
for k, v in sorted(b.items(), key=lambda x: -float(x[1].get("trades") or 0)):
    print("%-22s %7s %7s %8s %s" % (k, v.get("alpha"), v.get("beta"), v.get("trades"), v.get("last_update")))

reasons = Counter()
reason_pnl = defaultdict(float)
strat_cnt = Counter()
for name in AGENTS + ["主sim"]:
    f = "data/sim_trades.json" if name == "主sim" else "data/agent_%s/trades.json" % name
    for r in trades_of(f):
        if str(r.get("action")) != "sell":
            continue
        rr = str(r.get("reason") or "?")
        key = rr.split("@")[0].split(":")[0].split("|")[0].strip() or "?"
        reasons[key] += 1
        reason_pnl[key] += pnl_of(r)
        st_ = r.get("strategy") or r.get("strat")
        if st_:
            strat_cnt[str(st_)] += 1
print("\n退出路径:")
for k, v in reasons.most_common(12):
    print("  %-24s %4d 笔  盈亏合计 %10.0f" % (k, v, reason_pnl[k]))
if strat_cnt:
    print("\n按 strategy 字段统计成交:", dict(strat_cnt.most_common(10)))

print()
print("=" * 84)
print("D. 跨画像重叠审计（同(日,票) 多画像买入）")
print("=" * 84)
byday = defaultdict(lambda: defaultdict(list))
for name in AGENTS:
    for r in trades_of("data/agent_%s/trades.json" % name):
        if str(r.get("action")) == "buy":
            byday[d10(r)][str(r.get("code"))].append(name)
ov = {d: {c: n for c, n in cs.items() if len(n) > 1} for d, cs in byday.items()}
ov = {d: cs for d, cs in ov.items() if cs}
print("重叠组数: %d（买入总组数 %d）" % (sum(len(v) for v in ov.values()), sum(len(v) for v in byday.values())))
for d in sorted(ov)[-8:]:
    print("  %s %s" % (d, {c: n for c, n in list(ov[d].items())[:3]}))

print()
print("=" * 84)
print("E. 净值曲线 / 最大回撤（agent_comparison.json 快照序列）")
print("=" * 84)
cmp_ = load("data/agent_comparison.json", [])
if isinstance(cmp_, dict):
    cmp_ = cmp_.get("snapshots") or cmp_.get("history") or []
print("快照数: %d" % len(cmp_))
if cmp_:
    t0 = str(cmp_[0].get("time"))[:16]; t1 = str(cmp_[-1].get("time"))[:16]
    print("区间: %s ~ %s" % (t0, t1))
    series = defaultdict(list)
    for s in cmp_:
        ags = s.get("agents") or {}
        tot = 0.0
        for nm, v in ags.items():
            tv = float(v.get("total_value") or 0)
            series[nm].append((str(s.get("time"))[:10], tv))
            tot += tv
        series["合计"].append((str(s.get("time"))[:10], tot))
    print("%-14s %11s %11s %9s %9s" % ("账户", "期初", "期末", "峰值回撤", "波动"))
    for nm in AGENTS + ["合计"]:
        ss = [v for _, v in series.get(nm, []) if v > 0]
        if not ss:
            continue
        peak = ss[0]; mdd = 0.0
        for v in ss:
            peak = max(peak, v)
            mdd = min(mdd, v / peak - 1)
        print("%-14s %11.0f %11.0f %8.2f%% %8.2f%%" % (nm, ss[0], ss[-1], mdd * 100, (ss[-1] / ss[0] - 1) * 100))

print()
print("=" * 84)
print("F. 基准：上证 / 沪深300（market.db 只读）")
print("=" * 84)
try:
    con = sqlite3.connect("file:D:/MarketData/market.db?mode=ro", uri=True)
    for code, nm in (("sh000001", "上证指数"), ("sh000300", "沪深300")):
        rs = list(con.execute(
            "select ts,close from kline_daily where code=? and ts>=? and ts<=? order by ts",
            (code, "2026-08-12", "2026-09-30")))
        if rs:
            print("  %-8s %s(%.2f) → %s(%.2f)  %+.2f%%" %
                  (nm, rs[0][0], rs[0][1], rs[-1][0], rs[-1][1], (rs[-1][1] / rs[0][1] - 1) * 100))
        else:
            print("  %-8s market.db 无数据" % nm)
    con.close()
except Exception as e:
    print("  基准读取失败:", e)

print()
print("=" * 84)
print("G. 买点追高核验（买入价 vs 当日涨幅，需 kline）：用 trades 内 pnl_pct 反推 + 买入日计数")
print("=" * 84)
buys_by_day = Counter()
for name in AGENTS + ["主sim"]:
    f = "data/sim_trades.json" if name == "主sim" else "data/agent_%s/trades.json" % name
    for r in trades_of(f):
        if str(r.get("action")) == "buy":
            buys_by_day[d10(r)] += 1
print("买入日分布(前12):", buys_by_day.most_common(12))
print("买入总笔数:", sum(buys_by_day.values()), "| 交易日数:", len(buys_by_day))
now = None
