#!/usr/bin/env python
"""
全链路5年回测(2021.07-2026.06) vs 沪深300
SimAccount真实费用，输出PF/胜率/年化/MaxDD/超额收益
"""
import sys, os, json, time, math
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

PROJ = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJ))

TEST_STOCKS = [
    "600519","600036","300750","000333","601318","000858",
    "002594","600887","600585","601166","600030","600276",
    "601899","601012","603259","300059","300760","603288",
]
STOCK_NAMES = {
    "600519":"贵州茅台","600036":"招商银行","300750":"宁德时代",
    "000333":"美的集团","601318":"中国平安","000858":"五粮液",
    "002594":"比亚迪","600887":"伊利股份","600585":"海螺水泥",
    "601166":"兴业银行","600030":"中信证券","600276":"恒瑞医药",
    "601899":"紫金矿业","601012":"隆基绿能","603259":"药明康德",
    "300059":"东方财富","300760":"迈瑞医疗","603288":"海天味业",
}
S = "2021-07-01"
E = datetime.now().strftime("%Y-%m-%d")
CAP = 1_000_000
MP = 100
MXP = 5
STOP = 0.07
RR = 2.8

def _prefix(code):
    return f"sh{code}" if code.startswith(("6","9")) else f"sz{code}"

def load_data_tencent(code, days=1200):
    import requests
    pfx = _prefix(code)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={pfx},day,,,{days},qfq"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        data = r.json().get("data", {}).get(pfx, {})
        kline = data.get("qfqday", []) or data.get("day", [])
        if not kline: return pd.DataFrame()
        rows = [{"date": d[0], "open": float(d[1]), "close": float(d[2]),
                 "high": float(d[3]), "low": float(d[4]), "volume": float(d[5])} for d in kline]
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        return df
    except Exception as e:
        print(f"  [WARN] {code} fail: {e}")
        return pd.DataFrame()

def load_hs300_daily():
    import requests
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000300,day,,,1200,qfq"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        data = r.json().get("data", {}).get("sh000300", {})
        kline = data.get("qfqday", []) or data.get("day", [])
        if not kline: return pd.DataFrame()
        rows = [{"date": d[0], "close": float(d[2])} for d in kline]
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        return df
    except Exception as e:
        print(f"  [WARN] HS300 fail: {e}")
        return pd.DataFrame()

def get_price(kc, co, dt):
    df = kc.get(co)
    if df is None: return None
    r = df[df["date"] == dt]
    if r.empty:
        m = df[df["date"] <= dt]
        if m.empty: return None
        r = m.iloc[-1:]
    return float(r["close"].iloc[-1]) if not r.empty else None

def get_kline_up_to(kc, co, dt, n=120):
    df = kc.get(co)
    if df is None: return pd.DataFrame()
    s = df[df["date"] <= dt].tail(n).copy()
    return s if len(s) >= 30 else pd.DataFrame()

def get_market_regime_simple(kc, dt):
    df = kc.get("000001")
    if df is None: return "range", 50
    m = df[df["date"] <= dt].tail(60)
    if len(m) < 20: return "range", 50
    c = m["close"].values
    ma20 = np.mean(c[-20:])
    ma60 = np.mean(c[-min(60,len(c)):]) if len(c) >= 60 else np.mean(c)
    sc = 50
    for cond in [c[-1] > ma20, c[-1] > ma60, ma20 > ma60]: sc += 10 if cond else 0
    if len(c) >= 5 and c[-1] > c[-5]: sc += 10
    if len(c) >= 20 and c[-1] == max(c[-20:]): sc += 10
    sc = min(100, max(0, sc))
    if sc >= 75: return "bull_strong", sc
    if sc >= 55: return "bull_weak", sc
    if sc >= 45: return "range", sc
    if sc >= 25: return "bear_weak", sc
    return "bear_strong", sc

