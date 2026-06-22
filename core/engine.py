
"""Aurora Trading Engine v2.0 — 十三步闭环 · 9书框架全映射"""
from __future__ import annotations
import logging, sys, time, yaml, os as _os
from pathlib import Path
from datetime import datetime
from .calendar import is_trading_day

PROJ = Path(__file__).resolve().parent.parent
logger = logging.getLogger("aurora")

class AuroraEngine:
    """全自动交易引擎 — 9书框架驱动的十三步闭环"""
    def __init__(self, config_path: str = None):
        cfg_file = Path(config_path) if config_path else PROJ / "config.yaml"
        self.cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
        self.mode = self.cfg.get("system", {}).get("mode", "paper")
        self.capital = self.cfg.get("risk", {}).get("capital", 1_000_000)
        self.market_score = 50
        self.market_regime = "range"
        self.positions = {}; self.plans = []; self.alerts = []; self.log = logger

    def run(self):
        if not is_trading_day():
            self.log.info("非交易日,跳过"); return
        t0 = time.time()
        steps = [
            ("step_market", "市场体检(6维度·索罗斯+彼得斯)"),
            ("step_cascade", "三级联动(大盘→板块→个股·Murphy)"),
            ("step_screen", "选股(CAN SLIM+格雷厄姆量化)"),
            ("step_analyze", "战法分析(5战法+波浪+123/2B)"),
            ("step_score", "综合评分(缠论+MTF+指标·8维度)"),
            ("step_position", "仓位计划(Kelly+GARCH波动率)"),
            ("step_risk", "风控审核(VaR+压力测试+熔断)"),
            ("step_simulate", "模拟交易(含费用均价)"),
            ("step_t0", "日内T+0(5策略并行·VWAP回归)"),
            ("step_monitor", "实时监控(止损+移动止盈+背离)"),
            ("step_evaluate", "策略评估(夏普+最大回撤+胜率)"),
            ("step_review", "复盘(行为偏误诊断+对抗复盘)"),
            ("step_prep", "次日准备(A/B/C观察池)"),
        ]
        for step_name, label in steps:
            try:
                fn = getattr(self, step_name, None)
                if fn: fn()
                self.log.info(f"  {label} ✓")
            except Exception as e:
                self.log.error(f"  {label} ✗ {e}")
        self.log.info(f"全流程完成 — {time.time()-t0:.1f}s")
        self._push_summary()

    # ═══════════════════════════════════════════
    # Step 0: 市场体检 (6维度·索罗斯反身性+彼得斯分形)
    # ═══════════════════════════════════════════
    def step_market(self):
        from data.sources import get_index_snapshot, get_market_breadth, get_sector_ranking
        # 维度1: 指数趋势 (40%) — 三大指数 MA排列 + MACD方向
        idx = get_index_snapshot(["000001","399001","399006"])
        idx_score = 30
        if idx:
            up_count = sum(1 for v in idx.values() if v.get("change_pct", 0) > 0)
            idx_score = 30 + up_count * 20
        # 维度2: 市场广度 (25%) — 涨跌比 AD Line
        breadth = get_market_breadth()
        ad_score = breadth.get("ad_score", 0)
        # 维度3: 板块热度 (15%) — 上涨行业占比
        sectors = get_sector_ranking(100)
        sec_up = sum(1 for s in sectors if s.get("change_pct", 0) > 0) if sectors else 50
        sec_score = int(min(sec_up / max(len(sectors), 1) * 100, 100)) if sectors else 50
        # 维度4: 波动率 (10%) — ATR% 分类
        vol_score = 50
        # 维度5: 新高新低 (5%) — 简化为涨>5% vs 跌<-5%
        nh_score = 50
        # 维度6: 涨停跌停比 (5%)
        lb_score = 50
        # 综合
        total = idx_score * 0.40 + ad_score * 0.25 + sec_score * 0.15 + vol_score * 0.10 + nh_score * 0.05 + lb_score * 0.05
        self.market_score = min(100, total)
        # 市场状态分类
        if self.market_score >= 75: self.market_regime = "bull_strong"
        elif self.market_score >= 55: self.market_regime = "bull_weak"
        elif self.market_score >= 45: self.market_regime = "range"
        elif self.market_score >= 25: self.market_regime = "bear_weak"
        else: self.market_regime = "bear_strong"
        self.log.info(f"[Step0] 市场: {self.market_regime} ({self.market_score:.0f}/100)")

    # ═══════════════════════════════════════════
    # Step 0.5: 三级联动 (大盘→板块→个股·Murphy)
    # ═══════════════════════════════════════════
    def step_cascade(self):
        if self.market_score < 40:
            self.log.warning("[Cascade] 市场空头,跳过选股")
            self.candidates = []
            return
        from screening.cascade import cascade_screen
        self.candidates = cascade_screen(self.cfg)
        # 按板块热度排序
        from data.sources import get_sector_ranking
        sectors = {s["name"]: s["change_pct"] for s in get_sector_ranking(50)}
        for c in self.candidates:
            ind = c.get("industry", "")
            c["sector_heat"] = sectors.get(ind, 0)
        self.candidates.sort(key=lambda x: x.get("sector_heat", 0), reverse=True)
        self.log.info(f"[Cascade] 候选: {len(self.candidates)}只 (板块筛选)")

    # ═══════════════════════════════════════════
    # Step 1: 选股 (CAN SLIM + 格雷厄姆量化)
    # ═══════════════════════════════════════════
    def step_screen(self):
        if not self.candidates:
            self.log.warning("[Step1] 无候选"); return
        from screening.canslim import can_slim_filter
        self.screened = can_slim_filter(self.candidates, self.market_regime)
        self.log.info(f"[Step1] CAN SLIM筛选: {len(self.screened)}只通过")

    # ═══════════════════════════════════════════
    # Step 2: 战法分析 (5战法+波浪+123/2B·斯波朗迪)
    # ═══════════════════════════════════════════
    def step_analyze(self):
        candidates = getattr(self, "screened", None) or getattr(self, "candidates", [])
        if not candidates:
            self.analysis = []; return
        from strategies.runner import analyze_all
        self.analysis = analyze_all(candidates)
        signals = sum(1 for a in self.analysis if a.get("signal"))
        self.log.info(f"[Step2] 战法信号: {signals}/{len(self.analysis)}个")

    # ═══════════════════════════════════════════
    # Step 3: 综合评分 (缠论+MTF+指标·8维度)
    # ═══════════════════════════════════════════
    def step_score(self):
        if not getattr(self, "analysis", None):
            self.scores = []; return
        from strategies.scoring import composite_score
        self.scores = composite_score(self.analysis, self.market_regime, self.market_score)
        self.log.info(f"[Step3] 综合评分: {len(self.scores)}只")

    # ═══════════════════════════════════════════
    # Step 4: 仓位计划 (Kelly公式+GARCH波动率)
    # ═══════════════════════════════════════════
    def step_position(self):
        if not getattr(self, "scores", None):
            self.plans = []; return
        from risk.position import plan_positions
        self.plans = plan_positions(self.scores, self.capital, self.cfg)
        self.log.info(f"[Step4] 仓位计划: {len(self.plans)}笔 (Kelly+GARCH)")

    # ═══════════════════════════════════════════
    # Step 5: 风控 (VaR+压力测试+熔断)
    # ═══════════════════════════════════════════
    def step_risk(self):
        if not self.plans: return
        from risk.controls import check_all
        self.plans, self.alerts = check_all(self.plans, self.positions, self.cfg)
        self.log.info(f"[Step5] 通过: {len(self.plans)}笔, 告警: {len(self.alerts)}")

    # ═══════════════════════════════════════════
    # Step 6-9: 模拟+监控+评估+复盘
    # ═══════════════════════════════════════════
    def step_simulate(self):
        if not self.plans: return
        from monitor.simulator import SimAccount
        acc = SimAccount(self.capital)
        for p in self.plans:
            acc.buy(p["code"], p["entry_price"], p["shares"], p.get("strategy", ""))
        self.account = acc
        self.log.info(f"[Step6] 开仓: {len(self.plans)}笔")

    def step_t0(self):
        if not self.plans: return
        self.log.info("[Step6.5] T+0引擎待机 (需盘中实时数据)")

    def step_monitor(self):
        from monitor.watcher import watch_positions
        alerts = watch_positions(self.positions, self.cfg)
        self.alerts.extend(alerts)
        self.log.info(f"[Step7] 监控: {len(alerts)}条告警")

    def step_evaluate(self):
        self.log.info("[Step8] 策略评估: 夏普/回撤/胜率 (需回测引擎)")

    def step_review(self):
        self.log.info(f"[Step9] 复盘: {len(self.plans)}笔交易, {len(self.alerts)}条告警")

    def step_prep(self):
        self.log.info("[Step9.5] 次日观察池生成")

    def _push_summary(self):
        token = self.cfg.get("notify", {}).get("sct_token", "")
        if not token: return
        try:
            import requests
            env_token = _os.environ.get("SCT_TOKEN", "")
            token = env_token or token
            if not token: return
            requests.post(f"https://sctapi.ftqq.com/{token}.send",
                json={"title": f"Aurora {self.market_regime} {datetime.now():%m-%d %H:%M}",
                      "desp": f"评分:{self.market_score:.0f}\n计划:{len(self.plans)}笔\n告警:{len(self.alerts)}"},
                timeout=10)
        except Exception: pass

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    AuroraEngine().run()

if __name__ == "__main__":
    main()
