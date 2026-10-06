"""单个AI交易员Agent — 独立SimAccount + AuroraEngine"""
import sys, json, logging
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("aurora.agent")

AGENT_CAPITAL = 1_000_000  # 每个Agent 100万

class TraderAgent:
    def __init__(self, profile_name: str):
        self.profile_name = profile_name
        self._setup_dirs()
        self._init_account()
        self.engine = None
        # v14.50 修复(P0-B, 2026-09-04 周复盘): 跨Agent去重注入丢失
        #   原coordinator把 exclude/claims 直接设在 agent.engine 上, 但 run_intraday()
        #   内部 _fresh_engine() 每次重建 AuroraEngine → 注入全部丢失 → 短线/上班族
        #   同分钟买入同票(持仓100%重叠)。修复: 存agent实例, _fresh_engine后统一注入。
        self._pending_exclude = set()
        self._pending_claims = {}

    def set_exclusions(self, exclude_codes=None, claims=None):
        """设置跨Agent去重: exclude_codes=已持仓代码集合, claims=(code,strategy)->agent映射"""
        if exclude_codes:
            self._pending_exclude = set(exclude_codes)
        if claims:
            self._pending_claims = dict(claims)

    def _apply_exclusions(self):
        """_fresh_engine后注入去重(在step_screen前调用)"""
        try:
            if self._pending_exclude and self.engine is not None:
                self.engine.agent_exclude_codes = set(self._pending_exclude)
                logger.info(f"[Dedup] {self.profile_name} 注入排除{len(self._pending_exclude)}只: "
                            f"{sorted(self._pending_exclude)[:5]}{'...' if len(self._pending_exclude) > 5 else ''}")
            if self._pending_claims and self.engine is not None:
                self.engine.agent_signal_claims = dict(self._pending_claims)
                logger.info(f"[SignalDedup] {self.profile_name} 继承{len(self._pending_claims)}条信号认领")
        except Exception as e:
            logger.warning(f"[Dedup] {self.profile_name} 注入失败: {e}")

    def _setup_dirs(self):
        root = Path(__file__).resolve().parent.parent
        self.data_dir = root / "data" / f"agent_{self.profile_name}"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.data_dir / "state.json"
        self.trades_file = self.data_dir / "trades.json"

    def _init_account(self):
        from executor.sim_account import SimAccount
        import yaml
        cfg_path = Path(__file__).resolve().parent.parent / "config.yaml"
        cfg = yaml.safe_load(cfg_path.read_text("utf-8"))
        # 使用真实SimAccount但重写状态文件路径
        self.account = AgentSimAccount(AGENT_CAPITAL, cfg, self.state_file, self.trades_file)
        self.capital = AGENT_CAPITAL

    @property
    def total_value(self):
        return self.account.total_value if self.account else self.capital

    def run_morning(self, run_phase="morning"):
        """晨扫全流程: 与daily_run.py --phase morning一致"""
        self._fresh_engine(run_phase)
        self._apply_exclusions()  # v14.50: _fresh_engine后注入跨Agent去重
        self.engine.step_market()
        self.engine.step_cascade()
        self.engine.step_screen()
        self.engine.step_analyze()
        self.engine.step_score()
        self.engine.step_position()
        self.engine.step_risk()
        self.engine.step_simulate()
        self._sync_account()
        return self.engine

    def run_intraday(self, run_phase="monitor"):
        """盘中全流程: 与daily_run.py --phase monitor一致"""
        self._fresh_engine(run_phase)
        self._apply_exclusions()  # v14.50: _fresh_engine后注入跨Agent去重
        self.engine.step_market()
        self.engine.step_cascade()
        self.engine.step_screen()
        self.engine.step_analyze()
        self.engine.step_score()
        self.engine.step_position()
        self.engine.step_risk()
        self.engine.step_simulate()
        self.engine.step_monitor()
        self.engine.step_rebalance()
        self._sync_account()
        return self.engine

    def _fresh_engine(self, phase):
        import os
        os.environ["AURORA_AGENT"] = self.profile_name
        from core.engine import AuroraEngine
        self.engine = AuroraEngine()
        self.engine.profile_name = self.profile_name
        self.engine._apply_profile()
        self.engine.phase = phase
        self.engine.account = self.account
        self.engine.positions = dict(self.account.positions)
        # MTF方案分配: 前3个Agent用A(周线日线60分), 后2个用B(日线小时15分)
        scheme_a = ["上班族中短线", "短线狙击手", "趋势跟踪者"]
        self.engine.mtf_scheme = "A" if self.profile_name in scheme_a else "B"
        # [Opt] 分类施策: 注入Agent专属筛参数
        from profiling.strategy_mapping import get_screening_params
        self.engine.agent_screening = get_screening_params(self.profile_name)
        self.engine.agent_screening["profile_name"] = self.profile_name
        # ── P0升级: 注入Agent差异化交易风格 ──
        from strategies.regime import get_agent_trading_style, get_regime_screening_strategy
        self.engine.agent_trading_style = get_agent_trading_style(self.profile_name)
        # ── P0升级: 注入regime感知选股策略 (后续在step_cascade中用于替换粗筛阈值) ──
        regime = getattr(self.engine, 'market_regime', 'range')
        self.engine.regime_screening = get_regime_screening_strategy(regime)
        self.engine.monitor_interval = self.engine.agent_trading_style.get("monitor_interval", 30)

    def close_day(self) -> dict:
        """2026-09-24 weekly-review P0-2: Agent-side close handling (was missing).

        Agent positions' current_price was only set once at buy time (fill_price);
        multi_agent had NO close entry at all -> valuation == cost forever
        (float pnl always 0) and mark_day_close() never ran -> close_total == 0
        -> day_baseline() degraded -> per-profile risk_budget daily ~1e-9
        -> weekly -5% / monthly -8% budget gate never fires.
        This fills the gap: refresh close prices -> recompute total -> freeze day close.
        No trading action (read quotes + persist state only).
        """
        acc = self.account
        updated = 0
        try:
            codes = list(acc.positions.keys())
            if codes:
                from data.sources import get_tencent_quotes
                q = get_tencent_quotes(codes) or {}
                for c, p in acc.positions.items():
                    px = (q.get(c) or {}).get("price")
                    if px and float(px) > 0:
                        p["current_price"] = float(px)
                        updated += 1
                acc._update_total()
        except Exception as e:
            logger.warning("[Close] %s price refresh failed: %s" % (self.profile_name, e))
        close_total = 0.0
        try:
            close_total = float(acc.mark_day_close())
            acc._save()
        except Exception as e:
            logger.warning("[Close] %s mark_day_close failed: %s" % (self.profile_name, e))
        logger.info("[Close] %s: refreshed=%d close_total=%.0f total=%.0f"
                    % (self.profile_name, updated, close_total, float(acc.total_value)))
        # 2026-09-24 weekly-review P0-2: profile budget entry (same as
        #   engine.step_close -> budget.record_pnl). RiskBudget resolves its file
        #   from the AURORA_AGENT env var, so set it before instantiating.
        try:
            import os as _os
            _os.environ["AURORA_AGENT"] = self.profile_name
            from risk.budget import RiskBudget
            _b = RiskBudget(getattr(acc, "cfg", None) or {}, float(self.capital))
            _base = float(acc.day_baseline())
            _cur = float(acc.total_value)
            _dpnl = (_cur - _base) / _base if _base > 0 else 0.0
            _b.record_pnl(_dpnl, _cur)
            logger.info("[Close] %s budget: daily=%+.4f%% base=%.0f current=%.0f"
                        % (self.profile_name, _dpnl * 100, _base, _cur))
        except Exception as e:
            logger.warning("[Close] %s budget record failed: %s" % (self.profile_name, e))
        return {"profile": self.profile_name, "prices": updated,
                "close_total": round(close_total, 2),
                "total_value": round(float(acc.total_value), 2)}

    def _sync_account(self):
        if self.engine and hasattr(self.engine, 'account'):
            self.account = self.engine.account
            self.account._save()
            self._save_pnl()

    def _save_pnl(self):
        """保存到独立文件"""
        pass  # 由AgentSimAccount._save处理

    def get_summary(self) -> dict:
        total = self.account.total_value
        pos_detail = [{"code":c,"shares":p.get("shares",0),
                       "cost":round(p.get("avg_cost",0),2)}
                      for c,p in self.account.positions.items()]
        return {
            "profile": self.profile_name,
            "cash": round(self.account.cash, 2),
            "total_value": round(total, 2),
            "positions": len(self.account.positions),
            "positions_detail": pos_detail,
            "pnl": round(total - self.capital, 2),
            "return_pct": round((total - self.capital) / self.capital * 100, 4),
        }


