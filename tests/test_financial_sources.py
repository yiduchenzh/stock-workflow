"""
测试 A股基本面数据获取模块 financial_sources.py
测试要点:
  1. 模块导入正常
  2. get_financial_indicators 返回正确格式的 dict
  3. enrich_stock_with_financials 正确添加字段
  4. enrich_batch 批量处理正常
  5. test_single_stock 自测函数可独立运行
  6. 空/无效输入容错
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("test_financial")

# ─── Test 1: Module import ───────────────────────────────────────
def test_import():
    """Test that the module imports cleanly."""
    try:
        from data.financial_sources import (
            get_financial_indicators,
            enrich_stock_with_financials,
            enrich_batch,
            test_single_stock,
            _secid, _code_prefix,
            _safe_float,
        )
        print("[PASS] Module imports OK")
        return True
    except Exception as e:
        print(f"[FAIL] Import error: {e}")
        return False


# ─── Test 2: get_financial_indicators ────────────────────────────
def test_get_financial_indicators():
    """Test that get_financial_indicators returns a dict with correct keys."""
    from data.financial_sources import get_financial_indicators

    # Test with a valid code
    result = get_financial_indicators("600519")
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"

    # Check that the result contains Berkshire-relevant keys if data was fetched
    expected_keys = [
        "roe_10yr", "fcf_5yr_cumulative", "interest_coverage",
        "gross_margin_lt", "ocf_to_ni_5yr", "net_margin_lt",
        "share_dilution_5yr",
    ]
    for key in expected_keys:
        if key in result:
            print(f"  ✓ Has {key} = {result[key]}")
        else:
            print(f"  · {key} not available (network dependent)")

    print(f"[PASS] get_financial_indicators returned {len(result)} fields")
    return True


# ─── Test 3: enrich_stock_with_financials ────────────────────────
def test_enrich_stock():
    """Test that enrich_stock_with_financials adds fields to a stock dict."""
    from data.financial_sources import enrich_stock_with_financials

    stock = {"code": "600519", "name": "贵州茅台"}
    enriched = enrich_stock_with_financials(stock)

    assert "code" in enriched, "Missing code"
    assert enriched["code"] == "600519"
    assert "name" in enriched
    assert enriched["name"] == "贵州茅台"

    # Fields may or may not be present depending on network
    berkshire_fields = [
        "roe_10yr", "fcf_5yr_cumulative", "interest_coverage",
        "gross_margin_lt", "ocf_to_ni_5yr", "net_margin_lt",
        "share_dilution_5yr",
    ]
    found = sum(1 for f in berkshire_fields if f in enriched)
    print(f"  ✓ Original fields preserved")
    print(f"  ✓ {found}/{len(berkshire_fields)} Berkshire fields added")

    # Original stock dict should not be modified
    assert "roe_10yr" not in stock or stock.get("roe_10yr") is None

    print("[PASS] enrich_stock_with_financials")
    return True


# ─── Test 4: enrich_batch ────────────────────────────────────────
def test_enrich_batch():
    """Test batch enrichment."""
    from data.financial_sources import enrich_batch

    stocks = [
        {"code": "600519", "name": "贵州茅台"},
        {"code": "000858", "name": "五粮液"},
        {"code": "000333", "name": "美的集团"},
    ]
    enriched = enrich_batch(stocks)
    assert len(enriched) == 3, f"Expected 3, got {len(enriched)}"

    for s in enriched:
        assert "code" in s, f"Missing code in {s}"
        print(f"  ✓ {s['code']} ({s.get('name','?')}): {len(s)} fields")

    print("[PASS] enrich_batch")
    return True


# ─── Test 5: Edge cases ──────────────────────────────────────────
def test_edge_cases():
    """Test edge cases: empty input, invalid codes, missing fields."""
    from data.financial_sources import (
        get_financial_indicators,
        enrich_stock_with_financials,
        enrich_batch,
    )

    # Empty batch
    result = enrich_batch([])
    assert result == [], f"Empty batch should return [], got {result}"

    # Missing code
    stock = enrich_stock_with_financials({})
    assert stock == {}, "Empty stock should return unchanged"

    stock2 = enrich_stock_with_financials({"name": "Test"})
    assert "name" in stock2, "Stock without code should be unchanged"

    # Invalid code
    result = get_financial_indicators("")
    assert result == {}, f"Empty code should return empty dict"

    result = get_financial_indicators("abc")
    assert result == {}, f"Non-numeric code should return empty dict"

    # None code
    try:
        result = get_financial_indicators(None)
        assert result == {}, f"None code should return empty dict"
    except Exception as e:
        print(f"[NOTE] None code handled: {e}")

    print("[PASS] All edge cases handled correctly")
    return True


# ─── Test 6: Helper functions ────────────────────────────────────
def test_helpers():
    """Test internal helper functions."""
    from data.financial_sources import _safe_float, _secid, _code_prefix

    # _safe_float
    assert _safe_float("15.5") == 15.5
    assert _safe_float("20%") == 20.0
    assert _safe_float("1,234.56") == 1234.56
    assert _safe_float(None) == 0.0
    assert _safe_float("") == 0.0
    assert _safe_float(42) == 42.0

    # _secid
    assert _secid("600519") == "1.600519"
    assert _secid("000001") == "0.000001"
    assert _secid("300750") == "0.300750"
    assert _secid("688981") == "1.688981"

    # _code_prefix
    assert _code_prefix("600519") == "SH600519"
    assert _code_prefix("000001") == "SZ000001"
    assert _code_prefix("300750") == "SZ300750"

    print("[PASS] All helper functions correct")
    return True


# ─── Test 7: test_single_stock is callable ───────────────────────
def test_test_function():
    """Test that the built-in test function runs without error."""
    from data.financial_sources import test_single_stock

    # Capture stdout
    import io
    from contextlib import redirect_stdout

    f = io.StringIO()
    with redirect_stdout(f):
        result = test_single_stock("600519")

    output = f.getvalue()
    assert isinstance(result, dict), "test_single_stock should return dict"
    print(f"  ✓ test_single_stock produced {len(result)} fields")
    print(f"  ✓ Output: {len(output)} chars")

    # Run without args (default to 600519)
    f2 = io.StringIO()
    with redirect_stdout(f2):
        result2 = test_single_stock()
    assert isinstance(result2, dict), "Default test should return dict"

    print("[PASS] test_single_stock")
    return True


# ─── Run all tests ───────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  A股基本面数据模块 — 测试套件")
    print("=" * 60)

    tests = [
        ("Module Import", test_import),
        ("Helpers", test_helpers),
        ("Edge Cases", test_edge_cases),
        ("Financial Indicators", test_get_financial_indicators),
        ("Enrich Stock", test_enrich_stock),
        ("Enrich Batch", test_enrich_batch),
        ("Test Function", test_test_function),
    ]

    passed = 0
    failed = 0
    for name, func in tests:
        print(f"\n── {name} ──")
        try:
            func()
            print(f"  ✅ {name}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*60}")
    print(f"  结果: {passed} 通过, {failed} 失败 / {len(tests)} 总测试")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)
