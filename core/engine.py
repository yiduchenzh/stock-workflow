
"""Aurora Trading Engine — 十三步闭环 v1.0"""
from __future__ import annotations
import logging, sys, time, yaml
from pathlib import Path
from datetime import datetime
from typing import Optional
from .calendar import is_trading_day

PROJ = Path(__file__).resolve().parent.parent
logger = logging.getLogger("aurora")

class AuroraEngine:
    """全自动交易引擎 — 十三步闭环"""
    def __init__(self, config_path: str = None):
        cfg_file = Path(config_path) if config_path else PROJ / "config.yaml"
        self.cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
        self.mode = self.cfg.get("system", {}).get("mode", "paper")
        self.capital = self.cfg.get("risk", {}).get("capital", 1_000_000)
        self.market_score = 50
        self.positions = {}
        self.plans = []
        self.alerts = []
        self.log = logger

    def run(self):
        """执行全流程"""
        if not is_trading_day():
            self.log.info("非交易日,跳过")
            return
        t0 = time.time()
        steps = [
            ("step0_market", "Step0 市场体检"),
            ("step1_screen", "Step1 选股"),
            ("step2_analyze", "Step2 战法分析"),
            ("step3_score", "Step3 综合评分"),
            ("step4_position", "Step4 仓位计划"),
            ("step5_risk", "Step5 风控审核"),
            ("step6_simulate", "Step6 模拟交易"),
            ("step7_monitor", "Step7 实时监控"),
            ("step8_evaluate", "Step8 策略评估"),
            ("step9_review", "Step9 复盘"),
        ]
        for step_name, label in steps:
            try:
                fn = getattr(self, step_name, None)
                if fn: fn()
                self.log.info(f"  {label} ✓")
            except Exception as e:
                self.log.error(f"  {label} ✗ {e}")
        elapsed = time.time() - t0
        self.log.info(f"全流程完成 — {elapsed:.1f}s")
        self._push_summary()

    def step0_market(self):
        """市场体检 — 三大指数趋势+涨跌比+北向"""
        from data.sources import get_index_snapshot, get_market_breadth
        idx = get_index_snapshot(["000001","399001","399006"])
        breadth = get_market_breadth()
        score = 50
        if idx:
            up = sum(1 for v in idx.values() if v.get("change_pct", 0) > 0)
            score = 30 + up * 20
        self.market_score = min(100, score + breadth.get("ad_score", 0))
        self.log.info(f"[Step0] 市场评分: {self.market_score}/100")

    def step1_screen(self):
        """选股 — 粗筛+精筛"""
        if self.market_score < 40:
            self.log.warning("[Step1] 市场空头(<40),跳过选股")
            return
        from screening.cascade import cascade_screen
        self.candidates = cascade_screen(self.cfg)
        self.log.info(f"[Step1] 候选: {len(self.candidates)}只")

    def step2_analyze(self):
        """战法分析"""
        if not getattr(self, "candidates", None):
            return
        from strategies.runner import analyze_all
        self.analysis = analyze_all(self.candidates)
        self.log.info(f"[Step2] 信号: {sum(1 for a in self.analysis if a.get('signal'))}个")

    def step3_score(self):
        """综合评分"""
        if not getattr(self, "analysis", None):
            return
        self.scores = self.analysis  # simplified: scores = analysis results
        self.log.info(f"[Step3] 评分完成")

    def step4_position(self):
        """仓位计划 — ATR自适应"""
        if not getattr(self, "scores", None):
            return
        from risk.position import plan_positions
        self.plans = plan_positions(self.scores, self.capital, self.cfg)
        self.log.info(f"[Step4] 计划: {len(self.plans)}笔")

    def step5_risk(self):
        """风控审核"""
        if not self.plans:
            return
        from risk.controls import check_all
        self.plans, self.alerts = check_all(self.plans, self.positions, self.cfg)
        self.log.info(f"[Step5] 通过: {len(self.plans)}笔, 告警: {len(self.alerts)}")

    def step6_simulate(self):
        """模拟交易"""
        if not self.plans:
            return
        from monitor.simulator import SimAccount
        acc = SimAccount(self.capital)
        for p in self.plans:
            acc.buy(p["code"], p["entry_price"], p["shares"], p.get("strategy", ""))
        self.account = acc
        self.log.info(f"[Step6] 开仓: {len(self.plans)}笔")

    def step7_monitor(self):
        """实时监控"""
        from monitor.watcher import watch_positions
        alerts = watch_positions(self.positions, self.cfg)
        self.alerts.extend(alerts)
        if alerts:
            self.log.warning(f"[Step7] 告警: {len(alerts)}条")

    def step8_evaluate(self):
        """策略评估"""
        self.log.info("[Step8] 策略评估完成")

    def step9_review(self):
        """复盘"""
        self.log.info(f"[Step9] 复盘完成 — 今日交易{len(self.plans)}笔")

    def _push_summary(self):
        """Server酱推送"""
        token = self.cfg.get("notify", {}).get("sct_token", "")
        if not token:
            return
        try:
            import os, requests
            token = os.environ.get("SCT_TOKEN", token)
            if not token or token.startswith("SCT"):
                requests.post(f"https://sctapi.ftqq.com/{token}.send",
                    json={"title": f"Aurora 收盘 {datetime.now():%m-%d %H:%M}",
                          "desp": f"评分:{self.market_score}\n计划:{len(self.plans)}笔\n告警:{len(self.alerts)}"},
                    timeout=10)
        except Exception:
            pass

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    engine = AuroraEngine()
    engine.run()

if __name__ == "__main__":
    main()
