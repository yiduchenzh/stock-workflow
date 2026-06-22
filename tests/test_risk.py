"""Risk module tests"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from risk.controls import reset, check_all, record_trade
from risk.position import plan_positions

def test_check_all_normal():
    reset()
    plans, alerts = check_all([{"code":"000001"}], {}, {"risk":{"max_positions":5}})
    assert len(alerts) == 0
    assert len(plans) == 1

def test_check_all_capped():
    reset()
    candidates = [{"code": f"{i:06d}"} for i in range(1, 8)]
    plans, alerts = check_all(candidates, {}, {"risk":{"max_positions":5}})
    assert len(plans) == 5
    assert any("超限" in a["msg"] for a in alerts)

def test_record_trade():
    reset()
    record_trade(-0.05)
    record_trade(-0.03)
    record_trade(-0.02)
    plans, alerts = check_all([{"code":"000001"}], {}, {"risk":{"max_positions":5,"max_consecutive_losses":3}})
    assert len(alerts) > 0

def test_plan_positions():
    scores = [
        {"code":"000001","signal":True,"best_score":80,"entry_price":10,"stop_loss":9.5},
        {"code":"000002","signal":True,"best_score":65,"entry_price":20},
        {"code":"000003","signal":False,"best_score":30},
    ]
    plans = plan_positions(scores, 1000000, {"risk":{"position_weights":{"strong":0.30,"normal":0.20,"weak":0.10},"take_profit":{"rr_ratio":2.0},"risk_per_trade_pct":1.0}})
    assert len(plans) == 2
    assert plans[0]["weight"] == 0.30
    assert plans[1]["weight"] == 0.20
