# -*- coding: utf-8 -*-
"""v14.49 回归测试 (2026-09-11 周复盘修复)

覆盖:
  P0-1 流动性过滤单位修正(手→股, 阈值 2000万/日) — 原实现严 100 倍, 误杀 36% 计划
  P0-3 板块过滤命名空间对齐(东财行业名) + 无行业归属 fail-open
  P1-1 死账户(新手入门/价值投资者) prev_close_B 权重 ≥2.0(满足单信号确认门槛)
  P1-2 周/月预算闸: 日基准固化 + 按日覆盖累加(修复 weekly_pnl≡1e-9 → 闸永不触发)
  P1-3 跨体系(主sim ↔ Agent)持仓去重
全部离线可跑(不依赖行情网络)。
"""
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))


# ── P0-1 流动性单位 ───────────────────────────────────────────────────
def test_liquidity_metrics_lot_to_share():
    """日K volume 单位=手 → 必须 ×100 才是股; 成交额 = close × 股"""
    from risk import controls as C
    df = pd.DataFrame({"close": [10.0] * 20, "volume": [20000] * 20})   # 2万手=200万股
    m = C.liquidity_metrics("000001", kline_df=df)
    assert m["avg_vol_shares"] == pytest.approx(2_000_000, rel=1e-6)
    assert m["avg_turnover"] == pytest.approx(20_000_000, rel=1e-6)     # 2000万元


def test_check_liquidity_new_threshold(monkeypatch):
    """修复前: mean(close×volume)=成交额/100 与阈值2e6比 → 实际要求 2亿/日(误杀)"""
    from risk import controls as C
    # 003013 地铁设计实测: 20日均 1.92亿 → 修复后通过(修复前被砍)
    monkeypatch.setattr(C, "liquidity_metrics",
                        lambda code, days=20, kline_df=None: {"avg_turnover": 192_160_700.0,
                                                              "avg_vol_shares": 10_960_000.0, "bars": 20})
    assert C.check_liquidity("003013") is True
    # 真·低流动(500万/日, 40万股) → 仍拦截
    monkeypatch.setattr(C, "liquidity_metrics",
                        lambda code, days=20, kline_df=None: {"avg_turnover": 5_000_000.0,
                                                              "avg_vol_shares": 400_000.0, "bars": 20})
    assert C.check_liquidity("830799") is False
    # 无K线 → False(保持原行为)
    monkeypatch.setattr(C, "liquidity_metrics",
                        lambda code, days=20, kline_df=None: {"avg_turnover": None,
                                                              "avg_vol_shares": None, "bars": 0})
    assert C.check_liquidity("999999") is False


def test_check_liquidity_never_raises():
    from risk import controls as C
    assert C.check_liquidity("") is False        # 空代码


# ── P0-3 板块过滤 ─────────────────────────────────────────────────────
def test_sector_filter_namespace_aligned(monkeypatch):
    """判据=东财行业名时命中; 候选无行业归属 → fail-open 不误杀"""
    from screening import strong_stock as S
    monkeypatch.setattr(S, "get_sector_ranking", lambda n=100: [])   # 离线: 无板块数据 → 走降级
    cand = {"code": "002531", "industry": "风电设备", "change_pct": 1.0, "turnover": 4.0,
            "vol_ratio": 2.0, "amount_wan": 8000}
    out = S.screen_strong_stocks([dict(cand)], top_sectors=["风电设备"], flow_stocks=None)
    assert len(out) == 1, "行业名命中应保留"
    # 不同命名空间(同花顺概念名) → 板块过滤返回空, 不静默误判
    out2 = S.screen_strong_stocks([dict(cand)], top_sectors=["光伏玻璃"], flow_stocks=None)
    assert out2 == []
    # 候选无 industry → fail-open(原实现直接 0 通过)
    noind = {"code": "002531", "change_pct": 1.0, "turnover": 4.0, "vol_ratio": 2.0, "amount_wan": 8000}
    out3 = S.screen_strong_stocks([dict(noind)], top_sectors=["风电设备"], flow_stocks=None)
    assert len(out3) == 1, "无行业归属时应 fail-open 跳过过滤"


# ── P1-1 死账户 ───────────────────────────────────────────────────────
def test_dead_accounts_have_prev_close_b_weight():
    """runner 单信号确认规则: _SW[name] >= 2.0 (strategies/runner.py L191)"""
    from profiling.trader_types import SCREENING_CONFIGS, TRADER_PROFILES
    for name in ("新手入门", "价值投资者"):
        w = TRADER_PROFILES[name]["strategy_weights"]
        sp = SCREENING_CONFIGS[name]["signal_prefer"]
        assert w.get("prev_close_B", 0) >= 2.0, f"{name} strategy_weights prev_close_B 需 ≥2.0"
        assert sp.get("prev_close_B", 0) >= 2.0, f"{name} signal_prefer prev_close_B 需 ≥2.0"


