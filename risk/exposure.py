"""单票目标暴露 vs 开仓闸 — 单一真源 (P1-2a, 2026-09-28)
================================================================
背景 (2026-09-28 横向业绩审计, 真实数据 data/agent_aggregate.json):
  5 个 Agent 名义"全自动交易", 实际平均暴露只有 1.3%~11.1% (98% 现金):
    上班族中短线 11.12% / 价值投资者 7.83% / 趋势跟踪者 5.38% /
    新手入门 2.51% / 短线狙击手 1.29%
  收益被稀释到噪声级 (-0.88%~+1.55%)。

根因: 『趋势状态 → 目标暴露』与『单票上限』散落三处, 没有单一真源, 无可观测诊断:
  - strategies/prev_close_executor.py:24  TREND_TARGET_PCT = {up:0.8, range:0.5, down:0.3}
  - core/engine.py:1741                    _target = min(TREND_TARGET_PCT.get(_tr,0.5), max_position_pct)
  - risk/position.py::plan_positions       Kelly 份额, 完全不知道 max_position_pct (无单票上限截断)

本模块 = 唯一真源 + 运行时诊断 + 可调旋钮:
  1. DEFAULT_* 默认值 == 2026-09-28 现状 (历史可比; 默认行为逐笔不变)
  2. load_policy(cfg, agent_style, profile_name) → ExposurePolicy   (消费 config.yaml exposure 段)
  3. ExposurePolicy.target_exposure(trend) / gate_pct() / size_entry() / cap_shares()
  4. ExposureDiag: 每次建仓决策记账 → 『目标暴露 X% / 闸值 Y% / 当前实际暴露 Z% / 为什么没买』
  5. 旋钮(全部默认=现状): scale / max_position_pct / max_positions /
     min_cash_reserve_pct / enforce_plan_cap

配置 (config.yaml, 缺省段 = 完全等于改动前行为):
  exposure:
    trend_target_pct: {up: 0.8, range: 0.5, down: 0.3}
    max_position_pct: null        # null → 跟随 agent_trading_style / risk.max_position_pct
    max_positions: null           # null → 跟随 risk.max_positions
    scale: 1.0                    # ⭐提曝光旋钮: >1 放大目标暴露(仍受单票上限截断)
    min_cash_reserve_pct: 0.0     # 现金保留比例(0=现状)
    enforce_plan_cap: false       # true → plan_positions 也做单票上限截断(默认关=现状)
    diagnostics: true             # 建仓决策诊断日志
"""
from __future__ import annotations

import logging

logger = logging.getLogger("aurora.exposure")

# ── 默认值: 与 2026-09-28 现状逐字一致 (历史可比 / 默认行为不变) ──
DEFAULT_TREND_TARGET_PCT = {"up": 0.8, "range": 0.5, "down": 0.3}
DEFAULT_TARGET_FALLBACK = 0.5            # 未知趋势 → engine.py 原 `TREND_TARGET_PCT.get(_tr, 0.5)`
DEFAULT_MAX_POSITION_PCT = 0.28          # engine.py 原兜底 (risk.max_position_pct 缺省)
DEFAULT_MAX_POSITIONS = 5                # cfg.risk.max_positions 缺省
DEFAULT_SCALE = 1.0
DEFAULT_MIN_CASH_RESERVE_PCT = 0.0
LOT = 100                                # A股 1手 = 100股


