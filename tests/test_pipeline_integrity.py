"""
管线完整性测试 — Pipeline Integrity Tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.pipeline_validator import (
    PipelineValidator, STEP_CONTRACTS, CROSS_STEP_CONTRACTS,
    _check_account_positions_synced,
)

class MockEngine:
    def __init__(self):
        self.market_score = 50
        self.market_regime = "range"
        self.reflexivity = {"stage": "neutral"}
        self.northbound = {"signal": "neutral"}
        self.candidates = []
        self.screened = None
        self.analysis = []
        self.scores = []
        self.plans = []
        self.alerts = []
        self.account = None
        self.positions = {}

class MockAccount:
    def __init__(self):
        self.positions = {"000001": {"shares": 1000, "avg_cost": 10.0}}
        self.cash = 900000
        self.trades = []
    def buy(self, c, p, s, r=""):
        return {"success": True}
    def sell(self, c, p, s, r=""):
        return {"success": True, "trade": {"code": c}}
    @property
    def total_value(self):
        return self.cash + 10000

# ---- Type/Range Validation ----

class TestAttributeValidation:
    def test_market_score_type_error(self):
        e = MockEngine()
        v = PipelineValidator(e, auto_fix=False)
        v._check_attribute("step_market", "market_score", "abc", {"type": (int, float), "msg": "must be number"})
        assert len(v.errors) == 1
        assert "类型错误" in v.errors[0]["msg"]

    def test_market_score_valid(self):
        e = MockEngine()
        v = PipelineValidator(e, auto_fix=False)
        v._check_attribute("step_market", "market_score", 75, {"type": (int, float), "range": (0, 100)})
        assert len(v.errors) == 0

    def test_market_score_out_of_range(self):
        e = MockEngine()
        v = PipelineValidator(e, auto_fix=False)
        v._check_attribute("step_market", "market_score", 150, {"type": (int, float), "range": (0, 100)})
        assert any("超出范围" in w["msg"] for w in v.warnings)

    def test_regime_valid_values(self):
        e = MockEngine()
        v = PipelineValidator(e, auto_fix=False)
        valid = ["bull_strong", "bull_weak", "range", "bear_weak", "bear_strong"]
        for r in valid:
            v._check_attribute("step_market", "market_regime", r, {"type": str, "in_values": valid})
        assert all("不在期望值域" not in w["msg"] for w in v.warnings)

    def test_regime_invalid(self):
        e = MockEngine()
        v = PipelineValidator(e, auto_fix=False)
        v._check_attribute("step_market", "market_regime", "invalid", {"type": str, "in_values": ["range"]})
        assert any("不在期望值域" in w["msg"] for w in v.warnings)

    def test_screened_none_allowed(self):
        e = MockEngine()
        v = PipelineValidator(e, auto_fix=False)
        v._check_attribute("step_screen", "screened", None, {"type": (list, type(None)), "msg": ""})
        assert len(v.errors) == 0

    def test_candidates_list(self):
        e = MockEngine()
        v = PipelineValidator(e, auto_fix=False)
        v._check_attribute("step_cascade", "candidates", [], {"type": list, "msg": ""})
        assert len(v.errors) == 0

    def test_account_not_none(self):
        e = MockEngine()
        v = PipelineValidator(e, auto_fix=False)
        v._check_attribute("step_simulate", "account", None, {"not_none": True, "msg": "must exist"})
        assert any("None" in err["msg"] for err in v.errors)

    def test_account_has_attrs(self):
        e = MockEngine()
        v = PipelineValidator(e, auto_fix=False)
        v._check_attribute("step_simulate", "account", MockAccount(), {"type": object, "check_attrs": ["positions", "cash"]})
        assert len(v.errors) == 0

# ---- Cross-Step Contracts ----

class TestCrossStep:
    def test_cs001_synced_ok(self):
        acct = MockAccount()
        e = MockEngine()
        e.account = acct
        e.positions = acct.positions
        assert _check_account_positions_synced(e) == True

    def test_cs001_not_synced(self):
        acct = MockAccount()
        e = MockEngine()
        e.account = acct
        e.positions = {}
        assert _check_account_positions_synced(e) == False

    def test_cs001_no_account(self):
        e = MockEngine()
        assert _check_account_positions_synced(e) == True

    def test_account_reuse_detected(self):
        e = MockEngine()
        v = PipelineValidator(e, auto_fix=False)
        e.account = MockAccount()
        v._account_before_rebalance = id(e.account)
        e.account = MockAccount()
        v._check_rebalance_account_reuse()
        assert any("创建新account" in err["msg"] for err in v.errors)

    def test_account_reuse_ok(self):
        e = MockEngine()
        v = PipelineValidator(e, auto_fix=False)
        e.account = MockAccount()
        v._account_before_rebalance = id(e.account)
        v._check_rebalance_account_reuse()
        assert sum(1 for err in v.errors if "创建新account" in err["msg"]) == 0

    def test_validate_all_runs_all(self):
        e = MockEngine()
        v = PipelineValidator(e)
        r = v.validate_all()
        assert r["passed"] + r["failed"] == len(CROSS_STEP_CONTRACTS)

# ---- Auto-Fix ----

class TestAutoFix:
    def test_auto_fix_positions(self):
        acct = MockAccount()
        e = MockEngine()
        e.account = acct
        e.positions = {}
        v = PipelineValidator(e, auto_fix=True)
        v._run_cross_step_checks()
        assert e.positions is acct.positions
        assert len(v.fixes_applied) >= 1
        assert "auto-fix" in v.fixes_applied[0]

    def test_no_auto_fix_when_disabled(self):
        acct = MockAccount()
        e = MockEngine()
        e.account = acct
        e.positions = {}
        v = PipelineValidator(e, auto_fix=False)
        v._run_cross_step_checks()
        assert e.positions is not acct.positions
        assert len(v.fixes_applied) == 0

# ---- Report Structure ----

class TestReport:
    def test_report_structure(self):
        e = MockEngine()
        v = PipelineValidator(e)
        v.validate_after("step_market")
        v.validate_after("step_cascade")
        r = v.report()
        assert "summary" in r
        assert "total_errors" in r["summary"]
        assert "total_warnings" in r["summary"]
        assert "step_results" in r
        assert "cross_step" in r

    def test_summary_str(self):
        e = MockEngine()
        v = PipelineValidator(e)
        v._record_error("P0", "test error", fix="test fix")
        s = v.summary_str()
        assert "test error" in s
        assert "test fix" in s

    def test_empty_pipeline(self):
        e = MockEngine()
        v = PipelineValidator(e)
        r = v.report()
        assert r["summary"]["total_errors"] == 0

    def test_all_13_steps_have_contracts(self):
        steps = [
            "step_market", "step_cascade", "step_screen", "step_analyze",
            "step_score", "step_position", "step_risk", "step_simulate",
            "step_monitor", "step_rebalance", "step_evaluate",
            "step_review", "step_prep",
        ]
        for s in steps:
            assert s in STEP_CONTRACTS, f"Missing: {s}"

    def test_cross_step_ids_unique(self):
        ids = set()
        for c in CROSS_STEP_CONTRACTS:
            assert c["id"] not in ids
            ids.add(c["id"])

    def test_step_monitor_pre_check(self):
        e = MockEngine()
        e.positions = {}
        e.account = None
        v = PipelineValidator(e)
        v.validate_before("step_monitor")
        assert len(v.errors) == 0
