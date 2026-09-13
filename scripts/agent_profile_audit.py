# -*- coding: utf-8 -*-
"""逐Agent分析: 画像 vs 实际选股/交易一致性"""
import sys, json
sys.path.insert(0, '.')
from pathlib import Path
from collections import defaultdict

ROOT = Path(r"D:\Hermes Agent CN Desktop\stock-workflow\data")

def load(name):
    p = ROOT / f"agent_{name}" / "trades.json"
    if not p.exists(): return []
    raw = p.read_bytes()
    for enc in ("utf-8", "gbk"):
        try: return json.loads(raw.decode(enc))
        except: continue
    return []

# 画像速查
PROFILES = {
    "上班族中短线": {"周期": "3-10天", "风格": "蓝筹中大盘/均线突破+缠论三买", "信号偏好": "momentum2.0/wave1.5/sector0.5", "风控": "止损5%/仓位20%"},
    "短线狙击手": {"周期": "1-3天", "风格": "中小盘涨停热点/昨收战法", "信号偏好": "prev_close_A3.0/B2.5/首板2.0", "风控": "止损5%/仓位28%"},
    "趋势跟踪者": {"周期": "10-30天", "风格": "大盘趋势周线多头", "信号偏好": "momentum2.0/ma_breakout1.5/wave1.5/chan_buy", "风控": "止损7%/仓位20%"},
    "新手入门": {"周期": "3-10天", "风格": "大市值低波动", "信号偏好": "momentum1.0/wave1.0", "风控": "止损3%/仓位10%"},
    "价值投资者": {"周期": "30天+", "风格": "沪深300低PE高ROE", "信号偏好": "momentum1.5/mean_rev0.5/ma_breakout0.5", "风控": "止损10%/仓位25%"},
}

for agent, profile in PROFILES.items():
    trades = load(agent)
    print(f"\n{'='*70}")
    print(f"【{agent}】画像: {profile['风格']} | 周期{profile['周期']} | {profile['信号偏好']}")
    print(f"  风控: {profile['风控']}")
    buys = [t for t in trades if t["action"] == "buy"]
    sells = [t for t in trades if t["action"] == "sell"]
    print(f"  交易: 买{len(buys)} 卖{len(sells)}")
    for t in buys:
        ctx = t.get("context") or {}
        strat = ctx.get("strategy", t.get("reason", "?"))
        print(f"    BUY {t.get('code')} {t.get('shares')}股 @{t.get('price')} 策略={strat} "
              f"score={ctx.get('score')} regime={ctx.get('regime')} @{t.get('time','')[:16]}")
    for t in sells:
        strat = t.get("buy_context", {}).get("strategy", t.get("reason", "?"))
        print(f"    SELL {t.get('code')} {t.get('shares')}股 @{t.get('price')} "
              f"pnl={t.get('pnl_pct',0):+.1f}% 原策略={strat} 原因={t.get('reason','')[:30]} @{t.get('time','')[:16]}")

# 各账户持仓特征检查: 是否符合画像的市值/PE约束
print(f"\n{'='*70}")
print("【持仓是否符合画像的池子约束】")
try:
    from data.sources import get_tencent_quotes
    all_codes = set()
    for agent in PROFILES:
        sp = ROOT / f"agent_{agent}" / "state.json"
        if sp.exists():
            d = json.loads(sp.read_bytes().decode("utf-8", errors="replace"))
            all_codes.update(d.get("positions", {}).keys())
    if all_codes:
        q = get_tencent_quotes(list(all_codes))
        for agent in PROFILES:
            sp = ROOT / f"agent_{agent}" / "state.json"
            if not sp.exists(): continue
            d = json.loads(sp.read_bytes().decode("utf-8", errors="replace"))
            pos = d.get("positions", {})
            cfg_map = {
                "上班族中短线": ("蓝筹中大盘", 50, 20000), "短线狙击手": ("中小盘", 20, 8000),
                "趋势跟踪者": ("大盘", 100, 50000), "新手入门": ("大市值", 100, 20000),
                "价值投资者": ("沪深300低PE", 200, 50000),
            }
            name, min_mcap, max_mcap = cfg_map[agent]
            for code in pos:
                qd = q.get(code, {})
                mcap = qd.get("mcap", 0) or 0  # 亿
                pe = qd.get("pe", 0) or 0
                ok = "✅" if (not min_mcap or mcap >= min_mcap) and (not max_mcap or mcap <= max_mcap) else "❌"
                print(f"  {agent} {code}: 市值{mcap:.0f}亿 PE={pe:.0f} {ok} (约束{min_mcap}-{max_mcap}亿)")
except Exception as e:
    print(f"  行情获取失败: {e}")
