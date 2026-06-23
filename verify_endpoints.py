"""
L3 validation: Test every real data source endpoint.
Reports REAL data (not mock), reasonable values, any failures.
"""
import sys, logging, json, time

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s|%(name)s|%(message)s",
    stream=sys.stdout,
)

sys.path.insert(0, "D:\\Hermes Agent CN Desktop\\stock-workflow")

from data.sources import (
    get_tencent_quotes,
    get_kline,
    get_real_stock_list,
    get_sector_ranking,
    get_top_sectors,
    get_top_flow_stocks,
    get_market_breadth,
    get_index_snapshot,
)
from data.northbound import get_northbound_flow

passed = 0
failed = 0
results = []

def check(label, value, condition, detail=""):
    global passed, failed
    ok = bool(condition)
    status = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    else:
        failed += 1
    results.append(f"[{status}] {label}: {detail if detail else str(value)[:200]}")
    print(f"[{status}] {label}")
    if not ok:
        print(f"       -> {str(value)[:300]}")
    return ok

# ── 1 ──
print("\n" + "=" * 70)
print("1. get_tencent_quotes(['000001','000002','600519'])")
print("=" * 70)
try:
    t1 = time.time()
    q = get_tencent_quotes(["000001", "000002", "600519"])
    elapsed = time.time() - t1
    check("Returns dict", q, isinstance(q, dict), f"type={type(q).__name__}")
    check("Has 3 stocks", q, len(q) == 3, f"keys={list(q.keys())}")
    if "000001" in q:
        s = q["000001"]
        check("000001 has price", s, bool(s.get("price")), f"price={s.get('price')}")
        check("000001 has name", s, bool(s.get("name")), f"name={s.get('name')}")
        check("000001 change_pct exists", s, s.get("change_pct") is not None, f"change_pct={s.get('change_pct')}")
    if "600519" in q:
        s = q["600519"]
        check("600519 (Moutai) has price > 100", s, float(s.get("price", 0)) > 100, f"price={s.get('price')}")
    print(f"   Elapsed: {elapsed:.2f}s")
except Exception as e:
    check("1. get_tencent_quotes", e, False, f"EXCEPTION: {e}")

# ── 2 ──
print("\n" + "=" * 70)
print("2. get_kline('000001', 60)")
print("=" * 70)
try:
    t1 = time.time()
    df = get_kline("000001", 60)
    elapsed = time.time() - t1
    import pandas as pd
    check("Returns DataFrame", df, isinstance(df, pd.DataFrame), f"type={type(df).__name__}")
    check("Has rows", df, len(df) > 0, f"rows={len(df)}")
    if len(df) > 0:
        check("Has required columns", df, all(c in df.columns for c in ["date", "open", "close", "high", "low", "volume"]),
              f"columns={list(df.columns)}")
        check("First close > 0", df, float(df.iloc[0]["close"]) > 0, f"first_close={df.iloc[0]['close']}")
        print(f"   First row: {df.iloc[0].to_dict()}")
        print(f"   Last row:  {df.iloc[-1].to_dict()}")
    print(f"   Elapsed: {elapsed:.2f}s")
except Exception as e:
    check("2. get_kline", e, False, f"EXCEPTION: {e}")

# ── 3 ──
print("\n" + "=" * 70)
print("3. get_real_stock_list()")
print("=" * 70)
try:
    t1 = time.time()
    codes = get_real_stock_list()
    elapsed = time.time() - t1
    check("Returns list", codes, isinstance(codes, list), f"type={type(codes).__name__}")
    check("Has many stocks (>=500)", codes, len(codes) >= 500, f"count={len(codes)}")
    check("Codes are 6-digit strings", codes, all(len(c) == 6 for c in codes[:100]), f"sample={codes[:5]}")
    print(f"   Sample: {codes[:10]}")
    print(f"   Elapsed: {elapsed:.2f}s")
except Exception as e:
    check("3. get_real_stock_list", e, False, f"EXCEPTION: {e}")

# ── 4 ──
print("\n" + "=" * 70)
print("4. get_sector_ranking(10)")
print("=" * 70)
try:
    t1 = time.time()
    sectors = get_sector_ranking(10)
    elapsed = time.time() - t1
    check("Returns list", sectors, isinstance(sectors, list), f"type={type(sectors).__name__}")
    check("Has sectors", sectors, len(sectors) > 0, f"count={len(sectors)}")
    if sectors:
        check("Sector has name", sectors[0], bool(sectors[0].get("name")), f"name={sectors[0].get('name')}")
        check("Sector has change_pct", sectors[0], sectors[0].get("change_pct") is not None,
              f"change_pct={sectors[0].get('change_pct')}")
        print(f"   Top sector: {sectors[0]}")
        print(f"   All: {[s['name'] for s in sectors]}")
    print(f"   Elapsed: {elapsed:.2f}s")
except Exception as e:
    check("4. get_sector_ranking", e, False, f"EXCEPTION: {e}")

