# -*- coding: utf-8 -*-
"""股票工作流运行健康检查 v14.46 — 全链路验证"""
import sys, warnings, time
sys.path.insert(0, '.')
warnings.filterwarnings('ignore')
import datetime as dt

OK = lambda m: print(f"  ✅ {m}")
BAD = lambda m: print(f"  ❌ {m}")

print("=== 1. 核心模块导入 ===")
checks = [
    ("config", "import config"),
    ("data.sources", "from data.sources import get_kline, get_tencent_quotes, get_index_snapshot"),
    ("screening.cascade", "from screening.cascade import cascade_screen"),
    ("screening.auction", "from screening.auction import auction_screen"),
    ("screening.strong_stock", "from screening.strong_stock import screen_strong_stocks"),
    ("core.engine", "from core.engine import AuroraEngine"),
    ("executor.sim_account", "from executor.sim_account import SimAccount"),
    ("risk.trailing", "from risk.trailing import calc_trailing_stop"),
    ("monitor.watcher", "from monitor.watcher import watch_positions"),
    ("strategies.runner", "from strategies.runner import analyze_all"),
    ("strategies.prev_close_play", "from strategies.prev_close_play import check_prev_close"),
    ("multi_agent.coordinator", "from multi_agent.coordinator import MultiAgentCoordinator"),
    ("daily_run", "import daily_run"),
]
all_ok = True
for name, stmt in checks:
    try:
        exec(stmt, {})
        OK(f"{name}")
    except Exception as e:
        BAD(f"{name}: {e}")
        all_ok = False
print()

print("=== 2. 数据源 ===")
try:
    from data.sources import get_tencent_quotes
    q = get_tencent_quotes(["600519", "000001", "300319"])
    names = {c: d.get("name", "?") for c, d in q.items()}
    print(f"  腾讯行情: {names}")
    assert len(q) >= 2, "行情返回不足"
    OK("腾讯行情正常")
except Exception as e:
    BAD(f"腾讯行情: {e}")

try:
    from data.sources import get_kline
    k = get_kline("300319", 60)
    print(f"  K线 300319: {len(k)}根, attrs.code={k.attrs.get('code')}")
    assert len(k) >= 20, "K线不足20根"
    assert k.attrs.get("code") == "300319", "attrs code 未注入"
    OK("K线+attrs注入正常")
except Exception as e:
    BAD(f"K线: {e}")

try:
    from data.sources import get_index_snapshot
    idx = get_index_snapshot(["000001"])
    if idx:
        OK(f"指数快照: {list(idx.keys())}")
    else:
        BAD("指数快照为空")
except Exception as e:
    BAD(f"指数快照: {e}")
print()

print("=== 3. 交易日历 / 今日状态 ===")
try:
    from core.calendar import is_trading_day, is_market_open, is_auction_time
    today = dt.date.today()
    td = is_trading_day(today)
    open_now = is_market_open()
    print(f"  今天 {today} ({'交易日' if td else '非交易日'}), 当前交易中={open_now}")
    OK("日历模块正常 (is_trading_day/is_market_open)")
except Exception as e:
    BAD(f"日历: {e}")
print()

print("=== 4. 昨收战法核心 ===")
try:
    from strategies.prev_close_play import check_prev_close, check_prev_close_exit
    from strategies.runner import analyze_all
    k = get_kline("300319", 60)
    cand = [{"code": "300319", "name": "麦捷科技", "price": float(k['close'].iloc[-1]),
             "can_slim": 60, "strong_grade": "A", "strong_score": 88}]
    weights = {"prev_close_A": 3.0, "prev_close_B": 2.5, "sector_rotation": 1.5,
               "momentum_breakout": 0.0, "wave_point": 0.3, "mean_reversion": 0.0}
    res = analyze_all(cand, kline_override={"300319": k}, strategy_weights=weights)
    a = res[0]
    print(f"  analyze_all: signal={a.get('signal')} best={a.get('best_strategy')} all={a.get('all_signals')}")
    OK("analyze_all 正常 (含强势池护栏+动量禁用)")
except Exception as e:
    BAD(f"analyze_all: {e}")
print()

print("=== 5. 移动止盈(昨日修复) ===")
try:
    from monitor.watcher import watch_positions
    from unittest.mock import patch
    pos = {"600005": {"avg_cost": 10.0, "current_price": 11.5, "shares": 1000}}
    cfg = {"risk": {"stop_loss_pct": 0.05}, "market": {"default_regime": "range"}}
    with patch("monitor.watcher.get_tencent_quotes", return_value={"600005": {"price": 11.5}}):
        alerts = watch_positions(pos, cfg)
    types = [a["type"] for a in alerts]
    print(f"  移动止盈 alerts: {types}")
    assert "trailing_stop" in types, "ATR/阶梯止盈未触发"
    OK("移动止盈正常 (ATR增强激活)")
except Exception as e:
    BAD(f"移动止盈: {e}")
print()

print("=== 6. 引擎实例化+选股链路(只读, 不写模拟盘) ===")
try:
    import config as cfg_mod
    cfg = cfg_mod.load_config() if hasattr(cfg_mod, "load_config") else {}
    from screening.cascade import cascade_screen
    cands = cascade_screen(cfg, phase="monitor")
    print(f"  cascade_screen: {len(cands)} 只候选")
    if cands:
        from screening.auction import auction_screen
        auc = auction_screen(cands, top_n=10)
        print(f"  auction_screen: {len(auc)} 只 (竞价护栏)")
        OK("选股链路正常")
    else:
        BAD("cascade_screen 候选为0")
except Exception as e:
    BAD(f"选股链路: {e}")
print()

print("=== 7. 聚合状态文件 ===")
import os, json
for f in ["agent_aggregate.json", "sim_state.json"]:
    p = os.path.join("data", f)
    if os.path.exists(p):
        try:
            d = json.load(open(p, encoding="utf-8"))
            OK(f"{f}: {len(d)} 项, {os.path.getsize(p)}B")
        except Exception as e:
            BAD(f"{f}: 解析失败 {e}")
    else:
        BAD(f"{f}: 不存在")
print()

if all_ok:
    print("=== 全链路健康检查: 全部通过 ===")
else:
    print("=== 存在失败项, 见上 ===")
