import sys, json, time, logging
logging.basicConfig(level=logging.WARNING, format="%(levelname)s|%(name)s|%(message)s", stream=sys.stdout)
sys.path.insert(0, "D:\\Hermes Agent CN Desktop\\stock-workflow")
from data.sources import (
    get_tencent_quotes, get_kline, get_kline_period, get_real_stock_list,
    get_sector_ranking, get_top_sectors, get_top_flow_stocks,
    get_market_breadth, get_index_snapshot, _sina_stock_list,
)
from data.northbound import get_northbound_flow
import pandas as pd
PASS, FAIL, RESULTS = 0, 0, []
def test(label, fn):
    global PASS, FAIL
    t1 = time.time()
    try:
        r = fn(); el = time.time() - t1
        if r is None or (isinstance(r,(dict,list)) and len(r)==0) or (isinstance(r,pd.DataFrame) and len(r)==0):
            st, real, pv = "FAIL", "NO", str(type(r).__name__)+"(empty)"; FAIL += 1
        else:
            st, real = "PASS", "YES"; PASS += 1
            if isinstance(r,dict): pv = json.dumps({k:str(r[k])[:60] for k in list(r.keys())[:3]}, ensure_ascii=False)
            elif isinstance(r,list): pv = json.dumps(r[:3], ensure_ascii=False)[:150]
            elif isinstance(r,pd.DataFrame): pv = f"DF({len(r)}r,{list(r.columns)})"
            else: pv = str(r)[:150]
    except Exception as e:
        el = time.time()-t1; st, real = "FAIL","NO"; pv = f"{type(e).__name__}:{str(e)[:80]}"; FAIL += 1; r=None
    RESULTS.append(f"| {label:>2} | {st:<6} | {pv:<60} | {el:.2f}s | {real:<5} |")
    print(f"[{st}] #{label} ({el:.2f}s): {pv[:60]}")
    return r
print("="*90); print("R18 DATA SOURCE RELIABILITY AUDIT"); print("="*90)
test("1", lambda: get_tencent_quotes(["000001","000002","600519"]))
test("2", lambda: get_kline("000001",60))
test("3", lambda: get_kline_period("000001","week",12))
test("4", lambda: get_kline_period("000001","month",24))
test("5", lambda: get_real_stock_list())
test("6", lambda: get_sector_ranking(10))
test("7", lambda: get_top_sectors(5))
test("8", lambda: get_top_flow_stocks(200))
test("9", lambda: get_northbound_flow())
test("10", lambda: get_market_breadth())
test("11", lambda: get_index_snapshot(["000001","399001","399006"]))
test("12", lambda: _sina_stock_list())
print("\n"+"="*90); print(f"SUMMARY: {PASS} PASSED, {FAIL} FAILED"); print("="*90)
print(f"{'#':>2} | {'Status':<6} | {'Data Sample':<60} | {'Time':<6} | {'Real?':<5}"); print("-"*90)
for r in RESULTS: print(r)
print("-"*90); print(f"TOTAL: {PASS+FAIL} endpoints, {PASS} passed, {FAIL} failed")