# ── 5 ──
print("\n" + "=" * 70)
print("5. get_top_sectors(5)")
print("=" * 70)
try:
    t1 = time.time()
    top = get_top_sectors(5)
    elapsed = time.time() - t1
    check("Returns list", top, isinstance(top, list), f"type={type(top).__name__}")
    check("Has top sectors", top, len(top) > 0, f"count={len(top)}")
    if top:
        check("Sectors are strings", top, all(isinstance(s, str) for s in top), f"sample={top}")
    print(f"   Top sectors: {top}")
    print(f"   Elapsed: {elapsed:.2f}s")
except Exception as e:
    check("5. get_top_sectors", e, False, f"EXCEPTION: {e}")

# ── 6 ──
print("\n" + "=" * 70)
print("6. get_top_flow_stocks(200)")
print("=" * 70)
try:
    t1 = time.time()
    flow = get_top_flow_stocks(200)
    elapsed = time.time() - t1
    check("Returns dict", flow, isinstance(flow, dict), f"type={type(flow).__name__}")
    check("Has flow data", flow, len(flow) > 0, f"count={len(flow)}")
    if flow:
        sample_keys = list(flow.keys())[:5]
        check("Keys are 6-digit codes", flow, all(len(k) == 6 for k in sample_keys), f"sample_keys={sample_keys}")
        sample_val = flow[sample_keys[0]]
        check("Flow values are numeric", flow, isinstance(sample_val, (int, float)),
              f"first={sample_keys[0]}: {sample_val}")
        print(f"   Top stocks by inflow: {list(flow.items())[:3]}")
    print(f"   Elapsed: {elapsed:.2f}s")
except Exception as e:
    check("6. get_top_flow_stocks", e, False, f"EXCEPTION: {e}")

# ── 7 ──
print("\n" + "=" * 70)
print("7. get_northbound_flow()")
print("=" * 70)
try:
    t1 = time.time()
    nb = get_northbound_flow()
    elapsed = time.time() - t1
    check("Returns dict", nb, isinstance(nb, dict), f"type={type(nb).__name__}")
    for key in ["today_net_yi", "cumulative_yi", "direction", "signal", "score"]:
        check(f"Has key '{key}'", nb, key in nb, f"keys={list(nb.keys())}")
    check("direction is valid string", nb, nb.get("direction") in ("strong_inflow", "inflow", "outflow", "strong_outflow", "unknown"),
          f"direction={nb.get('direction')}")
    check("score is numeric", nb, isinstance(nb.get("score"), (int, float)), f"score={nb.get('score')}")
    print(f"   Result: {json.dumps(nb, ensure_ascii=False)}")
    print(f"   Elapsed: {elapsed:.2f}s")
except Exception as e:
    check("7. get_northbound_flow", e, False, f"EXCEPTION: {e}")

# ── 8 ──
print("\n" + "=" * 70)
print("8. get_market_breadth()")
print("=" * 70)
try:
    t1 = time.time()
    mb = get_market_breadth()
    elapsed = time.time() - t1
    check("Returns dict", mb, isinstance(mb, dict), f"type={type(mb).__name__}")
    for key in ["ad_score", "up_count", "down_count"]:
        check(f"Has key '{key}'", mb, key in mb, f"keys={list(mb.keys())}")
    check("ad_score is int 0-60", mb, isinstance(mb.get("ad_score"), int) and 0 <= mb["ad_score"] <= 60,
          f"ad_score={mb.get('ad_score')}")
    check("up_count + down_count plausible", mb,
          isinstance(mb.get("up_count"), int) and isinstance(mb.get("down_count"), int) and
          (mb["up_count"] + mb["down_count"]) > 0,
          f"up={mb.get('up_count')}, down={mb.get('down_count')}")
    print(f"   Result: {mb}")
    print(f"   Elapsed: {elapsed:.2f}s")
except Exception as e:
    check("8. get_market_breadth", e, False, f"EXCEPTION: {e}")

# ── 9 ──
print("\n" + "=" * 70)
print("9. get_index_snapshot(['000001','399001','399006'])")
print("=" * 70)
try:
    t1 = time.time()
    idx = get_index_snapshot(["000001", "399001", "399006"])
    elapsed = time.time() - t1
    check("Returns dict", idx, isinstance(idx, dict), f"type={type(idx).__name__}")
    check("Has index data", idx, len(idx) > 0, f"keys={list(idx.keys())}")
    if "000001" in idx:
        s = idx["000001"]
        check("000001 (SSE) has price", s, bool(s.get("price")), f"price={s.get('price')}")
        check("000001 (SSE) has name", s, s.get("name"), f"name={s.get('name')}")
        check("000001 (SSE) price > 2000", s, float(s.get("price", 0)) > 2000,
              f"price={s.get('price')}")
    else:
        check("Has 000001 in result", idx, False, f"Missing 000001 (SSE)")
    print(f"   Index data: {json.dumps({k: {kk: vv for kk, vv in v.items() if kk in ('code','name','price','change_pct')} for k, v in idx.items()}, ensure_ascii=False)}")
    print(f"   Elapsed: {elapsed:.2f}s")
except Exception as e:
    check("9. get_index_snapshot", e, False, f"EXCEPTION: {e}")

# ── Summary ──
print("\n" + "=" * 70)
print(f"SUMMARY: {passed} PASSED, {failed} FAILED")
print("=" * 70)
for r in results:
    print(r)
sys.exit(0 if failed == 0 else 1)