class AgentSimAccount:
    """Agent专用模拟账户 — 继承SimAccount核心逻辑, 使用独立文件"""
    def __init__(self, capital, cfg, state_path, trades_path):
        from executor.sim_account import SimAccount
        # v14.41e: _inner注入独立路径, 防止写全局sim_state.json污染主账户
        self._inner = SimAccount(capital, cfg, state_path=Path(state_path),
                                 trades_path=Path(trades_path))
        self.capital = capital
        self.cfg = cfg
        self.state_path = Path(state_path)
        self.trades_path = Path(trades_path)
        self.positions = {}
        self.cash = capital
        self.today_buys = {}
        self.trades = []
        self.total_value = capital
        # ⭐ v14.51(2026-09-18 周复盘 P1-1): 日基准字段(与 SimAccount 同口径)
        self.prev_total = float(capital)   # 加载时总资产(兜底)
        self.day_open_date = ""            # 当日基准日期
        self.day_open_total = 0.0          # 当日基准总资产(当日首次固化)
        self.close_date = ""               # 最近日终记录日期
        self.close_total = 0.0             # 该日总资产(次日作基准)
        self._load()

    def _load(self):
        if self.state_path.exists():
            try:
                from executor.sim_account import _read_json_text
                d = json.loads(_read_json_text(self.state_path))
                self.cash = d.get("cash", self.capital)
                self.positions = {k: dict(v) for k, v in d.get("positions", {}).items()}
                self.today_buys = dict(d.get("today_buys", {}))
                # v14.41d: 记录加载时的总资产(昨收/上次保存), 供engine计算"今日盈亏"基准
                self.prev_total = float(d.get("total", self.total_value))
                # ⭐ v14.51(2026-09-18 P1-1): 日基准字段落盘/读回
                self.day_open_date = str(d.get("day_open_date", "") or "")
                self.day_open_total = float(d.get("day_open_total", 0) or 0)
                self.close_date = str(d.get("close_date", "") or "")
                self.close_total = float(d.get("close_total", 0) or 0)
                saved_date = d.get("date", "")
                if saved_date and saved_date != str(datetime.now().date()):
                    self.today_buys = {}
            except: pass
        if self.trades_path.exists():
            try:
                from executor.sim_account import _read_json_text
                self.trades = json.loads(_read_json_text(self.trades_path))
            except: self.trades = []
        self._update_total()

    def _save(self):
        self._update_total()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        # v14.46: 显式 UTF-8 写入(原默认编码→GBK, 读UTF-8失败→trades加载空→覆盖丢历史)
        self.state_path.write_text(json.dumps({
            "capital": self.capital, "cash": round(self.cash, 2),
            "positions": {k: dict(v) for k, v in self.positions.items()},
            "today_buys": dict(self.today_buys),
            "total": round(self.total_value, 2),
            "date": str(datetime.now().date()),
            # ⭐ v14.51(2026-09-18 P1-1): 日基准随状态落盘
            "day_open_date": self.day_open_date,
            "day_open_total": round(self.day_open_total, 2),
            "close_date": self.close_date,
            "close_total": round(self.close_total, 2),
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        self.trades_path.write_text(json.dumps(self.trades[-500:], indent=2, ensure_ascii=False), encoding="utf-8")

    def day_baseline(self) -> float:
        """当日盈亏基准(总资产) — 每日首次调用固化并落盘, 同日复用。

        ⭐ v14.51(2026-09-18 周复盘 P1-1): AgentSimAccount 原缺此方法 → engine 回退
        prev_total(同日被 _save 刷新) → daily_pnl≡0 → 画像 risk_budget weekly_pnl
        恒 1e-9 → 周-5%/月-8% 闸永不触发。与 SimAccount.day_baseline 同口径。
        优先级: ① 昨日日终(close_total) ② 当日已固化 ③ 加载时总资产 ④ 本金。
        """
        today = str(datetime.now().date())
        if self.day_open_date == today and self.day_open_total > 0:
            return self.day_open_total
        base = 0.0
        if self.close_date and self.close_date != today and self.close_total > 0:
            base = self.close_total
        elif getattr(self, "prev_total", 0) and float(self.prev_total) > 0:
            base = float(self.prev_total)
        if base <= 0:
            base = float(self.capital)
        self.day_open_date = today
        self.day_open_total = float(base)
        self._save()
        return float(base)

    def mark_day_close(self) -> float:
        """日终记录总资产(供次日作当日基准)。⭐ v14.51(2026-09-18 P1-1)"""
        self.close_date = str(datetime.now().date())
        self.close_total = float(self.total_value)
        self._save()
        return self.close_total

    def _update_total(self):
        pv = sum(p.get("shares",0)*p.get("current_price",p.get("avg_cost",0))
                 for p in self.positions.values())
        self.total_value = self.cash + pv

    def buy(self, code, price, shares, reason="", context=None):
        """委托给_inner处理, 再同步回自身 (v14.41e: 支持六问证据链context参数)"""
        r = self._inner.buy(code, price, shares, reason, context=context)
        if r.get("success"):
            self.cash = self._inner.cash
            self.positions = dict(self._inner.positions)
            self.today_buys = dict(self._inner.today_buys)
            self.trades = list(self._inner.trades)
            self._save()
        return r

    def sell(self, code, price, shares, reason=""):
        r = self._inner.sell(code, price, shares, reason)
        if r.get("success"):
            self.cash = self._inner.cash
            self.positions = dict(self._inner.positions)
            self.today_buys = dict(self._inner.today_buys)
            self.trades = list(self._inner.trades)
            self._save()
        return r
