# -*- coding: utf-8 -*-
"""v14.51 回归测试 — 2026-09-18 周复盘 阶段2 修复

① P0-1 画像差异化: 各画像主战法不重复 + 每画像至少一个 ≥2.0 权重信号(防死账户复活)
② P0-2 趋势跟踪者: 有趋势类 ≥2.0 权重信号源(原 momentum_breakout 权重 0 → 死仓 9 日)
③ P1-1 AgentSimAccount: day_baseline/mark_day_close 存在 + 同口径固化 + 落盘读回
       + 画像预算 weekly_pnl 不再恒 ≈0

隔离铁律(2026-09-11 教训): 会 _save() 的组件必须注入 tmp 路径, 否则污染生产 data/*.json
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ───────────────────────── ① / ② 画像配置不变量 ─────────────────────────
def _profiles():
    from profiling.trader_types import TRADER_PROFILES, SCREENING_CONFIGS
    return TRADER_PROFILES, SCREENING_CONFIGS


def test_every_profile_has_a_signal_at_confirm_weight():
    """每个画像至少要有一个权重 ≥2.0 的信号源(runner 单信号确认门槛),
    否则该画像永远 0 confirmed = 死账户(2026-09-04/09-11 两次踩坑)。"""
    tp, sc = _profiles()
    for nm, prof in tp.items():
        w = prof["strategy_weights"]
        assert any(v >= 2.0 for v in w.values()), f"{nm} 无 ≥2.0 权重信号 → 必然死仓: {w}"


def test_trend_follower_activated_by_trend_strategies():
    """P0-2: 趋势跟踪者必须靠『趋势类』信号激活, 而不是再依赖 momentum_breakout(权重 0)。"""
    tp, sc = _profiles()
    w = tp["趋势跟踪者"]["strategy_weights"]
    sp = sc["趋势跟踪者"]["signal_prefer"]
    assert w.get("momentum_breakout", 0) == 0
    for k in ("chan_buy1", "ma_breakout", "wave_point"):
        assert w.get(k, 0) >= 2.0, f"趋势跟踪者 {k} 权重不足: {w}"
        assert sp.get(k, 0) >= 2.0, f"趋势跟踪者 signal_prefer {k} 权重不足: {sp}"


def test_value_investor_A_dominant_and_alive():
    """P0-1: 价值画像(30天+)以 A 型(挖坑低吸)为主导, 但 B 型保持 ≥2.0 不重新饿死。
    教训(本轮): 首版把 B 降到 1.0 → 触发 v14.49 的『死账户』回归测试失败 —— A 型实盘
    极少产信号, 降 B = 该账户再次 0 成交。差异化必须靠『加权主导』而不是『掐断信号源』。"""
    tp, sc = _profiles()
    w = tp["价值投资者"]["strategy_weights"]
    assert w["prev_close_A"] > w["prev_close_B"], f"价值画像 A 未主导: {w}"
    assert w["prev_close_B"] >= 2.0, f"价值画像 B 被掐断(会重新死仓): {w}"


def test_profiles_are_no_longer_homogeneous():
    """P0-1 核心不变量: 5 画像的『可单信号确认(≥2.0)』信号集合不得全部相同。
    注意: engine._apply_profile 里 signal_prefer **后应用**(覆盖 strategy_weights) → 有效权重取并集。"""
    tp, sc = _profiles()
    sigsets = {}
    for nm, prof in tp.items():
        eff = dict(prof["strategy_weights"])
        eff.update(sc.get(nm, {}).get("signal_prefer") or {})
        sigsets[nm] = frozenset(k for k, v in eff.items() if v >= 2.0)
    distinct = set(sigsets.values())
    assert len(distinct) >= 3, f"画像可确认信号集合过于同质({len(distinct)} 种): {sigsets}"
    b_profiles = [nm for nm, s in sigsets.items() if "prev_close_B" in s]
    assert len(b_profiles) < len(sigsets), f"prev_close_B 仍在所有画像单信号可确认: {b_profiles}"


# ───────────────────────── ③ AgentSimAccount 日基准 ─────────────────────────
@pytest.fixture()
def agent_account(tmp_path, monkeypatch):
    """构造隔离的 AgentSimAccount(不碰生产 data/*.json)"""
    from multi_agent.agent import AgentSimAccount
    st = tmp_path / "state.json"
    tr = tmp_path / "trades.json"
    return AgentSimAccount(1_000_000.0, {"risk": {}}, st, tr), st


def test_agent_account_has_day_baseline(agent_account):
    acc, _st = agent_account
    assert hasattr(acc, "day_baseline") and callable(acc.day_baseline)
    assert hasattr(acc, "mark_day_close") and callable(acc.mark_day_close)


def test_agent_day_baseline_is_stable_within_day(agent_account):
    """同日多次调用必须返回同一基准(修复前回退 prev_total 会随每次 _save 漂移)。"""
    acc, _st = agent_account
    b1 = acc.day_baseline()
    acc.cash += 50_000          # 模拟当日交易后总资产变化
    acc._update_total()
    b2 = acc.day_baseline()
    assert b1 == pytest.approx(b2), f"同日基准漂移: {b1} → {b2}"


def test_agent_day_close_becomes_next_baseline(agent_account, monkeypatch):
    """mark_day_close 记的总资产 → 次日 day_baseline 采用(与 SimAccount 同口径)。"""
    acc, _st = agent_account
    import multi_agent.agent as ag
    acc.day_baseline()
    acc.cash = 960_000.0
    acc._update_total()
    closed = acc.mark_day_close()

    class _Tomorrow:
        @staticmethod
        def now():
            import datetime as _dt
            return _dt.datetime.now() + _dt.timedelta(days=1)
    monkeypatch.setattr(ag, "datetime", _Tomorrow)
    assert acc.day_baseline() == pytest.approx(closed), "次日基准未采用昨日日终总资产"


def test_agent_budget_daily_is_persisted(agent_account):
    """日基准字段必须落盘(修复前状态文件只有 total/date → 重启即丢)。"""
    acc, st = agent_account
    acc.day_baseline()
    d = json.loads(st.read_text(encoding="utf-8"))
    for k in ("day_open_date", "day_open_total", "close_date", "close_total"):
        assert k in d, f"状态文件缺字段 {k}"


def test_profile_budget_weekly_not_nano(tmp_path, monkeypatch):
    """P1-1 核心: 画像级预算写入 -3% 后 weekly_pnl 必须 ≈ -0.03, 不再是 1e-9 量级。"""
    import risk.budget as B
    monkeypatch.setattr(B, "_budget_file_path",
                        lambda agent=None: tmp_path / "risk_budget_test.json", raising=False)
    b = B.RiskBudget({"risk": {}}, 1_000_000.0)
    b.record_pnl(-0.03, 970_000.0)
    wk = b.state["weekly_pnl"]
    assert abs(wk) > 1e-6, f"weekly_pnl 仍是垃圾量级: {wk!r}"
    assert wk == pytest.approx(-0.03, abs=1e-4)