# ── P1-2 预算闸 ───────────────────────────────────────────────────────
def _budget(tmp_path, monkeypatch):
    from risk import budget as B
    monkeypatch.setattr(B, "_budget_file_path", lambda: tmp_path / "risk_budget_test.json")
    return B.RiskBudget({}, 1_000_000)


def test_budget_same_day_overwrite_not_accumulate(tmp_path, monkeypatch):
    """同一自然日多次调用(morning/monitor/noon/close) → 覆盖写, 不虚增"""
    b = _budget(tmp_path, monkeypatch)
    b.record_pnl(-0.02, 980_000)
    b.record_pnl(-0.03, 970_000)
    b.record_pnl(-0.03, 970_000)
    assert b.state["weekly_pnl"] == pytest.approx(-0.03, abs=1e-9)
    assert b.state["monthly_pnl"] == pytest.approx(-0.03, abs=1e-9)
    assert len(b.state["daily"]) == 1


def test_budget_weekly_gate_can_trigger(tmp_path, monkeypatch):
    """周亏损 ≤ -5% 必须触发 reduce_half(修复前 weekly_pnl 恒 ~1e-9 → 永不触发)"""
    b = _budget(tmp_path, monkeypatch)
    b.record_pnl(-0.049, 951_000)                  # 达 -5% 的 80% → 预警(warn), 不砍仓
    _r = b.check()
    assert _r["level"] == "weekly_warn" and _r["action"] == "warn"
    b.record_pnl(-0.052, 948_000)                  # 击穿 -5%
    r = b.check()
    assert r["triggered"] is True
    assert r["action"] == "reduce_half"


def test_budget_weekly_is_sum_of_last_7_days(tmp_path, monkeypatch):
    b = _budget(tmp_path, monkeypatch)
    today = dt.date.today()
    daily = {(today - dt.timedelta(days=i)).isoformat(): -0.008 for i in range(1, 7)}
    daily[today.isoformat()] = -0.01
    daily[(today - dt.timedelta(days=20)).isoformat()] = -0.5      # 20天前(不计入周)
    b.state["daily"] = daily
    b.record_pnl(-0.01, 990_000)                                   # 触发重算
    assert b.state["weekly_pnl"] == pytest.approx(-0.058, abs=1e-6)
    assert b.state["monthly_pnl"] == pytest.approx(-0.558, abs=1e-6)
    assert b.check()["action"] == "reduce_half"


def test_budget_drawdown_gate(tmp_path, monkeypatch):
    b = _budget(tmp_path, monkeypatch)
    b.record_pnl(0.0, 1_200_000)                  # peak 抬到 120万
    b.record_pnl(0.0, 1_000_000)                  # 回撤 -16.7%
    r = b.check()
    assert r["triggered"] is True and r["action"] == "pause"


# ── P1-2 账户日基准 ───────────────────────────────────────────────────
def test_sim_account_day_baseline_stable_intraday(tmp_path):
    """当日起算基准: 首次固化, 同日再调用不变(修复前用 prev_total → 被交易刷新成≈current)"""
    from executor.sim_account import SimAccount
    a = SimAccount(1_000_000, {}, state_path=tmp_path / "s.json", trades_path=tmp_path / "t.json")
    base = a.day_baseline()
    assert base == pytest.approx(1_000_000, rel=1e-6)
    a.cash = 900_000                                # 模拟日内亏损 10万
    assert a.day_baseline() == pytest.approx(base, rel=1e-9)
    # 落盘 → 新实例(模拟引擎重建)同一天仍用同一基准
    b = SimAccount(1_000_000, {}, state_path=tmp_path / "s.json", trades_path=tmp_path / "t.json")
    assert b.day_baseline() == pytest.approx(base, rel=1e-9)
    # 日终记录 → close_total 落盘(供次日基准)
    b.mark_day_close()
    raw = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    assert raw["close_date"] == str(dt.date.today())
    assert raw["day_open_date"] == str(dt.date.today())


# ── P1-3 跨体系去重 ───────────────────────────────────────────────────
def test_held_by_others_excludes_self(tmp_path, monkeypatch):
    from multi_agent import global_dedup as G
    main = tmp_path / "sim_state.json"
    ag = tmp_path / "agentX_state.json"
    main.write_text(json.dumps({"positions": {"600000": {"shares": 100}}}), encoding="utf-8")
    ag.write_text(json.dumps({"positions": {"000001": {"shares": 200}}}), encoding="utf-8")
    monkeypatch.setattr(G, "_all_state_files", lambda: [main, ag])
    G._cache.update({"ts": 0.0, "by_path": {}})
    assert G.held_by_others(main) == {"000001"}          # 主sim 排除自己 → 只看到 Agent 持仓
    assert G.held_by_others(ag) == {"600000"}            # Agent 排除自己 → 看到主sim 持仓
    assert G.held_by_others(None) == {"600000", "000001"}
    # 列表形态(ts2: positions=[{code}] 也支持)
    ag.write_text(json.dumps({"positions": [{"code": "000002"}]}), encoding="utf-8")
    G._cache.update({"ts": 0.0, "by_path": {}})
    assert G.held_by_others(main) == {"000002"}
