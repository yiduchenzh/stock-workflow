#!/usr/bin/env python
"""微结构执行增强模块 — 独立测试"""
import sys, os, math, random, json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from executor.microstructure import (
    AlmgrenChrissImpact, VWAPExecutionPlan, TWAPExecutionPlan,
    OrderTypeSelector, MicrostructureSlippage, create_microstructure,
    _calc_time_factor, _get_ac_params,
)

PASS, FAIL = 0, 0
def check(name, cond, detail=""):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  OK {name}")
    else: FAIL += 1; print(f"  FAIL {name}  -- {detail}")

# ===== 1. Almgren-Chriss =====
def test_ac():
    print("\n[1] AlmgrenChrissImpact")
    ac = AlmgrenChrissImpact(avg_daily_turnover=5e8, annual_volatility=0.30)
    p = ac.permanent_impact(100_000, 10.0, 5_000_000)
    t = ac.temporary_impact(100_000, 10.0, 5_000_000)
    check("permanent>0", p > 0); check("temporary>0", t > 0)
    check("total=perm+temp", abs(ac.total_impact(100_000,10,5e6)-(p+t))<1e-10)
    check("large>small", ac.total_impact(500_000,10,5e6) > ac.total_impact(10_000,10,5e6))
    ac_h = AlmgrenChrissImpact(1e10, 0.30)
    ac_l = AlmgrenChrissImpact(5e7, 0.30)
    check("liquid<illiquid", ac_h.total_impact(100_000,10,5e7) < ac_l.total_impact(100_000,10,5e5))
    r = ac.impact_as_slippage(100_000, 10.0, 5_000_000, True)
    for f in ["slippage_pct","permanent_pct","temporary_pct","fill_price"]:
        check(f"has_{f}", f in r)
    check("buy_fill>10", r["fill_price"] > 10.0)
    r2 = ac.impact_as_slippage(100_000, 10.0, 5_000_000, False)
    check("sell_fill<10", r2["fill_price"] < 10.0)
    check("zero_vol=0", ac.total_impact(100_000, 10.0, 0) == 0.0)
    for n, v in [("ultra",1e11),("high",5e9),("mid",5e8),("low",5e7),("illi",1e6)]:
        check(f"tier_{n}", "eta" in _get_ac_params(v))

# ===== 2. VWAP =====
def test_vwap():
    print("\n[2] VWAP")
    v = VWAPExecutionPlan()
    now = datetime.now().replace(hour=9, minute=30, second=0, microsecond=0)
    end = now.replace(hour=15, minute=0, second=0, microsecond=0)
    p = v.generate_plan(100_000, start_time=now, end_time=end)
    check("nonempty", len(p)>0); check("total", sum(x["shares"] for x in p)==100_000)
    check("min>=100", min(x["shares"] for x in p)>=100)
    c = [x["cumulative_pct"] for x in p]
    check("cum_ascending", all(c[i]<=c[i+1] for i in range(len(c)-1)))
    check("last_100pct", abs(p[-1]["cumulative_pct"]-100)<1e-6)
    vwap = v.estimate_vwap_price(p, [random.uniform(9.5,10.5) for _ in p])
    check("vwap_reasonable", 9<vwap<11)
    np = v.generate_plan(100_000, start_time=now, end_time=end, noise=0.3)
    check("noise_total", sum(x["shares"] for x in np)==100_000)
    v2 = VWAPExecutionPlan({(9,30):0.5,(10,0):0.3,(11,0):0.2})
    cp = v2.generate_plan(10_000, start_time=now, end_time=now.replace(hour=11, minute=30))
    check("custom_total", sum(x["shares"] for x in cp)==10_000)

