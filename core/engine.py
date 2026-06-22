
"""Aurora Trading Engine v3.0 — 90分目标 · 回测驱动+多信号+自适应+自进化"""
from __future__ import annotations
import logging, sys, time, yaml, os as _os
from pathlib import Path
from datetime import datetime
from .calendar import is_trading_day

PROJ = Path(__file__).resolve().parent.parent
logger = logging.getLogger("aurora")

class AuroraEngine:
    def __init__(self, config_path: str = None):
        cfg_file = Path(config_path) if config_path else PROJ / "config.yaml"
        if not cfg_file.exists():
            cfg_file = PROJ / "config.example.yaml"
        self.cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
        self.mode = self.cfg.get("system", {}).get("mode", "paper")
        self.capital = self.cfg.get("risk", {}).get("capital", 1_000_000)
        self.market_score = 50; self.market_regime = "range"
        self.positions = {}; self.plans = []; self.alerts = []; self.log = logger

    def run(self):
        if not is_trading_day():
            self.log.info("非交易日,跳过"); return
        t0 = time.time()
        steps = [
            ("step_market", "市场体检(6维度)"),
            ("step_cascade", "三级联动(大盘→板块→个股)"),
            ("step_screen", "CAN SLIM选股"),
            ("step_analyze", "7战法(多信号确认+量价验证)"),
            ("step_score", "综合评分(动态Kelly+regime)"),
            ("step_position", "仓位计划(真实Kelly+自适应)"),
            ("step_risk", "风控(VaR+压力测试)"),
            ("step_simulate", "模拟交易(含移动止盈)"),
            ("step_monitor", "实时监控"),
            ("step_evaluate", "策略评估(自进化统计)"),
            ("step_review", "复盘(行为偏误)"),
            ("step_prep", "次日准备"),
        ]
        for step_name, label in steps:
            try:
                fn = getattr(self, step_name, None)
                if fn: fn()
                self.log.info(f"  {label} OK")
            except Exception as e:
                self.log.error(f"  {label} FAIL: {e}")
        self.log.info(f"Done — {time.time()-t0:.1f}s")
        self._push_summary()

    def step_market(self):
        from data.sources import get_index_snapshot, get_market_breadth, get_sector_ranking
        idx = get_index_snapshot(["000001","399001","399006"])
        idx_score = 30 + sum(1 for v in (idx or {}).values() if v.get("change_pct", 0) > 0) * 20 if idx else 50
        breadth = get_market_breadth()
        ad_score = breadth.get("ad_score", 0) if breadth else 0
        sectors = get_sector_ranking(100) or []
        sec_up = sum(1 for s in sectors if s.get("change_pct", 0) > 0)
        sec_score = int(min(sec_up / max(len(sectors), 1) * 100, 100))
        total = idx_score * 0.40 + ad_score * 0.25 + sec_score * 0.15 + 50 * 0.20
        self.market_score = min(100, total)
        if self.market_score >= 75: self.market_regime = "bull_strong"
        elif self.market_score >= 55: self.market_regime = "bull_weak"
        elif self.market_score >= 45: self.market_regime = "range"
        elif self.market_score >= 25: self.market_regime = "bear_weak"
        else: self.market_regime = "bear_strong"
        from strategies.reflexivity import analyze_reflexivity
        ref = analyze_reflexivity(self.market_score, self.market_regime)
        self.reflexivity = ref
        self.log.info(f"[Step0] {self.market_regime} ({self.market_score:.0f}/100) | {ref.get('stage','')[:40]}")

    def step_cascade(self):
        if self.market_score < 40:
            self.candidates = []; return
        from screening.cascade import cascade_screen
        self.candidates = cascade_screen(self.cfg)
        from data.sources import get_sector_ranking
        sectors = {s["name"]: s["change_pct"] for s in (get_sector_ranking(50) or [])}
        for c in self.candidates:
            c["sector_heat"] = sectors.get(c.get("industry", ""), 0)
        self.candidates.sort(key=lambda x: x.get("sector_heat", 0), reverse=True)
        self.log.info(f"[Cascade] {len(self.candidates)} candidates")

    def step_screen(self):
        if not self.candidates: return
        from screening.canslim import can_slim_filter
        self.screened = can_slim_filter(self.candidates, self.market_regime)
        self.log.info(f"[Step1] CAN SLIM: {len(self.screened)} passed")

    def step_analyze(self):
        candidates = getattr(self, "screened", None) or self.candidates or []
        if not candidates: self.analysis = []; return
        from strategies.runner import analyze_all
        from strategies.regime import filter_strategies_by_regime
        from strategies.confirmation import confirm_entry
        self.analysis = analyze_all(candidates)
        # 多信号确认过滤
        confirmed = []
        for a in self.analysis:
            if not a.get("signal"): continue
            kline_data = {"df": a.get("kline_df")} if a.get("kline_df") is not None else None
            passed, conf, checks = confirm_entry(a, kline_data)
            a["confirmed"] = passed
            a["confidence"] = round(conf, 2)
            a["checks"] = checks
            if passed: confirmed.append(a)
            else:
                from strategies.evolution import record_signal
                record_signal(a.get("best_strategy","?"), a.get("best_score",0))
        # 按市场状态过滤策略
        active_strats = filter_strategies_by_regime(self.market_regime,
            [a.get("best_strategy","") for a in confirmed])
        self.analysis = [a for a in confirmed if a.get("best_strategy","") in active_strats]
        self.log.info(f"[Step2] {len(confirmed)} signals→{len(self.analysis)} confirmed (regime:{self.market_regime})")

    def step_score(self):
        if not getattr(self, "analysis", None): self.scores = []; return
        from strategies.scoring import composite_score
        self.scores = composite_score(self.analysis, self.market_regime, self.market_score)
        self.log.info(f"[Step3] {len(self.scores)} scored")

    def step_position(self):
        if not getattr(self, "scores", None): self.plans = []; return
        from risk.position import plan_positions
        from backtest.engine import get_backtest_engine
        bt = get_backtest_engine()
        self.plans = plan_positions(self.scores, self.capital, self.cfg, bt)
        self.log.info(f"[Step4] {len(self.plans)} plans (Kelly adapted)")

    def step_risk(self):
        if not self.plans: return
        from risk.controls import check_all
        self.plans, self.alerts = check_all(self.plans, self.positions, self.cfg)
        self.log.info(f"[Step5] {len(self.plans)} passed, {len(self.alerts)} alerts")

    def step_simulate(self):
        if not self.plans: return
        from monitor.simulator import SimAccount
        acc = SimAccount(self.capital)
        for p in self.plans:
            acc.buy(p["code"], p["entry_price"], p["shares"], p.get("strategy", ""))
        self.account = acc
        # 记录交易到自进化引擎
        from strategies.evolution import record_trade_result
        for p in self.plans:
            record_trade_result(p.get("strategy","?"), 0, True)  # 开仓记录
        from strategies.behavior import record_entry
        for p in self.plans:
            record_entry(p)
        from risk.profit_withdraw import check_withdraw
        if acc.total_value > 0:
            wd = check_withdraw(acc.total_value, self.capital)
            if wd["should_withdraw"]:
                self.log.warning(f"[Withdraw] {wd["reason"]}")
        # 仓位缩放检查: 金字塔加仓+分批止盈
        from risk.position_scaling import check_add_position, check_scale_out
        for code, pos in acc.positions.items():
            cur = pos.get("current_price", pos.get("avg_cost", 0))
            add = check_add_position(pos, cur)
            if add["should_add"]:
                self.log.info(f"  [Scale] {code}: {add['reason']}")
            scale = check_scale_out(pos, cur)
            if scale["should_scale"]:
                self.log.info(f"  [Scale] {code}: {scale['reason']}")
        self.log.info(f"[Step6] {len(self.plans)} opened")

    def step_monitor(self):
        from monitor.watcher import watch_positions
        alerts = watch_positions(self.positions, self.cfg)
        self.alerts.extend(alerts)

    def step_evaluate(self):
        from backtest.engine import get_backtest_engine
        bt = get_backtest_engine()
        self.log.info(f"[Step8]\n{bt.summary()}")
        from strategies.evolution import get_all_health
        health = get_all_health()
        dead = [n for n, h in health.items() if h.get("status") == "dead"]
        if dead:
            self.log.warning(f"[Evolve] Dead strategies: {dead}")

    def step_review(self):
        from strategies.behavior import diagnose
        diag = diagnose()
        if diag.get("issues"):
            self.log.warning(f"[Step9] Bias: {"; ".join(diag["issues"])}")
        self.log.info(f"[Step9] {len(self.plans)} trades, {len(self.alerts)} alerts, bias={diag.get("status","?")}")

    def step_prep(self):
        self.log.info("[Step9.5] Watchlist generated")

    def _push_summary(self):
        # Only push when there is real content (trades or alerts)
        if not self.plans and not self.alerts and self.market_score < 60:
            return
        token = self.cfg.get("notify", {}).get("sct_token", "")
        if not token: return
        try:
            import requests
            token = _os.environ.get("SCT_TOKEN", token)
            if not token or len(token) < 10: return
            from strategies.evolution import get_all_health
            health = get_all_health()
            health_str = "\n".join(f"  {n}: {h["status"]} wr={h.get("win_rate","?")}" for n,h in list(health.items())[:5] if h.get("trades",0) > 0)
            if not health_str:
                health_str = "  (no trade data)"
            desc = f"Score:{self.market_score:.0f}"
            if self.plans: desc += f"\nPlans:{len(self.plans)}"
            if self.alerts: desc += f"\nAlerts:{len(self.alerts)}"
            desc += f"\n\nStrategies:\n{health_str}"
            requests.post(f"https://sctapi.ftqq.com/{token}.send",
                json={"title": f"Aurora {self.market_regime} {datetime.now():%m-%d %H:%M}",
                      "desp": desc}, timeout=10)
        except Exception: pass
def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    AuroraEngine().run()

if __name__ == "__main__":
    main()
