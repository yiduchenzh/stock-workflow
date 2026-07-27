"""新增模块集成测试 — engine_live/recovery/account_verify/ht_bridge/profiling/event_signals/DataQC"""
import sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

class TestLiveEngine:
    def test_import(self):
        from core.engine_live import EngineLiveWrapper
        assert EngineLiveWrapper is not None

class TestRecovery:
    def test_import(self):
        from monitor.recovery import EngineRecovery, auto_recover
        r = EngineRecovery()
        status = r.check_availability()
        assert "available" in status

class TestAccountVerify:
    def test_import(self):
        from monitor.account_verify import AccountVerifier, verify_all
        v = AccountVerifier()
        assert v is not None
    def test_reconcile(self):
        from monitor.account_verify import AccountVerifier
        v = AccountVerifier()
        alerts = v.reconcile({"000001":{"shares":100}}, {"000001":{"shares":100}})
        assert len(alerts) == 0
    def test_capital_safety(self):
        from monitor.account_verify import AccountVerifier
        v = AccountVerifier()
        alerts = v.check_capital_safety(800000, 1000000)
        assert len(alerts) > 0

class TestHTBridge:
    def test_import(self):
        from executor.ht_bridge import HTTradeExecutor, SimBroker, create_executor
        e = create_executor(mode="sim")
        assert e.get_account_info()["total_value"] == 1000000
    def test_buy_sell(self):
        from executor.ht_bridge import create_executor
        e = create_executor(mode="sim")
        r = e.buy("600519", 1500, 100)
        assert r.get("success")
        r2 = e.sell("600519", 1520, 50)
        assert r2.get("success")

class TestProfiling:
    def test_import(self):
        from profiling import get_trader_profile, list_profiles, get_engine_config
        profiles = list_profiles()
        assert len(profiles) == 6
    def test_fulltime_config(self):
        from profiling import get_engine_config
        c = get_engine_config("全职短线客")
        assert c["strategy_weights"]["momentum_breakout"] >= 2.0
        assert c["risk"]["stop_loss_pct"] == 0.03
    def test_questionnaire(self):
        from profiling.questionnaire import evaluate
        r = evaluate({"q1":"A","q2":"C","q3":"A","q4":"A","q5":"A"})
        assert r["matched_profile"] == "全职短线客"

class TestEventSignals:
    def test_import(self):
        from screening.event_signals import scan_event_signals, _break_book_signal
        score = _break_book_signal(0.5, 6.0)
        assert score > 90

class TestDataQC:
    def test_import(self):
        from data.data_quality import DataQualityCheck
        d = DataQualityCheck()
        assert d is not None

class TestAutoTune:
    def test_import(self):
        from strategies.auto_tune import auto_downgrade, apply_adjustments
        adj = auto_downgrade(min_trades=0)
        assert isinstance(adj, dict)

class TestAllModules:
    def test_all_imports(self):
        import core.engine, core.engine_live
        import monitor.recovery, monitor.account_verify
        import executor.ht_bridge, profiling
        import screening.event_signals
        import data.data_quality, strategies.auto_tune
        assert True