class ExposurePolicy:
    """单票暴露策略 (单一真源) — 由 load_policy() 构造"""

    def __init__(self, trend_target_pct=None, max_position_pct=None, max_positions=None,
                 scale=DEFAULT_SCALE, min_cash_reserve_pct=DEFAULT_MIN_CASH_RESERVE_PCT,
                 enforce_plan_cap=False, diagnostics=True, source="", kelly_scale=1.0):
        self.trend_target_pct = dict(trend_target_pct or DEFAULT_TREND_TARGET_PCT)
        self._cap = max_position_pct          # None = 不设单票上限(与原 `_mpp<=0` 分支等价)
        self.max_positions = max_positions
        self.scale = float(scale)
        self.min_cash_reserve_pct = float(min_cash_reserve_pct)
        self.enforce_plan_cap = bool(enforce_plan_cap)
        self.diagnostics = bool(diagnostics)
        # ⭐ Kelly 份额旋钮: 计划层(plan_positions) 的曝光由 Kelly×置信度决定,
        #   实测(2026-09-28 干跑) 3 个计划只占 6.3% 资金 → 这是 98% 持币的主因之一。
        #   1.0 = 现状(逐笔不变); >1 放大计划份额(仍受 enforce_plan_cap 的单票上限约束)。
        self.kelly_scale = float(kelly_scale if kelly_scale is not None else 1.0)
        self.source = source

    # ── 闸值(单票上限) ──
    @property
    def gate_pct(self):
        return self._cap

    def gate_pct_display(self) -> str:
        return "无上限" if not self._cap or self._cap <= 0 else f"{self._cap*100:.1f}%"

    # ── 趋势 → 目标暴露 (含旋钮 scale, 再受单票上限截断) ──
    def target_exposure(self, trend: str) -> float:
        base = float(self.trend_target_pct.get(trend, DEFAULT_TARGET_FALLBACK))
        target = base * self.scale
        if self._cap and self._cap > 0:
            target = min(target, float(self._cap))
        return max(0.0, target)

    def raw_target(self, trend: str) -> float:
        """未截断的目标(诊断用)"""
        return float(self.trend_target_pct.get(trend, DEFAULT_TARGET_FALLBACK)) * self.scale

    # ── 份数: 与 engine.py 原式 `int(cash * target / price / 100) * 100` 完全一致 ──
    def size_entry(self, cash: float, price: float, trend: str) -> int:
        if price is None or price <= 0:
            return 0
        usable = max(0.0, float(cash) * (1.0 - self.min_cash_reserve_pct))
        return int(usable * self.target_exposure(trend) / price / LOT) * LOT

    # ── 单票上限对应的最大股数(开仓闸口径; plan_positions 用) ──
    def cap_shares(self, capital: float, price: float) -> int:
        if not self._cap or self._cap <= 0 or not price or price <= 0:
            return 0
        return int(float(capital) * float(self._cap) / price / LOT) * LOT

    # ── 目标总仓位(多票时, 诊断用) ──
    def target_total_exposure(self, trend: str) -> float:
        n = self.max_positions or DEFAULT_MAX_POSITIONS
        return min(1.0, self.target_exposure(trend) * n)


class ExposureDiag:
    """建仓决策诊断 — 记录『为什么没买』, 每次运行输出一行汇总。

    目标暴露 X% / 闸值 Y% / 当前实际暴露 Z% / 为什么没买(top 原因)
    """

    def __init__(self, policy: ExposurePolicy = None):
        self.policy = policy
        self.buy = 0
        self.reasons = {}
        self.planned_shares = 0
        self.target_pct = None
        self.trend = None

    def note(self, reason: str, n: int = 1):
        if not reason:
            reason = "unknown"
        self.reasons[reason] = self.reasons.get(reason, 0) + n

    def note_buy(self, shares: int, trend: str = "", target_pct: float = None):
        self.buy += 1
        self.planned_shares += int(shares or 0)
        if trend:
            self.trend = trend
        if target_pct is not None:
            self.target_pct = target_pct

    def actual_exposure(self, account) -> float:
        try:
            total = float(getattr(account, "total_value", 0) or 0)
            if total <= 0:
                return 0.0
            pos_val = 0.0
            for _c, _p in (getattr(account, "positions", {}) or {}).items():
                _sh = float(_p.get("shares", 0) or 0)
                _px = float(_p.get("current_price") or _p.get("avg_cost", 0) or 0)
                pos_val += _sh * _px
            return pos_val / total
        except Exception:
            return 0.0

    def summary(self, account=None) -> str:
        pol = self.policy
        tgt = "?" if self.target_pct is None else f"{self.target_pct*100:.1f}%"
        gate = pol.gate_pct_display() if pol else "?"
        act = f"{self.actual_exposure(account)*100:.1f}%" if account is not None else "?"
        why = ", ".join(f"{k}×{v}" for k, v in
                        sorted(self.reasons.items(), key=lambda kv: -kv[1])[:6]) or "无"
        return (f"[Expose] 目标暴露 {tgt}(趋势{self.trend or '?'}) / 闸值(单票上限) {gate} / "
                f"当前实际暴露 {act} / 本轮买入 {self.buy} 笔({self.planned_shares}股) / "
                f"为什么没买: {why}")


