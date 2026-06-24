"""策略自进化 v2.0 多维评分测试"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path
from strategies.evolution import (
    record_signal, record_trade_result, record_regime,
    record_regime_trade, record_ic,
    get_strategy_health, get_all_health, compute_ic,
    compute_regime_health, compute_half_life, recommend_weights,
)
DATA  = Path(__file__).resolve().parent.parent / "data" / "strategy_evolution.json"
def _clean():
    if DATA.exists(): DATA.unlink()
def _add_trades(name, wins, losses, regime="bull_strong", scores=None):
    for i in range(wins):
        sc = scores[i] if scores and i < len(scores) else 65
        record_signal(name, sc)
        record_trade_result(name, 0.03, True)
        record_regime(name, regime)
        record_regime_trade(name, regime, True)
        if scores: record_ic(name, sc, 2.5)
    for i in range(losses):
        idx = wins + i
        sc = scores[idx] if scores and idx < len(scores) else 40
        record_signal(name, sc)
        record_trade_result(name, -0.02, False)
        r2 = "range" if regime == "bull_strong" else regime
        record_regime(name, r2)
        record_regime_trade(name, r2, False)
        if scores: record_ic(name, sc, -2.0)
class TestBasicRecord:
    def setup_method(self, m): _clean()
    def test_signal(self): record_signal("t",75);d=json.loads(DATA.read_text());assert d["t"]["signals"][0]["score"]==75
    def test_trade(self): record_trade_result("t",0.05,True);d=json.loads(DATA.read_text());assert d["t"]["trades"][0]["win"]==True
    def test_regime(self): record_regime("t","bs");assert json.loads(DATA.read_text())["t"]["regime"]["bs"]["signals"]==1
    def test_ic(self): record_ic("t",75,2.5);assert len(json.loads(DATA.read_text())["t"]["ic_records"])==1
class TestHealth:
    def setup_method(self, m): _clean()
    def test_insufficient(self): assert get_strategy_health("x")["status"]=="new"
    def test_good(self): _add_trades("g",7,3,scores=[70,75,80,65,72,68,78,45,40,42]);h=get_strategy_health("g");assert h["composite"]>=50
    def test_bad(self): _add_trades("b",1,9,scores=[55,30,35,32,28,33,38,29,31,25]);assert get_strategy_health("b")["status"]=="dead"
    def test_range(self): _add_trades("t",5,5);assert 0<=get_strategy_health("t")["composite"]<=100
    def test_structure(self): _add_trades("t",6,4);h=get_strategy_health("t");assert all(k in h for k in["ic","regime","half_life"])
class TestIC:
    def setup_method(self, m): _clean()
    def test_insufficient(self): assert compute_ic("x")["reliable"]==False
    def test_computed(self):
        for i in range(20): record_ic("t",70+(i%5)*5,2.0+(i%5)*0.5)
        assert compute_ic("t")["ic"] is not None
class TestRegime:
    def setup_method(self, m): _clean()
    def test_stats(self): record_regime("t","bs");record_regime_trade("t","bs",True);record_regime_trade("t","bs",False);assert compute_regime_health("t")["bs"]["wr"]==50.0
class TestHalfLife:
    def setup_method(self, m): _clean()
    def test_consistent(self):
        for i in range(10): record_trade_result("t", 0.02 if i<7 else -0.01, i<7)
        assert compute_half_life("t")["half_life"] is not None
    def test_concentrated(self):
        for i in range(10): record_trade_result("t", 1.0 if i==0 else -0.01, i==0)
        assert compute_half_life("t")["half_count"] <= 2
class TestRecommend:
    def setup_method(self, m): _clean()
    def test_weights(self): _add_trades("g",8,2);_add_trades("b",1,9);w=recommend_weights();assert w["b"]<=w["g"]