def calc_annual_return(start_val, end_val, start_date, end_date):
    days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days
    if days <= 0: return 0.0
    total_ret = (end_val / start_val) - 1
    return ((1 + total_ret) ** (365.25 / days) - 1) * 100

def calc_sharpe(returns_list, rf=0.02):
    if not returns_list or len(returns_list) < 2: return 0.0
    arr = np.array(returns_list)
    excess = arr - rf / 252
    if np.std(excess, ddof=1) == 0: return 0.0
    return np.mean(excess) / np.std(excess, ddof=1) * np.sqrt(252)

def run_backtest():
    t0 = time.time()
    print("=" * 70)
    print("  Aurora 全链路5年回测 v3.0 vs 沪深300")
    print(f"  股票池: {len(TEST_STOCKS)}只沪深300蓝筹")
    print(f"  期间: {S} ~ {E}")
    print(f"  初始资金: {CAP:,.0f}")
    print("=" * 70)
    print("\n[Step 1] 加载K线数据...")
    kc = {}; ok = 0
    for co in TEST_STOCKS:
        df = load_data_tencent(co, 1200)
        if df is not None and not df.empty:
            kc[co] = df; ok += 1
            print(f"  OK {co} {STOCK_NAMES.get(co,'')} {len(df)}条 {df['date'].iloc[0]}~{df['date'].iloc[-1]}")
        else:
            print(f"  FAIL {co} {STOCK_NAMES.get(co,'')}")
    sh_df = load_data_tencent("000001", 1200)
    if sh_df is not None and not sh_df.empty:
        kc["000001"] = sh_df
        print(f"  OK 000001(上证) {len(sh_df)}条 {sh_df['date'].iloc[0]}~{sh_df['date'].iloc[-1]}")
    print(f"\n  Result: {ok}/{len(TEST_STOCKS)} OK")
    if ok < 3:
        return {"meta": {"error": "Too few stocks", "note": f"{ok}/{len(TEST_STOCKS)}"}}

    hs300_df = load_hs300_daily()
    hs300_ret, hs300_ann = 0, 0
    if hs300_df is not None and not hs300_df.empty:
        hs300_f = hs300_df[(hs300_df["date"] >= S) & (hs300_df["date"] <= E)]
        if not hs300_f.empty:
            hs300_ret = (float(hs300_f.iloc[-1]["close"])/float(hs300_f.iloc[0]["close"])-1)*100
            hs300_ann = calc_annual_return(float(hs300_f.iloc[0]["close"]), float(hs300_f.iloc[-1]["close"]),
                                            hs300_f.iloc[0]["date"], hs300_f.iloc[-1]["date"])
            print(f"\n  HS300: {hs300_ret:+.2f}% ann={hs300_ann:+.2f}%")
    else:
        print("\n  [WARN] HS300 unavailable")

    print("\n[Step 2] 构建交易日历...")
    al = set()
    for df in kc.values():
        if "date" in df.columns: al.update(df["date"].values)
    al = sorted([d for d in al if S <= d <= E])
    print(f"  {len(al)} trading days ({al[0]} ~ {al[-1]})")
    if len(al) < 60:
        return {"meta": {"error": "Not enough days"}}
    actual_start, actual_end = al[0], al[-1]

    print("\n[Step 3] 运行回测引擎(逐日回放)...")
    from executor.sim_account import SimAccount
    acc = SimAccount(CAP)
    trades = []; daily_ret = []; prev_total = CAP

    for di, dt in enumerate(al):
        if di % 200 == 0 or di == len(al)-1:
            print(f"  [{di/len(al)*100:.0f}%] {di}/{len(al)} {dt} pos:{len(acc.positions)}")
        rg, ms = get_market_regime_simple(kc, dt)
        for co in list(acc.positions.keys()):
            cp = get_price(kc, co, dt)
            if cp is None: continue
            p = acc.positions[co]; ep = p.get("avg_cost", cp)
            if cp <= ep*(1-STOP):
                res = acc.sell(co, cp, p["shares"], "stop")
                if res: trades.append(res["trade"]); continue
            if cp >= ep*(1+RR*STOP):
                res = acc.sell(co, cp, p["shares"], "tp")
                if res: trades.append(res["trade"]); continue
            ed = p.get("entry_date")
            if ed:
                try:
                    ed_dt = datetime.strptime(str(ed)[:10],"%Y-%m-%d")
                    nd = datetime.strptime(dt,"%Y-%m-%d")
                    if (nd-ed_dt).days > 60:
                        res = acc.sell(co, cp, p["shares"], "time")
                        if res: trades.append(res["trade"]); continue
                except: pass
        if rg == "bear_strong" or ms < 30:
            daily_ret.append((acc.total_value-prev_total)/prev_total if prev_total>0 else 0)
            prev_total = acc.total_value; continue
        if len(acc.positions) >= MXP:
            daily_ret.append((acc.total_value-prev_total)/prev_total if prev_total>0 else 0)
            prev_total = acc.total_value; continue
        for co in TEST_STOCKS:
            if co in acc.positions: continue
            k = get_kline_up_to(kc, co, dt)
            if k.empty: continue
            px = float(k["close"].iloc[-1])
            if px <= 0 or px > MP: continue
            try:
                from strategies.runner import analyze_all
                dummy = [{"code":co, "name":STOCK_NAMES.get(co,co), "price":px}]
                rr = analyze_all(dummy, kline_override={co:k}, market_regime=rg)
                if rr and rr[0].get("signal"):
                    rps = px*STOP
                    sh = max(100, int(acc.cash*0.01/rps/100)*100)
                    if sh*px < acc.cash:
                        res = acc.buy(co, px, sh, f"bt5_{rg}")
                        if res:
                            strat = rr[0].get("best_strategy","?")
                            trades.append({"code":co,"entry":px,"shares":sh,"strategy":strat,"date":dt,"action":"buy"})
            except: pass
        daily_ret.append((acc.total_value-prev_total)/prev_total if prev_total>0 else 0)
        prev_total = acc.total_value

    print("\n[Step 4] 收盘平仓...")
    for co in list(acc.positions.keys()):
        cp = get_price(kc, co, actual_end)
        if cp:
            res = acc.sell(co, cp, acc.positions[co]["shares"], "end")
            if res: trades.append(res["trade"])

    print("\n[Step 5] 计算统计指标...")
    close_trades = [t for t in trades if t.get("action")=="sell" or t.get("pnl") is not None]
    n = len(close_trades)
    wins = [t for t in close_trades if t.get("pnl",0) > 0]
    losses = [t for t in close_trades if t.get("pnl",0) <= 0]
    wr = len(wins)/n*100 if n>0 else 0
    tp = sum(t.get("pnl",0) for t in close_trades)
    gp = sum(t.get("pnl",0) for t in wins)
    gl = abs(sum(t.get("pnl",0) for t in losses))
    pf = gp/gl if gl>0 else 0
    avg_win = gp/len(wins) if wins else 0
    avg_loss = gl/len(losses) if losses else 0
    rr_actual = (avg_win/max(avg_loss,1)) if avg_loss>0 else 0
    peak = CAP; cum = CAP; mdd = 0
    for t in close_trades:
        cum += t.get("pnl",0)
        if cum > peak: peak = cum
        dd = (peak-cum)/peak*100
        if dd > mdd: mdd = dd
    final_value = cum
    total_return_pct = (final_value/CAP-1)*100
    ann_pct = calc_annual_return(CAP, final_value, actual_start, actual_end)
    sharpe = calc_sharpe(daily_ret) if len(daily_ret)>1 else 0.0
    calmar = ann_pct/mdd if mdd>0 else 0
    excess_return_pct = total_return_pct-hs300_ret
    excess_ann = ann_pct-hs300_ann
    tracking_error = np.std([r-hs300_ret/len(daily_ret) for r in daily_ret])*np.sqrt(252) if daily_ret and hs300_ret!=0 else 0.001
    information_ratio = excess_ann/tracking_error if tracking_error>0 else 0
    profit_quality = wr*rr_actual/100 if rr_actual>0 else 0

    strat_stats = {}
    for t in close_trades:
        s = t.get("strategy","?"); 
        if s not in strat_stats: strat_stats[s] = {"n":0,"w":0,"pnl":0}
        strat_stats[s]["n"] += 1
        if t.get("pnl",0) > 0: strat_stats[s]["w"] += 1
        strat_stats[s]["pnl"] += t.get("pnl",0)
    stock_pnl = {}
    for t in close_trades:
        c = t.get("code","?")
        if c not in stock_pnl: stock_pnl[c] = {"n":0,"w":0,"pnl":0}
        stock_pnl[c]["n"] += 1
        if t.get("pnl",0) > 0: stock_pnl[c]["w"] += 1
        stock_pnl[c]["pnl"] += t.get("pnl",0)

    result = {
        "meta": {
            "backtest_name": "全链路5年回测 vs 沪深300",
            "engine_version": "Aurora v3.0 + SimAccount",
            "period_actual": f"{actual_start} ~ {actual_end}",
            "period_desired": f"{S} ~ {E}",
            "total_days": (datetime.strptime(actual_end,"%Y-%m-%d")-datetime.strptime(actual_start,"%Y-%m-%d")).days,
            "trade_days": len(al),
            "stock_pool_size": len(TEST_STOCKS),
            "stocks_loaded": ok,
            "capital": CAP,
            "elapsed_seconds": round(time.time()-t0, 1),
            "timestamp": datetime.now().isoformat(),
            "note": ("Tencent API K线最多约1200条(~4.7年). 建议用tushare/akshare获取完整5年数据"),
        },
        "performance": {
            "total_return_pct": round(total_return_pct, 2),
            "annual_return_pct": round(ann_pct, 2),
            "max_drawdown_pct": round(mdd, 2),
            "sharpe_ratio": round(sharpe, 3),
            "calmar_ratio": round(calmar, 3),
            "profit_factor": round(pf, 2),
            "win_rate_pct": round(wr, 1),
            "total_trades": n,
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "avg_win": round(avg_win, 0),
            "avg_loss": round(avg_loss, 0),
            "avg_win_loss_ratio": round(rr_actual, 2),
            "profit_quality_score": round(profit_quality, 2),
            "net_profit": round(tp, 0),
            "final_value": round(final_value, 0),
        },
        "benchmark": {
            "name": "沪深300", "code": "000300",
            "return_pct": round(hs300_ret, 2),
            "annual_return_pct": round(hs300_ann, 2),
        },
        "excess_return": {
            "excess_return_pct": round(excess_return_pct, 2),
            "excess_annual_pct": round(excess_ann, 2),
            "information_ratio": round(information_ratio, 3),
            "alpha_pct": round(excess_ann, 2),
        },
        "per_strategy": {}, "per_stock": {},
    }
    for sn, st in sorted(strat_stats.items(), key=lambda x: -x[1]["pnl"]):
        swr = st["w"]/st["n"]*100 if st["n"]>0 else 0
        result["per_strategy"][sn] = {"trades":st["n"],"wins":st["w"],"win_rate_pct":round(swr,1),"net_pnl":round(st["pnl"],0)}
    for co, st in sorted(stock_pnl.items(), key=lambda x: -x[1]["pnl"]):
        swr = st["w"]/st["n"]*100 if st["n"]>0 else 0
        result["per_stock"][co] = {"name":STOCK_NAMES.get(co,co),"trades":st["n"],"wins":st["w"],"win_rate_pct":round(swr,1),"net_pnl":round(st["pnl"],0)}
    return result

