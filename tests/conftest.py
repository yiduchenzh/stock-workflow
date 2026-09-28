import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ═══ 测试隔离 (2026-09-27) ═══
# executor/sim_account.py 在检测到调用栈含 "tests" 时, 把账户状态改写到
#   data/sim_state_test.json + data/sim_trades_test.json
# 但这两个文件**跨 pytest 轮次残留** → 下一轮的 `positions == {}` 类断言被历史持仓污染
#   (实例: tests/test_pipeline.py::TestEngine::test_init 因 2026-09-25 残留的 000001 持仓长期挂掉)。
# 处理: 每次会话开始先清掉隔离账户文件, 保证"新会话=空账户"; 生产文件 data/sim_state.json 不受影响。
import pytest
from pathlib import Path

_ISOLATED_ACCOUNT_FILES = [
    Path(__file__).resolve().parent.parent / "data" / name
    for name in ("sim_state_test.json", "sim_trades_test.json")
]


@pytest.fixture(scope="session", autouse=True)
def _clean_isolated_account():
    """会话级: 清空上一轮遗留的隔离模拟账户(不影响生产 sim_state.json)"""
    for p in _ISOLATED_ACCOUNT_FILES:
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    yield


# ═══ 生产状态文件守卫 + 落盘路径隔离 (2026-09-28) ═══
# 两起实测事故(2026-09-27, 非推测):
#  ① tests/test_risk.py 调 record_trade()/check_all() → 写生产 data/risk_state.json,
#     内容 = 测试常量 {"breaker":true,"consec":3,"daily_pnl":-0.1,"peak_value":0.0,...}
#     → 生产熔断 True + peak 0.0, 引擎 step_risk 会清空全部开仓计划。
#  ② tests/test_evolution_r24.py unlink+写生产 data/strategy_evolution.json(fixture 键
#     'g'/'b') → 复盘报告『策略健康度』表渲染出单字母策略名。
# 修法(§1 变体3 标准写法): 会话内把「会落盘」的模块路径指到 tmp, 并对生产状态文件做
#   字节快照 —— 会话结束校验, 被改动则还原并打印告警。
_PROJ = Path(__file__).resolve().parent.parent
_PRODUCTION_STATE_FILES = [
    _PROJ / "data" / name for name in (
        "risk_state.json", "risk_budget.json", "strategy_evolution.json",
        "beliefs.json", "sim_state.json", "sim_trades.json",
    )
]


@pytest.fixture(scope="session", autouse=True)
def _isolate_production_state(tmp_path_factory):
    """会话级: 隔离会落盘的模块路径 + 生产状态文件快照/校验/还原"""
    import os as _os
    tmp = tmp_path_factory.mktemp("aurora_isolated_state")
    # ① 落盘路径隔离
    _os.environ["AURORA_RISK_STATE"] = str(tmp / "risk_state_test.json")
    import risk.budget as _budget
    _orig_budget_path = _budget._budget_file_path
    _budget._budget_file_path = lambda: tmp / "risk_budget_test.json"
    import strategies.evolution as _evo
    _orig_evo_data = _evo.DATA
    _evo.DATA = tmp / "strategy_evolution_test.json"
    # ② 快照
    snap = {}
    for p in _PRODUCTION_STATE_FILES:
        try:
            snap[p] = p.read_bytes()
        except Exception:
            snap[p] = None
    yield
    # ③ 校验 + 还原
    dirty = []
    for p, blob in snap.items():
        try:
            cur = p.read_bytes()
        except Exception:
            cur = None
        if cur != blob:
            dirty.append(p.name)
            if blob is not None:
                p.write_bytes(blob)
            else:
                try:
                    p.unlink()
                except Exception:
                    pass
    _budget._budget_file_path = _orig_budget_path
    _evo.DATA = _orig_evo_data
    _os.environ.pop("AURORA_RISK_STATE", None)
    if dirty:
        print(f"\n[conftest] ⚠️ 测试改写了生产状态文件, 已还原: {dirty}")