# ===== 3. TWAP =====
def test_twap():
    print("\n[3] TWAP")
    t = TWAPExecutionPlan()
    now = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
    end = now.replace(hour=11, minute=0, second=0, microsecond=0)
    p = t.generate_plan(50_000,10,start_time=now,end_time=end)
    check("nonempty", len(p)>0); check("total", sum(x["shares"] for x in p)==50_000)
    w = [x["weight"] for x in p]; check("uniform", max(w)-min(w)<0.01)
    c = [x["cumulative_pct"] for x in p]
    check("cum_ascending", all(c[i]<=c[i+1] for i in range(len(c)-1)))
    check("last_100pct", abs(p[-1]["cumulative_pct"]-100)<1e-6)
    p2 = t.generate_plan(50_000,interval_minutes=5,start_time=now,end_time=end)
    check("interval_total", sum(x["shares"] for x in p2)==50_000)
    p3 = t.generate_plan(1_000,20,100,start_time=now,end_time=end)
    check("small_total", sum(x["shares"] for x in p3)==1_000)

# ===== 4. OrderTypeSelector =====
def test_selector():
    print("\n[4] OrderTypeSelector")
    s = OrderTypeSelector()
    r = s.select(10_000,10,1e10,5e7,0.01,True)
    check("liquid_small->market", r["order_type"]=="market"); check("confidence", 0<=r["confidence"]<=1)
    r2 = s.select(300_000,10,5e6,500_000,0.05,True,current_time=datetime.now().replace(hour=10, minute=30))
    check("illiquid_large->limit", r2["order_type"]=="limit", f"got={r2['order_type']} reason={r2['reason']}")
    r3 = s.select(10_000,10,5e8,5e6,True,True,current_time=datetime.now().replace(hour=14, minute=55))
    check("urgency>0.5", r3["factors"]["urgency_score"]>0.5)
    for f in ["order_type","confidence","factors","reason","limit_price","limit_offset_bps"]:
        check(f"has_{f}", f in r3)
    br = s.select(50_000,10,5e8,5e6,0.02,True)
    sr = s.select(50_000,10,5e8,5e6,0.02,False)
    check("direction_matters", br["confidence"] != sr["confidence"])

# ===== 5. MicrostructureSlippage =====
def test_ms():
    print("\n[5] MicrostructureSlippage")
    ms = MicrostructureSlippage(5e8,5_000_000,0.30,True)
    # Use large volume to ensure fill_price measurably differs from 10.0
    r = ms.compute_slippage(500_000,10,True, mcap_hundred_million=200)
    check("slip>0", r["slippage"]>0); check("buy_fill>10", r["fill_price"]>10, f"fill={r['fill_price']}")
    check("has_impact_detail", "impact_detail" in r); check("has_order_advice", "order_type_advice" in r)
    r2 = ms.compute_slippage(500_000,10,False, mcap_hundred_million=200)
    check("sell_fill<10", r2["fill_price"]<10, f"fill={r2['fill_price']}")
    ms_big = MicrostructureSlippage(1e10,5e7)
    big_s = ms_big.compute_slippage(100_000,10,True, mcap_hundred_million=1000)["slippage"]
    small_s = ms.compute_slippage(100_000,10,True, mcap_hundred_million=200)["slippage"]
    check("big_lower_slip", big_s < small_s, f"big={big_s} small={small_s}")
    ms_n = MicrostructureSlippage(5e8,5e6,use_ac_model=False)
    check("noac_slip>0", ms_n.compute_slippage(10_000,10,True)["slippage"]>0)
    check("noac_impact=0", ms_n.compute_slippage(10_000,10,True)["ac_impact"]==0)
    ms.update_market_params(avg_daily_turnover=1e10)
    check("update_params", ms._avg_daily_turnover==1e10)
    check("ac_synced", ms.ac.eta==_get_ac_params(1e10)["eta"])
    big_s2 = ms.compute_slippage(1_000_000,10,True)["slippage"]
    small_s2 = ms.compute_slippage(1_000,10,True)["slippage"]
    check("large>small", big_s2 > small_s2, f"large={big_s2} small={small_s2}")

