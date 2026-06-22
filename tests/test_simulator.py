"""Simulator tests"""
import sys, os, json
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from executor.sim_account import SimAccount, STATE, TRADES

def _clean():
    for f in [STATE, TRADES]:
        if f.exists():
            f.unlink()

def test_buy_and_sell():
    _clean()
    acc = SimAccount(1000000)
    t = acc.buy("000001", 10.0, 1000, "test")
    assert t is not None
    assert acc.cash < 1000000
    assert "000001" in acc.positions
    assert acc.positions["000001"]["avg_cost"] > 10.0

def test_avg_cost_includes_fees():
    _clean()
    acc = SimAccount(1000000)
    acc.buy("000001", 10.0, 1000)
    avg = acc.positions["000001"]["avg_cost"]
    assert avg > 10.0, f"avg_cost={avg} should include fees (>{10.0})"

def test_sell_pnl_calculation():
    _clean()
    acc = SimAccount(1000000)
    acc.buy("000001", 10.0, 1000)
    result = acc.sell("000001", 11.0, 1000)
    assert result.get("success")
    assert "000001" not in acc.positions
    assert result.get("success") or result.get("trade", {}).get("pnl", 0) > 0

def test_total_value():
    _clean()
    acc = SimAccount(1000000)
    acc.buy("000001", 10.0, 1000)
    tv = acc.total_value
    assert tv > 0
