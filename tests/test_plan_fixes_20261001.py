# -*- coding: utf-8 -*-
"""2026-10-01 计划修复批次2 回归测试

A 单日开仓笔数上限(实测: 当天第1笔 +0.22%/笔, 第2笔 -2.48%/笔, 第3+笔 -2.41%/笔)
B 滑点 tick 校准(实测: 单笔占成交额中位 0.0010% → 冲击可忽略; 真实≈1跳 vs 旧口径 0.272%/边)
隔离: SimAccount 在 tests 栈内自动用 *_test.json; 本测试再显式注入 tmp 路径。
"""
import pytest


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """涨停板检查会调腾讯行情 → 测试内打桩为空(离线可跑)"""
    try:
        import data.sources as _ds
        monkeypatch.setattr(_ds, "get_tencent_quotes", lambda codes: {}, raising=False)
    except Exception:
        pass


def _acct(tmp_path, cfg):
    from executor.sim_account import SimAccount
    return SimAccount(capital=1_000_000, config=cfg,
                      state_path=tmp_path / "st.json", trades_path=tmp_path / "tr.json")


def test_daily_open_cap_blocks_second_open(tmp_path):
    a = _acct(tmp_path, {"max_opens_per_day": 1})
    r1 = a.buy("600519", 100.0, 100)
    assert r1["success"], r1
    r2 = a.buy("000001", 10.0, 100)
    assert not r2["success"], "第2笔应被单日上限拦截"
    assert "单日开仓上限" in r2["error"], r2["error"]
    # 被拦的笔不得计入持仓
    assert "000001" not in a.positions


def test_daily_open_cap_zero_means_unlimited(tmp_path):
    a = _acct(tmp_path, {"max_opens_per_day": 0})
    assert a.buy("600519", 100.0, 100)["success"]
    assert a.buy("000001", 10.0, 100)["success"]


def test_daily_open_cap_nested_config_location(tmp_path):
    """旋钮放在 execution: 段下也应生效(engine 传的 config 层级不定)"""
    a = _acct(tmp_path, {"execution": {"max_opens_per_day": 1}})
    assert a.buy("600519", 100.0, 100)["success"]
    assert not a.buy("000001", 10.0, 100)["success"]


def test_slippage_tick_mode_is_far_cheaper_than_legacy(tmp_path):
    tick = _acct(tmp_path, {"slippage_mode": "tick"})
    r1 = tick.buy("600519", 100.0, 100)          # 100 元股: 1跳 = 0.01/100 = 0.01%
    t1 = r1["trade"]
    assert t1["slip_mode"] == "tick", t1
    assert t1["slippage_pct"] <= 0.0202, t1["slippage_pct"]      # ≈2跳(默认 slippage_ticks=2)

    legacy = _acct(tmp_path, {"slippage_mode": "legacy"})
    t2 = legacy.buy("600519", 100.0, 100)["trade"]
    assert t2["slip_mode"] == "legacy", t2
    assert t2["slippage_pct"] > t1["slippage_pct"] * 3, (t1["slippage_pct"], t2["slippage_pct"])


def test_default_slippage_mode_is_tick(tmp_path):
    """缺省必须为 tick(实测支撑) —— 防止有人把默认值改回去"""
    t = _acct(tmp_path, {}).buy("600519", 100.0, 100)["trade"]
    assert t["slip_mode"] == "tick"


def test_cheap_stock_tick_is_meaningful(tmp_path):
    """低价股 1跳 占比更大(4元股 → 0.25%), 不得被 0.1% 上限误伤下限"""
    a = _acct(tmp_path, {"slippage_mode": "tick"})
    t = a.buy("601988", 4.0, 100)["trade"]       # 4 元: tick = 0.01/4 = 0.25%
    assert t["slippage_pct"] >= 0.4, t["slippage_pct"]


def test_sell_uses_same_tick_mode_not_legacy(tmp_path):
    """⭐ 完整性关键: 卖出一侧必须用同一口径 —— 只改买侧会变成"买便宜卖贵"的偏袒偏置"""
    a = _acct(tmp_path, {"slippage_mode": "tick", "max_opens_per_day": 0})
    assert a.buy("600519", 100.0, 100)["success"]
    # A股 T+1: 当日买入不可卖 → 清掉当日买入登记(模拟隔日) 才能测卖出滑点
    a.today_buys.clear()
    r = a.sell("600519", 100.0, 100, "test")
    assert r.get("success"), r
    t = r.get("trade") or r
    assert t.get("slip_mode") == "tick", t
    assert float(t.get("slippage_pct") or 0) <= 0.0202, t.get("slippage_pct")
    # 卖出记录必须留痕(与买入对称)
    last = a.trades[-1]
    assert last["slip_mode"] == "tick" and last["action"] == "sell", last


def test_tick_slippage_magnitude_matches_measurement(tmp_path, monkeypatch):
    """实测画像: 默认 2跳 = 2*0.01/价 (round 到 4 位小数 → 容差 1e-3)"""
    import data.sources as _ds
    monkeypatch.setattr(_ds, "get_tencent_quotes", lambda codes: {}, raising=True)
    a = _acct(tmp_path, {"slippage_mode": "tick", "max_opens_per_day": 0})
    for px in (20.0, 30.0, 60.0):
        r = a.buy("600000", px, 100)
        assert r.get("success"), ("买入被拒", px, r)
        sp = float(r["trade"]["slippage_pct"])
        assert abs(sp - 0.01 / px * 100 * 2) < 1e-3, (px, sp)   # 2跳