# ===== 6. 集成 =====
def test_integration():
    print("\n[6] SimAccount+Microstructure")
    from executor.sim_account import SimAccount, STATE, TRADES

    # 清除持久化状态避免交叉影响
    if STATE.exists(): STATE.unlink()
    if TRADES.exists(): TRADES.unlink()

    # 用1000万资金确保大单测试通过
    acct = SimAccount(10_000_000, {"use_microstructure":True,"microstructure":{"avg_daily_turnover":5e8,"daily_volume_shares":5_000_000,"annual_volatility":0.30}})
    acct.register_stock_market_params("600519",8e9,3_000_000,0.25,20000)
    acct.register_stock_market_params("000001",3e8,30_000_000,0.35,200)
    check("enabled", acct._use_microstructure); check("cache_600519", "600519" in acct._stock_micro_cache)

    # 买入茅台(大盘), 大单使AC冲击可测量
    r1 = acct.buy("600519",150,100_000,"test")
    check("buy_moutai", r1["success"], f"error={r1.get('error','')}")
    if r1["success"]:
        for k in ["slippage_pct","time_factor","ac_impact_pct","order_type"]:
            check(f"trade_has_{k}", k in r1["trade"])

    # 买入小盘股
    r2 = acct.buy("000001",10,100_000,"test")
    check("buy_xiaopan", r2["success"], f"error={r2.get('error','')}")

    if r1["success"] and r2["success"]:
        slip_m = r1["trade"]["slippage_pct"]
        slip_x = r2["trade"]["slippage_pct"]
        check("moutai_slip<xiaopan_slip", slip_m < slip_x, f"moutai={slip_m}% xiaopan={slip_x}%")

    # 注入昨日持仓测试卖出
    acct.positions["000888"] = {"shares":1000,"avg_cost":10.0,"current_price":10.5,"entry_date":"2024-01-01"}
    r3 = acct.sell("000888",10.5,500,"测试卖出")
    check("sell_ok(T+1)", r3["success"], f"error={r3.get('error','')}")
    if r3["success"]:
        check("sell_has_slippage", "slippage_pct" in r3["trade"])

    info = acct.get_account_info()
    check("account_info", "cash" in info and "positions" in info)

    # Legacy模式: 清除状态后创建新账户
    if STATE.exists(): STATE.unlink()
    if TRADES.exists(): TRADES.unlink()
    legacy = SimAccount(1_000_000, {"use_microstructure":False})
    lb = legacy.buy("600519",150,1000)
    check("legacy_buy", lb["success"], f"result={lb}")

    # 资金不足
    if STATE.exists(): STATE.unlink()
    if TRADES.exists(): TRADES.unlink()
    poor = SimAccount(1000, {"use_microstructure":False})
    poor_r = poor.buy("600519",150,10000)
    check("poor_insufficient", not poor_r["success"] and "error" in poor_r, f"result={poor_r}")

    # 清理
    if STATE.exists(): STATE.unlink()
    if TRADES.exists(): TRADES.unlink()

# ===== 7. time_factor =====
def test_tf():
    print("\n[7] _calc_time_factor")
    for (h,m),exp,label in [((9,35),2.0,"open"),((10,30),1.0,"mid_am"),((11,15),0.8,"pre_lunch"),((13,5),1.8,"post_lunch"),((14,45),2.5,"close"),((3,0),1.0,"off_hours")]:
        val = _calc_time_factor(datetime.now().replace(hour=h, minute=m))
        check(f"{label}~={exp}", abs(val-exp)<0.15, f"got={val}")
    check("default>0", _calc_time_factor()>0)

# ===== 8. factory =====
def test_factory():
    print("\n[8] create_microstructure")
    ms = create_microstructure(1e9,10_000_000,0.25)
    check("instance", isinstance(ms, MicrostructureSlippage))
    check("params", ms._avg_daily_turnover==1e9)

if __name__ == "__main__":
    print("="*50+"\n 微结构执行增强模块 -- 测试\n"+"="*50)
    test_ac(); test_vwap(); test_twap(); test_selector()
    test_ms(); test_tf(); test_factory(); test_integration()
    total = PASS+FAIL; print(f"\n{PASS}/{total} 通过, {FAIL}/{total} 失败")
    sys.exit(1 if FAIL else 0)
