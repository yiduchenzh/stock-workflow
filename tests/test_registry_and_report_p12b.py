"""P1-2b 零成交死战法下线 + P2a 报告策略名修复 — 回归测试 (2026-09-28)"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path

import pytest

import strategies.evolution as _evo
from strategies.registry import (DEFAULT_DISABLED, DELETED, LIVE_STRATEGIES,
                                 StrategyRegistry, filter_health_rows,
                                 is_disabled, is_valid_strategy_name)


def test_zero_trade_seven_resolution():
    """7 个零成交死战法: 3 真删(elliott_wave + chan_/naked_ 占位键) + 4 显式下线"""
    assert set(DELETED) == {"elliott_wave", "chan_", "naked_"}
    assert set(DEFAULT_DISABLED) == {"wave_point", "mean_reversion",
                                     "sector_rotation", "mtf_resonance"}
    assert len(DELETED) + len(DEFAULT_DISABLED) == 7
    # 已成交的 7 个策略绝不能被误伤
    for s in LIVE_STRATEGIES:
        assert s not in DEFAULT_DISABLED and s not in DELETED


def test_deleted_module_is_gone_and_unreferenced():
    proj = Path(__file__).resolve().parent.parent
    assert not (proj / "strategies" / "elliott_wave.py").exists()
    # 全仓不得再有 import strategies.elliott_wave / from strategies.elliott_wave
    import subprocess
    r = subprocess.run(["git", "grep", "-n", "-E",
                        r"(import|from)\s+strategies\.elliott_wave", "--", "*.py"],
                       cwd=str(proj), capture_output=True, text=True)
    assert r.returncode != 0, f"仍有悬空引用:{r.stdout}"
    # beliefs 默认先验里也不再有它
    from strategies.bayesian_belief import _DEFAULT_BELIEFS, _WILDCARD_PRIORS
    assert "elliott_wave" not in _DEFAULT_BELIEFS
    assert "chan_" not in _DEFAULT_BELIEFS and "naked_" not in _DEFAULT_BELIEFS
    assert set(_WILDCARD_PRIORS) == {"chan_", "naked_"}   # 通配先验改为不持久化


def test_registry_from_config():
    reg = StrategyRegistry.from_config({"strategies": {"disabled": ["a", "b"]}})
    assert reg.disabled == ("a", "b")
    assert reg.is_disabled("a") and not reg.is_disabled("c")
    # 配置缺省 → 4 个零成交战法
    assert StrategyRegistry.from_config({}).disabled == tuple(sorted(DEFAULT_DISABLED))
    # 显式置空 → 恢复全部收集(可逆旋钮)
    assert StrategyRegistry.from_config({"strategies": {"disabled": []}}).disabled == ()


def test_signal_collection_gates_present_at_every_collect_point():
    """4 个下线战法的**每个**信号收集点都必须有闸门(防漏网)"""
    proj = Path(__file__).resolve().parent.parent
    runner = (proj / "strategies" / "runner.py").read_text(encoding="utf-8")
    scoring = (proj / "strategies" / "scoring.py").read_text(encoding="utf-8")
    assert 'collect_allowed("wave_point")' in runner
    assert 'collect_allowed("mean_reversion")' in runner
    assert 'collect_allowed("sector_rotation")' in runner
    assert '_ca("mtf_resonance")' in scoring
    assert "from strategies.registry import collect_allowed" in runner


def test_invalid_name_filter_covers_report_bug():
    """P2a 根因键: 单字母('b'/'g')与哨兵键('unknown')必须被过滤"""
    for bad in ("b", "g", "t", "x", "unknown", "", "?", "  ", "None", None, 123):
        assert not is_valid_strategy_name(bad), bad
    for good in LIVE_STRATEGIES + ("prev_close_A", "chan_buy2", "naked_pinbar"):
        assert is_valid_strategy_name(good), good


def test_get_all_health_excludes_test_pollution_keys(tmp_path, monkeypatch):
    """策略健康度不得再渲染测试 fixture 键('b'/'g')与 'unknown'"""
    f = tmp_path / "strategy_evolution_test.json"
    monkeypatch.setattr(_evo, "DATA", f)
    for i in range(10):
        _evo.record_signal("b", 40)
        _evo.record_trade_result("b", -0.02, False)
    for i in range(10):
        _evo.record_signal("g", 65)
        _evo.record_trade_result("g", 0.03, True)
    _evo.record_trade_result("unknown", 0.09, True)
    _evo.record_trade_result("chan_buy1", 0.02, True)
    health = _evo.get_all_health()
    assert set(health) == {"chan_buy1"}, health
    assert _evo.get_quarantined_names() == ["b", "g", "unknown"]
    # 需要时仍可取(隔离, 但显式请求)
    assert set(_evo.get_all_health(include_quarantined=True)) == {"b", "g", "unknown", "chan_buy1"}


def test_filter_health_rows_split():
    valid, q = filter_health_rows({"b": {}, "momentum_breakout": {}, "unknown": {}})
    assert set(valid) == {"momentum_breakout"} and set(q) == {"b", "unknown"}


def test_review_report_table_renders_full_names(tmp_path, monkeypatch):
    """复盘报告『策略健康度』表: 完整策略名 + 下线标注, 无单字母行"""
    import notify.review_report as rr
    from strategies.registry import StrategyRegistry, set_registry

    f = tmp_path / "strategy_evolution_test.json"
    monkeypatch.setattr(_evo, "DATA", f)
    for i in range(12):
        _evo.record_trade_result("momentum_breakout", 0.03 if i < 7 else -0.02, i < 7)
    for i in range(10):
        _evo.record_trade_result("b", -0.02, False)      # 测试污染键(旧 bug 源)
    _evo.record_trade_result("unknown", 0.09, True)      # 哨兵键
    monkeypatch.setattr(rr, "REPORT_DIR", tmp_path / "reports")

    class _Eng:
        market_regime = "range"
        market_score = 49.0
        plans = []
        alerts = []
        candidates = []
        positions = {}
        capital = 1_000_000
        cfg = {"strategies": {"disabled": ["wave_point", "mean_reversion",
                                           "sector_rotation", "mtf_resonance"]}}

    report = rr.generate_report(_Eng())
    assert "momentum_breakout" in report
    assert "存活策略(有成交记录)" in report
    assert "显式下线(零成交死战法)" in report
    assert "已隔离无效键" in report and "'b'" in report and "'unknown'" in report
    # 关键: 表格行里不能再出现单字母策略名
    for line in report.splitlines():
        if line.startswith("| ") and "状态" not in line and "---" not in line:
            first = line.split("|")[1].strip()
            assert len(first) >= 3, f"表格首列仍是单字母/哨兵键: {line}"
    assert (tmp_path / "reports").exists()