def print_result(result):
    out_path = PROJ / "data" / "bt_5yr_upgrade_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    meta = result.get("meta",{})
    perf = result.get("performance",{})
    bench = result.get("benchmark",{})
    excess = result.get("excess_return",{})
    print("\n" + "="*70)
    print("  全链路5年回测结果 vs 沪深300")
    print("="*70)
    print(f"\n  实际覆盖: {meta.get('period_actual','N/A')}")
    print(f"  目标期间: {meta.get('period_desired','N/A')}")
    print(f"  股票池: {meta.get('stocks_loaded',0)}/{meta.get('stock_pool_size',0)}只蓝筹")
    print(f"  交易日: {meta.get('trade_days',0)}天  耗时: {meta.get('elapsed_seconds',0)}s")
    print(f"\n  {'─'*60}")
    print(f"  {'指标':<18} {'策略':>12} {'沪深300':>12} {'超额':>12}")
    print(f"  {'─'*60}")
    ret = perf.get("total_return_pct",0)
    hs_ret = bench.get("return_pct",0); ex_ret = excess.get("excess_return_pct",ret-hs_ret)
    print(f"  {'总收益率(%)':<18} {ret:>+12.2f} {hs_ret:>+12.2f} {ex_ret:>+12.2f}")
    ann = perf.get("annual_return_pct",0)
    hs_ann = bench.get("annual_return_pct",0); ex_ann = excess.get("excess_annual_pct",ann-hs_ann)
    print(f"  {'年化收益率(%)':<18} {ann:>+12.2f} {hs_ann:>+12.2f} {ex_ann:>+12.2f}")
    print(f"  {'─'*50}")
    print(f"  {'利润因子(PF)':<18} {perf.get('profit_factor',0):>10.2f}")
    print(f"  {'胜率(%)':<18} {perf.get('win_rate_pct',0):>10.1f}")
    print(f"  {'最大回撤(%)':<18} {perf.get('max_drawdown_pct',0):>10.2f}")
    print(f"  {'夏普比率':<18} {perf.get('sharpe_ratio',0):>10.3f}")
    print(f"  {'卡玛比率':<18} {perf.get('calmar_ratio',0):>10.3f}")
    print(f"  {'信息比率':<18} {excess.get('information_ratio',0):>10.3f}")
    print(f"  {'总交易':<18} {perf.get('total_trades',0):>10}")
    print(f"  {'净收益(¥)':<18} {perf.get('net_profit',0):>+10,.0f}")
    print(f"  {'最终价值(¥)':<18} {perf.get('final_value',0):>10,.0f}")
    print(f"  {'盈损比':<18} {perf.get('avg_win_loss_ratio',0):>10.2f}")
    print(f"\n  {'─'*50}")
    print(f"  {'按策略分解':^50}")
    for sn, st in sorted(result.get("per_strategy",{}).items(), key=lambda x: -x[1]["net_pnl"]):
        print(f"  {sn:<20} {st['trades']:3d}tr WR={st['win_rate_pct']:5.1f}% P&L {st['net_pnl']:+8,.0f}")
    print(f"\n  {'─'*50}")
    print(f"  {'按个股分解(TOP5)':^50}")
    for i,(co,st) in enumerate(sorted(result.get("per_stock",{}).items(), key=lambda x: -x[1]["net_pnl"])):
        if i>=5: break
        print(f"  {co}({st['name']}): {st['trades']}tr WR={st['win_rate_pct']:.1f}% P&L {st['net_pnl']:+8,.0f}")
    if meta.get("note"): print(f"\n  备注: {meta['note']}")
    print(f"\n  [Saved] data/bt_5yr_upgrade_result.json")
    print("="*70)

if __name__ == "__main__":
    st = time.time()
    result = run_backtest()
    print_result(result)
    print(f"\n  总耗时: {time.time()-st:.1f}s")