def _resolve_cap(cfg: dict, agent_style: dict, exposure_cfg: dict):
    """单票上限解析 — 与 engine.py 原逻辑逐字等价:
    agent_trading_style.max_position_pct → cfg.risk.max_position_pct → 0.28 (仅键缺失时兜底;
    键存在但非法(如 None) → 原实现 except: pass = 不设上限; 此处保持一致)
    """
    if exposure_cfg.get("max_position_pct") is not None:
        try:
            v = float(exposure_cfg["max_position_pct"])
            return v if v > 0 else None
        except Exception:
            return None
    try:
        return float((agent_style or {}).get(
            "max_position_pct",
            ((cfg or {}).get("risk", {}) or {}).get("max_position_pct", DEFAULT_MAX_POSITION_PCT)))
    except Exception:
        return None                      # 与原 except: pass (不截断) 等价


def load_policy(cfg: dict = None, agent_style: dict = None, profile_name: str = None) -> ExposurePolicy:
    """从 config.yaml `exposure` 段 + 画像读取策略 (缺省 = 现状, 保证历史可比)"""
    cfg = cfg or {}
    exposure_cfg = cfg.get("exposure") or {}
    if not isinstance(exposure_cfg, dict):
        exposure_cfg = {}
    trend = exposure_cfg.get("trend_target_pct") or cfg.get("target_exposure") or DEFAULT_TREND_TARGET_PCT
    if not isinstance(trend, dict) or not trend:
        trend = DEFAULT_TREND_TARGET_PCT
    max_pos = exposure_cfg.get("max_positions")
    if max_pos is None:
        max_pos = (cfg.get("risk", {}) or {}).get("max_positions", DEFAULT_MAX_POSITIONS)
    try:
        max_pos = int(max_pos)
    except Exception:
        max_pos = DEFAULT_MAX_POSITIONS
    cap = _resolve_cap(cfg, agent_style or {}, exposure_cfg)
    # ──────── 提曝光护栏 (2026-09-28 操作清单#2) ────────
    #   背景: 实测 5 个账户暴露仅 1.3%~11.1%(≈98% 现金), 但**没有任何战法实测为稳定正期望**
    #   (prev_close_B 118笔/胜率30%/均值-1.20% 已判 dead; chan_buy1 34/100 dead)。
    #   结论: 放大暴露只会放大噪声 → 旋钮保留但**必须显式二次确认**才能越过 1.0,
    #         防"静默把风险放大 1.8~5 倍"(影响面实测: 单账户 9~27万 → 42~48万)。
    _allow_raise = bool(exposure_cfg.get("allow_raise", False))
    _scale = float(exposure_cfg.get("scale", DEFAULT_SCALE) or DEFAULT_SCALE)
    _kelly_scale = float(exposure_cfg.get("kelly_scale", 1.0) or 1.0)
    if not _allow_raise:
        if _scale > 1.0:
            logger.warning("[Expose] scale=%.2f > 1 被护栏钳制为 1.0 —— 需显式 exposure.allow_raise: true" % _scale)
            _scale = 1.0
        if _kelly_scale > 1.0:
            logger.warning("[Expose] kelly_scale=%.2f > 1 被护栏钳制为 1.0 —— 需显式 exposure.allow_raise: true"
                           % _kelly_scale)
            _kelly_scale = 1.0
    pol = ExposurePolicy(
        trend_target_pct=trend,
        max_position_pct=cap,
        max_positions=max_pos,
        scale=_scale,
        min_cash_reserve_pct=exposure_cfg.get("min_cash_reserve_pct", DEFAULT_MIN_CASH_RESERVE_PCT),
        enforce_plan_cap=exposure_cfg.get("enforce_plan_cap", False),
        diagnostics=exposure_cfg.get("diagnostics", True),
        kelly_scale=_kelly_scale,
        source=f"profile={profile_name or '-'}",
    )
    return pol


def plan_gate(policy: ExposurePolicy, capital: float, price: float, kelly_fraction: float):
    """开仓闸 — plan_positions 口径 (K式仓位 × 单票上限截断, 消费同一真源)

    Returns: (shares, capped: bool)
      enforce_plan_cap=False (默认) → 不做截断 = 改动前行为逐笔不变
      enforce_plan_cap=True         → min(kelly 份额, 单票上限份额)
    """
    if not price or price <= 0:
        return 0, False
    raw = max(LOT, int(float(capital) * float(kelly_fraction) / price / LOT) * LOT)
    if not policy or not policy.enforce_plan_cap:
        return raw, False
    cap = policy.cap_shares(capital, price)
    if cap and raw > cap:
        return cap, True
    return raw, False
