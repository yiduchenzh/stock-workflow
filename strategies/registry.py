"""策略注册表 — 存活/禁用单一真源 (P1-2b, 2026-09-28)
====================================================
背景 (2026-09-28 横向业绩审计, 数据 data/beliefs.json):
  14 个战法里 7 个从零成交 (死战法):
    sector_rotation / wave_point / mean_reversion / chan_ / naked_ /
    elliott_wave / mtf_resonance     ← trades=0
  有成交的 7 个:
    momentum_breakout(12) / chan_sell3(17) / chan_buy3(3) / naked_supply_demand(15) /
    chan_buy1(21) / naked_engulf(1) / prev_close_B(23)

本模块 = 『哪些策略存活、哪些显式下线、为什么』的单一真源 (0 死代码原则):
  - 真删: elliott_wave (模块零引用 + 自声明 NotYetConnected) ;
          chan_ / naked_ (beliefs 占位键, 不是策略 —— 通配前缀, 只在模糊匹配里当先验用)
  - 显式下线(不删): wave_point / mean_reversion / sector_rotation / mtf_resonance
          —— 四者仍在活跃信号链路上 (runner.py:66-72,136-143 / scoring.py:35-43),
          删除会牵动 engine/API/backtest/profiling 多处; 按老陈『不该删、只是默认关』
          的规则改为显式 disabled 标记 + 收集点闸门 + 引擎启动日志。

旋钮 (config.yaml, 缺省=下线这 4 个):
  strategies:
    disabled: [wave_point, mean_reversion, sector_rotation, mtf_resonance]
    # 置 [] 即恢复全部信号收集 = 2026-09-28 之前的行为
"""
from __future__ import annotations

import logging

logger = logging.getLogger("aurora.registry")

# ── 零成交死战法 (2026-09-28 审计证据: data/beliefs.json trades=0) ──
ZERO_TRADE_STRATEGIES = (
    "sector_rotation",      # 板块轮动: runner.py:136-143 只在 code==sector_best_code 时加成
    "wave_point",           # 波段低点: runner.py:66-67 (config.yaml strategies.wave_point.enabled)
    "mean_reversion",       # 均值回归: runner.py:70-72 (无权重闸门 —— 与 momentum 不一致)
    "elliott_wave",         # 艾略特波浪: 模块自声明 NotYetConnected, 零调用点 → 已删除
    "mtf_resonance",        # 多周期共振: scoring.py:35-43 仅作评分加成
    "chan_",                # ❌ 不是策略: beliefs 占位通配键 (前缀先验) → 已删除
    "naked_",               # ❌ 不是策略: beliefs 占位通配键 (前缀先验) → 已删除
)

# ── 真删的 (模块/键已移除, 不可再启用) ──
DELETED = ("elliott_wave", "chan_", "naked_")

# ── 显式下线的默认集合 (不删, 一键可恢复) ──
DEFAULT_DISABLED = ("wave_point", "mean_reversion", "sector_rotation", "mtf_resonance")

# ── 已成交策略 (审计: data/beliefs.json trades>0) — 存活基线, 任何清理都不得误伤 ──
LIVE_STRATEGIES = (
    "momentum_breakout", "chan_sell3", "chan_buy3", "naked_supply_demand",
    "chan_buy1", "naked_engulf", "prev_close_B",
)

# ── 全部已知策略名 (信号收集点可产出的名字; 用于报告/信念校验) ──
KNOWN_STRATEGIES = tuple(sorted(set(LIVE_STRATEGIES) | set(DEFAULT_DISABLED) | {
    "prev_close_A", "chan_buy2", "chan_sell1", "chan_sell2", "chan_theory",
    "naked_pinbar", "naked_insidebar", "naked_fakey", "naked_k",
    "first_board", "pullback", "ma_breakout", "test_line", "123_rule",
    "williams_r", "williams_compression", "orb", "sector_rotation",
}))

# ── 垃圾/哨兵键 (报告与信念表必须过滤, 否则出现 'b'/'g'/'unknown' 单字母行) ──
SENTINEL_KEYS = ("unknown", "?", "", "none", "null", "test", "t", "x")


class StrategyRegistry:
    """存活策略注册表 — 实例化时读 config.yaml strategies.disabled"""

    def __init__(self, disabled=None):
        if disabled is None:
            disabled = DEFAULT_DISABLED
        self.disabled = tuple(sorted({str(d) for d in disabled if d}))

    @classmethod
    def from_config(cls, cfg: dict = None) -> "StrategyRegistry":
        cfg = cfg or {}
        block = cfg.get("strategies") or {}
        if isinstance(block, dict) and "disabled" in block:
            d = block.get("disabled")
            if d is None:
                d = DEFAULT_DISABLED
            elif isinstance(d, str):
                d = [x.strip() for x in d.split(",") if x.strip()]
            return cls(d)
        return cls(DEFAULT_DISABLED)

    def is_disabled(self, name: str) -> bool:
        return bool(name) and name in self.disabled

    def collect_allowed(self, name: str) -> bool:
        """信号收集闸门: False = 不收集该策略信号(下线)"""
        return not self.is_disabled(name)

    def filter_names(self, names):
        return [n for n in names if not self.is_disabled(n)]

    def summary(self) -> str:
        return (f"[Registry] 存活策略 {len(LIVE_STRATEGIES)} / 显式下线 {len(self.disabled)} "
                f"{list(self.disabled)} / 已删除 {list(DELETED)}")

    def disabled_reason(self, name: str) -> str:
        return "零成交死战法(2026-09-28 审计 beliefs.trades=0) → 显式下线" if self.is_disabled(name) else ""


# ── 模块级默认实例 (runner/scoring 的收集闸门直接用; 引擎启动时可用 from_config 覆盖) ──
_REGISTRY = StrategyRegistry()


def get_registry() -> StrategyRegistry:
    return _REGISTRY


def set_registry(reg: StrategyRegistry):
    global _REGISTRY
    _REGISTRY = reg or StrategyRegistry()


def is_disabled(name: str) -> bool:
    return _REGISTRY.is_disabled(name)


def collect_allowed(name: str) -> bool:
    return _REGISTRY.collect_allowed(name)


def is_valid_strategy_name(name: str) -> bool:
    """报告/信念表用: 过滤哨兵键与单字母垃圾键 (P2a 根因防护)"""
    if not name or not isinstance(name, str):
        return False
    n = name.strip()
    if n.lower() in SENTINEL_KEYS or len(n) < 3:
        return False
    if n.startswith("_"):
        return False          # 元数据键(_meta 等)不是策略
    return True


def filter_health_rows(health: dict):
    """把健康度表切成 (有效行, 隔离行) —— 报告只渲染有效行, 隔离行单列备注。

    _meta/下划线开头的元数据键直接丢弃(既不是策略, 也不是污染键)。
    """
    valid, quarantined = {}, {}
    for name, h in (health or {}).items():
        if isinstance(name, str) and name.startswith("_"):
            continue
        (valid if is_valid_strategy_name(name) else quarantined)[name] = h
    return valid, quarantined
