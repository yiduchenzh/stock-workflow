"""Core module tests"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from datetime import date
from core.calendar import is_trading_day, is_market_open

def test_is_trading_day_weekday():
    assert is_trading_day(date(2026, 6, 22)) == True   # Monday

def test_is_trading_day_weekend():
    assert is_trading_day(date(2026, 6, 20)) == False  # Saturday
    assert is_trading_day(date(2026, 6, 21)) == False  # Sunday

def test_is_trading_day_holiday():
    assert is_trading_day(date(2026, 1, 1)) == False   # New Year

def test_engine_init():
    from core.engine import AuroraEngine
    engine = AuroraEngine()
    assert engine.capital == 1000000
    assert engine.mode == "paper"
    assert engine.market_score == 50
