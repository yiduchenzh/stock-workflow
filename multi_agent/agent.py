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
        self._load()

    def _load(self):
        if self.state_path.exists():
            try:
                d = json.loads(self.state_path.read_text())
                self.cash = d.get("cash", self.capital)
                self.positions = {k: dict(v) for k, v in d.get("positions", {}).items()}
                self.today_buys = dict(d.get("today_buys", {}))
                # v14.41d: 记录加载时的总资产(昨收/上次保存), 供engine计算"今日盈亏"基准
                self.prev_total = float(d.get("total", self.total_value))
                saved_date = d.get("date", "")
                if saved_date and saved_date != str(datetime.now().date()):
                    self.today_buys = {}
            except: pass
        if self.trades_path.exists():
            try: self.trades = json.loads(self.trades_path.read_text())
            except: self.trades = []
        self._update_total()

    def _save(self):
        self._update_total()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({
            "capital": self.capital, "cash": round(self.cash, 2),
            "positions": {k: dict(v) for k, v in self.positions.items()},
            "today_buys": dict(self.today_buys),
            "total": round(self.total_value, 2),
            "date": str(datetime.now().date()),
        }, indent=2, ensure_ascii=False))
        self.trades_path.write_text(json.dumps(self.trades[-500:], indent=2, ensure_ascii=False))

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
