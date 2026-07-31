"""Aurora Trading Engine v3.0 — 完整重建版"""
from __future__ import annotations
import logging, sys, time, yaml, os as _os, urllib.request, json as _json
from pathlib import Path
from datetime import datetime
from .calendar import is_trading_day, is_market_open
from pipeline.pipeline_validator import PipelineValidator
from data.sources import get_index_snapshot, get_market_breadth, get_sector_ranking
from data.sources import get_limit_up_count, get_tencent_quotes, get_kline
from risk.garch_var import get_market_volatility_score, predict_var
from strategies.reflexivity import analyze_reflexivity
from strategies.mtf_intraday import analyze_stock
from strategies.runner import analyze_all
from strategies.regime import filter_strategies_by_regime, get_regime_config, get_dynamic_weights
from strategies.confirmation import confirm_entry
from strategies.scoring import composite_score, MLFactorScorer
from strategies.evolution import get_all_health, record_signal, record_trade_result
from strategies.behavior import record_entry, diagnose
# [Soul] 5个灵魂模块
from strategies.market_memory import market_memory
from strategies.market_sentiment import sentiment
from strategies.decision_v2 import make_decision_v2
from strategies.trade_reflector import TradeReflector
from strategies.style_adaptive import AdaptiveParams
# [Soul] 灵性增强模块
from strategies.market_intuition import calc_market_anomaly, calc_sentiment_index
from strategies.bayesian_belief import update_belief, get_adjusted_kelly
from data.xtick_adapter import get_order_book
# [Soul] 全局风险监控 + 事件驱动
from strategies.global_risk_monitor import get_overnight_risk, get_macro_cycle_phase
from strategies.global_risk_monitor import get_risk_level, adjust_regime_by_risk
from strategies.event_signals import enrich_candidates

from screening.cascade import cascade_screen
from screening.strong_stock import screen_strong_stocks
from screening.auction import auction_screen
from screening.canslim import can_slim_filter
from risk.position import plan_positions
from risk.controls import check_all, check_liquidity
from risk.position_scaling import check_add_position, check_scale_out
from risk.profit_withdraw import check_withdraw
from executor.sim_account import SimAccount
from monitor.watcher import watch_positions
from monitor.contingency import check_contingency
from backtest.engine import get_backtest_engine

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
        self.market_score = 50
        self.market_regime = "range"
        self.positions = {}
        self.plans = []
        self.alerts = []
        self.log = logger
        self.stock_losses: dict = {}
        self.paused_stocks: set = set()
        self.last_trade_date: str = ""
        self.profile_name = self.cfg.get("profiling", {}).get("active_profile", "上班族中短线")
        self._apply_profile()
        # [Soul] 灵魂模块状态变量
        self.memory_hints: dict = {}
        self.sentiment_score: float = 50.0
        self.decision_v2_result: dict = {}
        self.trade_reflections: list = []
        self.adaptive_params: dict = {}
        self.overnight_risk_level: str = "normal"
        self.overnight_score: float = 50.0
        self.macro_phase: dict = {}
        # 加载已有持仓
        try:
            self.account = SimAccount(self.capital, self.cfg)
            self.positions = dict(self.account.positions)
            if self.positions:
                self.log.info(f"[Init] 加载已有持仓: {len(self.positions)}只")
        except Exception as e:
            self.log.warning(f"[Init] 持仓加载失败: {e}")
        self.pipeline_validator = PipelineValidator(self, auto_fix=True)
        # 熔断状态检测(24h自动恢复)
        try:
            check_all([], cfg=self.cfg)
        except Exception:
            pass
        # 运行阶段标记 (由daily_run.py设置)
        self.phase = "monitor"
        self.mtf_scheme = "A"  # MTF方案: A=周线日线60分, B=日线小时15分

    def _apply_profile(self):
        try:
            from profiling.strategy_mapping import get_engine_config
            self.profile_config = get_engine_config(self.profile_name)
            pc = self.profile_config
            rc = self.cfg.get("risk", {})
            for k in ["stop_loss_pct", "take_profit_pct", "max_positions", "daily_loss_limit_pct"]:
                rc[k] = pc["risk"][k]
            if self.cfg.get("profiling", {}).get("enable_profiling", True):
                self.cfg.setdefault("risk", {}).setdefault("strategy_weights", {}).update(pc["strategy_weights"])
            # [Opt] 分类施策: 注入Agent专属信号偏好
            try:
                from profiling.strategy_mapping import get_screening_params
                sp = get_screening_params(self.profile_name)
                sig_pref = sp.get("signal_prefer", {})
                if sig_pref:
                    self.cfg.setdefault("risk", {}).setdefault("strategy_weights", {}).update(sig_pref)
                    self.log.info(f"  [SignalPrefer] {len(sig_pref)}条信号权重注入")
            except Exception:
                pass
            self.log.info("[Profile] " + self.profile_name)
        except Exception as e:
            self.log.warning("[Profile] fail: " + str(e))

    def _calc_northbound_score(self):
        """北向资金评分0-100: 同花顺北向→恒指代理二重降级"""
        score = 50
        try:
            from data.fallback_sources import get_northbound_score
            score = get_northbound_score()
            if score != 50:
                self.log.info(f"[北向] 同花顺: {score}/100")
                return score
        except Exception:
            pass
        try:
            r = urllib.request.urlopen("https://qt.gtimg.cn/q=hkHSI,sh000001", timeout=5)
            raw = r.read().decode("gbk", "replace")
            for line in raw.split(";"):
                if "~" in line:
                    parts = line.split("~")
                    if len(parts) > 32:
                        chg = float(parts[32] or 0)
                        if chg > 1: score += 20
                        elif chg > 0: score += 10
                        elif chg < -1: score -= 15
                        elif chg < 0: score -= 5
            return max(0, min(100, score))
        except Exception:
            return 50

    def _calc_macro_score(self) -> int:
        score = 50
        try:
            r = urllib.request.urlopen("https://qt.gtimg.cn/q=usINX,USDCNY,hsHSI", timeout=8)
            raw = r.read().decode("gbk")
            for line in raw.split(";"):
                if "~" not in line: continue
                parts = line.split("~")
                name = parts[1] if len(parts) > 1 else ""
                chg = float(parts[32]) if len(parts) > 32 and parts[32] else 0
                if "S&P" in name or "INX" in name:
                    if chg > 0.5: score += 15
                    elif chg > 0: score += 10
                    elif chg < -1: score -= 10
                elif "HSI" in name:
                    if chg > 1: score += 15
                    elif chg > 0: score += 10
                    elif chg < -1.5: score -= 10
                elif "CNY" in name:
                    if chg < -0.1: score += 15
                    elif chg > 0.2: score -= 10
        except Exception:
            pass
        return max(0, min(100, score))

    # ──────── step 1: market state ────────
    def step_market(self):
        idx = get_index_snapshot(["000001", "399001", "399006"])
        idx_score = 30 + sum(1 for v in (idx or {}).values() if v.get("change_pct", 0) > 0) * 20 if idx else 50
        breadth = get_market_breadth()
        ad_score = breadth.get("ad_score", 0) if breadth else 0
        sectors = get_sector_ranking(100) or []
        sec_up = sum(1 for s in sectors if s.get("change_pct", 0) > 0)
        sec_score = int(min(sec_up / max(len(sectors), 1) * 100, 100))
        nb_score = self._calc_northbound_score()
        macro_score = self._calc_macro_score()
        total = idx_score * 0.30 + ad_score * 0.10 + sec_score * 0.10 + nb_score * 0.20 + macro_score * 0.20 + 50 * 0.10

        try:
            limit_up_cnt = get_limit_up_count() or 0
            total += min(limit_up_cnt, 10)
        except Exception:
            pass
        try:
            vol_score = get_market_volatility_score()
            total = total * (1.0 + (vol_score - 50) / 200)
        except Exception:
            pass

        # [Soul] 外围市场联动检测
        try:
            ext = get_tencent_quotes(["hsHSI", "usINX", "USDCNY"])
            for ext_code in ["HSI", "INX", "USDCNY"]:
                q = ext.get(ext_code, {})
                if abs(q.get("change_pct", 0)) > 2:
                    total = max(20, total - 10)
                    self.log.warning(f"[Soul] 外围异动 {ext_code} {q.get('change_pct',0):+.1f}%")
        except Exception:
            pass

        # [Soul] 市场异常检测
        try:
            idx_kline = get_kline("000001", 60)
            if idx_kline is not None and not getattr(idx_kline, 'empty', True):
                anomaly = calc_market_anomaly(idx_kline)
                if anomaly.get("anomaly_detected"):
                    total *= 0.85
            limit_up = get_limit_up_count() or 0
            breadth_ratio = breadth.get("advance_ratio", 0.5) if breadth else 0.5
            sent_index = calc_sentiment_index(breadth_ratio, limit_up, total / 100.0, nb_score)
            if sent_index <= 20:
                total *= 0.9
            elif sent_index >= 80:
                total *= 1.05
            self.log.info(f"[Soul] sentiment_index={sent_index:.0f} anomaly={anomaly.get('anomaly_detected',False)}")
        except Exception as e:
            self.log.debug(f"[Soul] market_intuition: {e}")

        self.market_score = min(100, max(0, total))
        # regime mapping
        if nb_score < 25:
            if self.market_score >= 70: self.market_regime = "bull_weak"
            elif self.market_score >= 55: self.market_regime = "range"
            elif self.market_score >= 40: self.market_regime = "bear_weak"
            else: self.market_regime = "bear_strong"
        else:
            if self.market_score >= 70: self.market_regime = "bull_strong"
            elif self.market_score >= 55: self.market_regime = "bull_weak"
            elif self.market_score >= 40: self.market_regime = "range"
            elif self.market_score >= 20: self.market_regime = "bear_weak"
            else: self.market_regime = "bear_strong"
        ref = analyze_reflexivity(self.market_score, self.market_regime)
        self.reflexivity = ref
        self.log.info(f"[Step0] {self.market_regime} ({self.market_score:.0f}/100) | {ref.get('stage','')[:40]}")
        try:
            from strategies.regime import get_trading_advice
            self.trading_advice = get_trading_advice(self.market_regime)
            self.log.info(f"[Advice] {self.trading_advice}")
        except Exception:
            self.trading_advice = ""

        # [Soul] 市场记忆匹配
        try:
            kline_idx = get_kline("399300", 60)
            if kline_idx is not None and len(kline_idx) > 20:
                self.memory_hints = market_memory.match_current(kline_idx)
                self.log.info(f"[Soul] market_memory: {self.memory_hints.get('advice','?')}")
        except Exception as e:
            self.log.warning(f"[Soul] market_memory: {e}")

        # [Soul] 情绪呼吸
        try:
            up_stocks = breadth.get("up_count", 400) if breadth else 400
            down_stocks = breadth.get("down_count", 300) if breadth else 300
            lmt_up = get_limit_up_count() or 0
            sent_result = sentiment.compute_breath({
                "up_stocks": up_stocks, "down_stocks": down_stocks,
                "limit_up": lmt_up, "limit_down": int(lmt_up * 0.3),
                "volume_ratio": breadth.get("volume_ratio", 1) if breadth else 1,
                "northbound": nb_score,
            })
            self.sentiment_score = sent_result.get("score", 50)
            self.log.info(f"[Soul] sentiment: {sent_result.get('score',50)}/100 {sent_result.get('state','?')}")
        except Exception as e:
            self.log.warning(f"[Soul] sentiment: {e}")
            self.sentiment_score = 50

        # [Soul] 隔夜风险 + 宏观周期
        try:
            ov = get_overnight_risk()
            self.overnight_score = ov.get("score", 50)
            self.overnight_risk_level = ov.get("level", "normal")
            self.log.info(f"[Soul] overnight: score={self.overnight_score} level={self.overnight_risk_level}")
            if self.overnight_risk_level in ("high", "danger"):
                old = self.market_regime
                self.market_regime = adjust_regime_by_risk(self.market_regime, self.overnight_risk_level)
                if old != self.market_regime:
                    self.log.warning(f"[Soul] regime降级: {old} -> {self.market_regime} (risk={self.overnight_risk_level})")
        except Exception as e:
            self.log.debug(f"[Soul] get_overnight_risk: {e}")
        try:
            mc = get_macro_cycle_phase()
            self.macro_phase = mc
        except Exception as e:
            self.log.debug(f"[Soul] get_macro_cycle_phase: {e}")

        # [Soul] 每日市场快照(积累记忆)
        try:
            top5 = [s.get("name", "") for s in (sectors or [])[:5]]
            market_memory.daily_snapshot(
                market_score=self.market_score, regime=self.market_regime,
                top_sectors=top5, sentiment=self.sentiment_score)
        except Exception as e:
            self.log.debug(f"[Soul] daily_snapshot: {e}")

        # XTick盘口探针(预留)
        try:
            _ = get_order_book("000001")
        except Exception:
            pass

    # ──────── step 2: cascade screening ────────
    def step_cascade(self):
        # 个股优先: 先选股, 大盘评分作为后续权重(不作为门禁)
        # [Opt] 分类施策: 如果有Agent专属筛参数, 注入cfg
        # 从agent_trading_style提取筛选参数(优先级: agent_screening > agent_trading_style > cfg默认)
        agent_style = getattr(self, 'agent_trading_style', {})
        if hasattr(self, 'agent_screening') and self.agent_screening:
            try:
                sc = self.agent_screening
                self.log.info(f"[Cascade] Agent={sc.get('profile_name','?')} 策略={sc.get('desc','')[:20]}")
                if 'screening' not in self.cfg:
                    self.cfg['screening'] = {}
                if 'coarse' not in self.cfg['screening']:
                    self.cfg['screening']['coarse'] = {}
                c = self.cfg['screening']['coarse']
                c['max_price'] = sc.get('max_price', c.get('max_price', 200))
                c['min_mcap_yi'] = sc.get('min_mcap_yi', c.get('min_mcap_yi', 20))
                c['max_mcap_yi'] = sc.get('max_mcap_yi', c.get('max_mcap_yi', 20000))
                c['min_turnover'] = sc.get('min_turnover', c.get('min_turnover', 0.3))
                c['min_pe'] = sc.get('min_pe', c.get('min_pe', -100))
                c['max_pe'] = sc.get('max_pe', c.get('max_pe', 500))
                c['min_vol_ratio'] = sc.get('min_vol_ratio', c.get('min_vol_ratio', 0.5))
                self.log.info(f"  [Screening] 价格≤{c['max_price']} 市值{c['min_mcap_yi']}-{c['max_mcap_yi']}亿 "
                              f"换手≥{c['min_turnover']}% PE∈[{c['min_pe']},{c['max_pe']}]")
            except Exception as e:
                self.log.debug(f"[Cascade] agent_screening注入失败: {e}")
        elif agent_style:
            # 后备: 从agent_trading_style注入筛选参数
            try:
                if 'screening' not in self.cfg:
                    self.cfg['screening'] = {}
                if 'coarse' not in self.cfg['screening']:
                    self.cfg['screening']['coarse'] = {}
                c = self.cfg['screening']['coarse']
                c['max_price'] = agent_style.get('max_price', c.get('max_price', 200))
                c['min_mcap_yi'] = agent_style.get('min_mcap_yi', c.get('min_mcap_yi', 20))
                c['min_vol_ratio'] = agent_style.get('min_vol_ratio', c.get('min_vol_ratio', 0.5))
                c['min_turnover'] = agent_style.get('min_turnover', c.get('min_turnover', 0.3))
                self.log.info(f"  [AgentStyle] 价格≤{c['max_price']} 市值≥{c['min_mcap_yi']}亿 "
                              f"换手≥{c['min_turnover']}% 量比≥{c['min_vol_ratio']}")
            except Exception as e:
                self.log.debug(f"[Cascade] agent_trading_style注入失败: {e}")
        # ── P1升级: Regime感知粗筛阈值 ──
        # 在Agent专属参数之上再叠加regime自适应调整
        try:
            regime = getattr(self, 'market_regime', 'range')
            regime_screen = getattr(self, 'regime_screening', None)
            if regime_screen is None:
                from strategies.regime import get_regime_screening_strategy
                regime_screen = get_regime_screening_strategy(regime)
                self.regime_screening = regime_screen
            c = self.cfg.get('screening', {}).get('coarse', {})
            # bear_weak/bear_strong: 放低换手和量比门槛(熊市缩量)
            rs_min_turn = regime_screen.get('min_turnover')
            rs_min_vr = regime_screen.get('min_vol_ratio')
            if rs_min_turn is not None:
                old_turn = c.get('min_turnover', 0.3)
                c['min_turnover'] = min(c.get('min_turnover', 0.3), rs_min_turn)
                if old_turn != c['min_turnover']:
                    self.log.info(f"  [RegimeScreen] regime={regime} 换手阈值 {old_turn}→{c['min_turnover']}")
            if rs_min_vr is not None:
                old_vr = c.get('min_vol_ratio', 0.5)
                c['min_vol_ratio'] = min(c.get('min_vol_ratio', 0.5), rs_min_vr)
                if old_vr != c['min_vol_ratio']:
                    self.log.info(f"  [RegimeScreen] regime={regime} 量比阈值 {old_vr}→{c['min_vol_ratio']}")
        except Exception as e:
            self.log.debug(f"[RegimeScreen] 注入失败: {e}")
        self.candidates = cascade_screen(self.cfg, phase=getattr(self, 'phase', 'monitor'))
        if not self.candidates:
            self.log.info(f"[Cascade] 0 candidates")
            return
        sectors = {s["name"]: s["change_pct"] for s in (get_sector_ranking(50) or [])}
        for c in self.candidates:
            c["sector_heat"] = sectors.get(c.get("industry", ""), 0)
        self.candidates.sort(key=lambda x: x.get("sector_heat", 0), reverse=True)
        self.log.info(f"[Cascade] {len(self.candidates)} candidates")
        from data.sources import get_top_sectors, get_top_flow_stocks
        top_sectors = None
        try:
            top_sectors = get_top_sectors(15)
        except Exception:
            pass
        flow_stocks = None
        try:
            flow_stocks = get_top_flow_stocks(200)
        except Exception:
            pass
        strong = screen_strong_stocks(self.candidates, getattr(self, "northbound", None),
                                      top_sectors=top_sectors, flow_stocks=flow_stocks)
        if not strong:
            strong = screen_strong_stocks(self.candidates, getattr(self, "northbound", None),
                                          top_sectors=None, flow_stocks=flow_stocks)
        if not strong:
            self.log.warning("[Strong] 板块+资金流均无候选, 降级为裸选")
            strong = screen_strong_stocks(self.candidates, getattr(self, "northbound", None),
                                          top_sectors=None, flow_stocks=None)
        self.candidates = strong
        if self.candidates:
            self.candidates = auction_screen(self.candidates, top_n=10)
            self.log.info(f"[Auction] CC筛选后: {len(self.candidates)}只")

    # ──────── step 3: CAN SLIM ────────
    def step_screen(self):
        if not self.candidates:
            return
        self.screened = can_slim_filter(self.candidates, self.market_regime)
        self.log.info(f"[Step1] CAN SLIM: {len(self.screened)} passed")

    # ──────── step 4: analyze + signals ────────
    def step_analyze(self):
        candidates = getattr(self, "screened", None) or self.candidates or []
        if not candidates:
            self.analysis = []
            return
        self.analysis = analyze_all(candidates, market_regime=self.market_regime)
        # ── P1升级: Regime感知信号偏好调整 ──
        try:
            regime_screen = getattr(self, 'regime_screening', None)
            if regime_screen is None:
                from strategies.regime import get_regime_screening_strategy
                regime_screen = get_regime_screening_strategy(self.market_regime)
                self.regime_screening = regime_screen
            prefer_signals = regime_screen.get('prefer_signals', [])
            avoid_signals = regime_screen.get('avoid_signals', [])
            for a in self.analysis:
                strat = a.get('best_strategy', '')
                if any(strat.startswith(p) for p in prefer_signals):
                    boost = 20  # 偏好信号+20分
                    a['best_score'] = min(100, a.get('best_score', 50) + boost)
                    a['regime_boost'] = boost
                    self.log.debug(f"  [RegimeSignal] {a.get('code','')}: {strat} 偏好加分+{boost}")
                elif any(strat.startswith(av) for av in avoid_signals):
                    penalty = -30  # 回避信号-30分
                    a['best_score'] = max(0, a.get('best_score', 50) + penalty)
                    a['regime_penalty'] = penalty
                    self.log.debug(f"  [RegimeSignal] {a.get('code','')}: {strat} 回避扣分{penalty}")
        except Exception as e:
            self.log.debug(f"[RegimeSignal] 调整失败: {e}")
        try:
            for a in self.analysis:
                code = a.get("code", "")
                if code:
                    mtf = analyze_stock(code, has_position=False)
                    a["mtf_decision"] = mtf.get("decision", {})
                    a["mtf_daily"] = mtf.get("daily", {})
                    a["mtf_score"] = {"daily": mtf.get("daily", {}).get("score", 50),
                                       "m30": mtf.get("m30", {}).get("score", 50),
                                       "m5": mtf.get("m5", {}).get("score", 0)}
        except Exception:
            pass
        confirmed = []
        for a in self.analysis:
            if not a.get("signal"):
                continue
            kline_data = {"df": a.get("kline_df")} if a.get("kline_df") is not None else None
            passed, conf, checks = confirm_entry(a, kline_data)
            a["confirmed"] = passed
            a["confidence"] = round(conf, 2)
            a["checks"] = checks
            if passed:
                confirmed.append(a)
            else:
                record_signal(a.get("best_strategy", "?"), a.get("best_score", 0))
        active_strats = filter_strategies_by_regime(self.market_regime,
            [a.get("best_strategy", "") for a in confirmed])
        self.analysis = [a for a in confirmed if a.get("best_strategy", "") in active_strats]
        dyn_weights = get_dynamic_weights(self.market_score, self.market_regime)
        for a in self.analysis:
            strat = a.get("best_strategy", "")
            if strat in dyn_weights:
                a["best_score"] = a.get("best_score", 50) * (dyn_weights[strat] or 0.5)
        self.log.info(f"[DynamicWeights] {dyn_weights}")

        # [Soul] 贝叶斯信念调整评分
        try:
            for a in self.analysis:
                strat = a.get("best_strategy", "")
                base_score = a.get("best_score", 50)
                adj_kelly = get_adjusted_kelly(0.08, strat, self.market_regime)
                kelly_mult = adj_kelly / 0.08 if 0.08 > 0 else 1.0
                a["best_score"] = min(100, base_score * (0.7 + 0.3 * kelly_mult))
                a["kelly_adj"] = round(adj_kelly, 4)
        except Exception:
            pass
        self.log.info(f"[Step2] {len(confirmed)} signals -> {len(self.analysis)} confirmed (regime:{self.market_regime})")

        # [Soul] 五维融合决策
        try:
            dv2 = make_decision_v2(self)
            self.decision_v2_result = dv2
            sent_score = dv2.get("sentiment", {}).get("score", 50)
            for a in self.analysis:
                a["soul_sentiment"] = dv2.get("sentiment", {})
                a["soul_feeling"] = dv2.get("feeling", "")
                a["soul_style"] = dv2.get("style", {})
                a["soul_can_trade"] = dv2.get("can_trade", True)
                if sent_score < 30:
                    a["best_score"] = a.get("best_score", 50) * 0.85
                elif sent_score > 70:
                    a["best_score"] = a.get("best_score", 50) * 1.05
            self.log.info(f"[Soul] decision_v2: sent={sent_score} slots={dv2.get('available_slots','?')}")
        except Exception as e:
            self.log.warning(f"[Soul] decision_v2: {e}")

        # [Soul] 事件驱动信号
        try:
            if getattr(self, "analysis", None):
                codes = [a.get("code", "") for a in self.analysis if a.get("code")]
                quotes = get_tencent_quotes(codes) if codes else {}
                self.analysis = enrich_candidates(self.analysis, quotes)
                high_event = sum(1 for a in self.analysis if a.get("event_total_score", 0) >= 30)
                self.log.info(f"[Soul] event_signals: {len(self.analysis)} scored, {high_event} high-signal")
                for a in self.analysis:
                    adj = 0
                    ev = a.get("event_total_score", 0)
                    if a.get("event_undervaluation", {}).get("score", 0) >= 40: adj += 5
                    if a.get("event_buyback", {}).get("score", 0) >= 20: adj += 3
                    if a.get("event_earnings", {}).get("window_active", False): adj += 3
                    if a.get("event_limit_up", {}).get("score", 0) in range(1, 15): adj -= 5
                    if adj:
                        a["best_score"] = min(100, max(0, a.get("best_score", 50) + adj))
        except Exception as e:
            self.log.debug(f"[Soul] enrich_candidates: {e}")

        # ── P1: 4 battle.py 战法注入引擎 ──
        try:
            profile_name = getattr(self, 'profile_name', '')
            agent_style = getattr(self, 'agent_trading_style', {})
            # 从 profile_name 或 agent_trading_style 判断角色
            role = agent_style.get('role', '')
            if not role:
                if '上班族' in profile_name or 'office' in profile_name.lower():
                    role = 'office'
                elif '短线' in profile_name or 'fulltime' in profile_name.lower():
                    role = 'fulltime'
                elif '趋势' in profile_name or 'trend' in profile_name.lower():
                    role = 'trend'
                elif '价值' in profile_name or 'value' in profile_name.lower():
                    role = 'value'
            if role and getattr(self, 'analysis', None):
                battle_boost_count = 0
                if role == 'office':
                    from strategies.office_battle import check_mgp, check_lcp, check_eodm, check_sqb
                    for a in self.analysis:
                        code = a.get('code', '')
                        if not code:
                            continue
                        daily = {}; today_bar = {}; morning = {}
                        try:
                            from data.sources import get_kline, get_tencent_quotes
                            df = get_kline(code, 60)
                            if df is not None and len(df) >= 20:
                                last = df.iloc[-1]
                                prev = df.iloc[-2] if len(df) > 1 else last
                                closes = df['close'].values
                                highs = df['high'].values
                                lows = df['low'].values
                                # 计算ADX(简化版)
                                import numpy as np
                                adx_val = 25
                                try:
                                    tr = np.maximum(highs[1:] - lows[1:], abs(highs[1:] - closes[:-1]), abs(lows[1:] - closes[:-1]))
                                    atr14 = float(np.mean(tr[-14:])) if len(tr) >= 14 else float(np.mean(tr))
                                    dm_plus = np.maximum(highs[1:] - np.roll(highs,1)[1:], 0)
                                    dm_minus = np.maximum(np.roll(lows,1)[1:] - lows[1:], 0)
                                    dp = float(np.mean(dm_plus[-14:])) if len(dm_plus) >= 14 else 20
                                    dm = float(np.mean(dm_minus[-14:])) if len(dm_minus) >= 14 else 20
                                    di_p = 100 * dp / atr14 if atr14 > 0 else 20
                                    di_m = 100 * dm / atr14 if atr14 > 0 else 20
                                    dx = 100 * abs(di_p - di_m) / (di_p + di_m) if (di_p + di_m) > 0 else 20
                                    adx_val = int(dx)
                                except Exception:
                                    pass
                                # 计算MACD(简化版)
                                macd_val = 0.0
                                try:
                                    ema12 = float(np.mean(closes[-12:])) if len(closes) >= 12 else float(np.mean(closes))
                                    ema26 = float(np.mean(closes[-26:])) if len(closes) >= 26 else float(np.mean(closes))
                                    macd_val = round(ema12 - ema26, 2)
                                except Exception:
                                    pass
                                daily = {
                                    'close': float(last['close']), 'open': float(last['open']),
                                    'high': float(last['high']), 'low': float(last['low']),
                                    'volume': float(last['volume']),
                                    'ma5': float(df['close'].rolling(5).mean().iloc[-1]) if len(df) >= 5 else float(last['close']),
                                    'ma10': float(df['close'].rolling(10).mean().iloc[-1]) if len(df) >= 10 else float(last['close']),
                                    'ma20': float(df['close'].rolling(20).mean().iloc[-1]) if len(df) >= 20 else float(last['close']),
                                    'ma60': float(df['close'].rolling(60).mean().iloc[-1]) if len(df) >= 60 else float(last['close']),
                                    'ma5_slope': (float(last['close']) - float(df['close'].iloc[-5])) / float(df['close'].iloc[-5]) if len(df) >= 5 else 0,
                                    'vol': float(last['volume']),
                                    'ma5_vol': float(df['volume'].rolling(5).mean().iloc[-1]) if len(df) >= 5 else 0,
                                    'adx': adx_val, 'macd': macd_val, 'prev_low': float(prev['low']),
                                    'range_pct': (float(last['high']) - float(last['low'])) / float(prev['close']) * 100 if float(prev['close']) > 0 else 0,
                                    'squeeze_days': 0,
                                    'bollinger_width_pct': 0,
                                    'bollinger_20day_min': 0,
                                    'di_plus': 0, 'di_minus': 0,
                                }
                                today_bar = {
                                    'high': float(last['high']), 'close': float(last['close']),
                                    'range_pct': daily['range_pct'],
                                    'vol': float(last['volume']),
                                }
                            q = get_tencent_quotes([code]).get(code, {})
                            morning = {
                                'gap_pct': abs(float(q.get('price', 0)) - float(prev['close'])) / float(prev['close']) * 100 if float(prev['close']) > 0 else 0,
                                'vol_ratio': float(q.get('vol_ratio', 0)) if q.get('vol_ratio') else 1.0,
                            }
                        except Exception as ke:
                            self.log.warning(f"[Battle-Office] K线获取失败 {code}: {ke}")
                        for check_fn, name in [(check_mgp, 'MGP'), (check_lcp, 'LCP'), (check_eodm, 'EODM'), (check_sqb, 'SQB')]:
                            try:
                                kwargs = {'stock': a, 'daily': daily}
                                if name == 'MGP':
                                    kwargs['morning_data'] = morning
                                elif name in ('LCP',):
                                    kwargs['h60_last_4'] = []
                                elif name in ('EODM',):
                                    kwargs['today_bar'] = today_bar; kwargs['sector'] = {}
                                elif name in ('SQB',):
                                    kwargs['today_bar'] = today_bar
                                result = check_fn(**kwargs)
                                if result and result.get('signal'):
                                    boost = 10 + min(10, result.get('score', 25) // 10)
                                    a['best_score'] = min(100, a.get('best_score', 50) + boost)
                                    a['battle_boost'] = boost
                                    a['battle_signal'] = name
                                    battle_boost_count += 1
                                    self.log.info(f"  [Battle-Office] {code}: {name} 触发 +{boost}分")
                                    break
                            except Exception as be:
                                self.log.debug(f"[Battle-Office] {code} {name}: {be}")
                elif role == 'fulltime':
                    from strategies.fulltime_battle import check_a_mode, check_c_mode
                    for a in self.analysis:
                        code = a.get('code', '')
                        if not code:
                            continue
                        kline = None; morning = {}
                        try:
                            from data.sources import get_kline, get_tencent_quotes
                            kline_m15 = get_kline(code, 60)
                            kline_m5 = get_kline(code, 120)
                            kline = {'m5': kline_m5, 'm15': kline_m15}
                            q = get_tencent_quotes([code]).get(code, {})
                            morning = {'vol_ratio': float(q.get('vol_ratio', 0)) if q.get('vol_ratio') else 1.0}
                        except Exception as ke:
                            self.log.debug(f"[Battle-Fulltime] K线获取失败 {code}: {ke}")
                        for check_fn, name in [(check_a_mode, 'A_mode'), (check_c_mode, 'C_mode')]:
                            try:
                                result = check_fn(code, kline.get('m5') if kline else None,
                                                  kline.get('m15') if kline else None, morning) if name == 'A_mode' \
                                         else check_fn(code, kline.get('m15') if kline else None, {})
                                if result and result.get('signal') if isinstance(result, dict) and 'signal' in result else result and result.get('signal_strength', 0) >= 60:
                                    boost = 10 + min(5, result.get('score', 50) // 20)
                                    a['best_score'] = min(100, a.get('best_score', 50) + boost)
                                    a['battle_boost'] = boost
                                    a['battle_signal'] = name
                                    battle_boost_count += 1
                                    self.log.info(f"  [Battle-Fulltime] {code}: {name} 触发 +{boost}分")
                                    break
                            except Exception as be:
                                self.log.debug(f"[Battle-Fulltime] {code} {name}: {be}")
                elif role == 'trend':
                    from strategies.trend_battle import check_cup_handle, check_ma_resonance, check_ma_spread
                    for a in self.analysis:
                        code = a.get('code', '')
                        if not code:
                            continue
                        weekly = None; daily = None
                        try:
                            from data.sources import get_kline, get_kline_period
                            # 趋势跟踪需要真实周线数据
                            weekly = get_kline_period(code, "week", 52) or get_kline(code, 120)
                            daily = get_kline(code, 60)
                        except Exception as ke:
                            self.log.debug(f"[Battle-Trend] K线获取失败 {code}: {ke}")
                        for check_fn, name in [(check_cup_handle, 'CUP_HANDLE'), (check_ma_resonance, 'MA_RESONANCE'), (check_ma_spread, 'MA_SPREAD')]:
                            try:
                                result = check_fn(code, weekly, daily)
                                if result and result.get('signal') if isinstance(result, dict) and 'signal' in result else result and result.get('signal_strength', 0) >= 60:
                                    boost = 10 + min(5, result.get('score', 50) // 20)
                                    a['best_score'] = min(100, a.get('best_score', 50) + boost)
                                    a['battle_boost'] = boost
                                    a['battle_signal'] = name
                                    battle_boost_count += 1
                                    self.log.info(f"  [Battle-Trend] {code}: {name} 触发 +{boost}分")
                                    break
                            except Exception as be:
                                self.log.debug(f"[Battle-Trend] {code} {name}: {be}")
                elif role == 'value':
                    from strategies.value_battle import calc_fscore, check_value_entry
                    for a in self.analysis:
                        code = a.get('code', '')
                        if not code:
                            continue
                        fundamentals = {}
                        try:
                            from data.sources import get_tencent_quotes
                            q = get_tencent_quotes([code]).get(code, {})
                            if q:
                                fundamentals = {
                                    'pe': float(q.get('pe', 0)) if q.get('pe') else 0,
                                    'pb': float(q.get('pb', 0)) if q.get('pb') else 0,
                                    'mcap_yi': float(q.get('mcap', 0)) / 1e8 if q.get('mcap') else 0,
                                    'turnover': float(q.get('turnover', 0)) if q.get('turnover') else 0,
                                    'price': float(q.get('price', 0)) if q.get('price') else 0,
                                }
                            from data.fallback_sources import get_sectors_fallback
                            sec = get_sectors_fallback()
                            if sec:
                                a['sector_heat'] = sec[0].get('change_pct', 0)
                        except Exception:
                            pass
                        try:
                            score = calc_fscore(code, fundamentals)
                            entry_result = check_value_entry(code, score, fundamentals)
                            if entry_result.get('signal'):
                                boost = 15
                                a['best_score'] = min(100, a.get('best_score', 50) + boost)
                                a['battle_boost'] = boost
                                a['battle_signal'] = entry_result.get('strategy', 'value')
                                battle_boost_count += 1
                                self.log.info(f"  [Battle-Value] {code}: {entry_result.get('strategy','?')} 触发 +{boost}分")
                        except Exception as ve:
                            self.log.debug(f"[Battle-Value] {code}: {ve}")
                if battle_boost_count > 0:
                    self.log.info(f"[Battle] {role}战法: {battle_boost_count}只触发加分")
        except Exception as e:
            self.log.debug(f"[Battle] 战法注入失败: {e}")

    # ──────── step 5: scoring ────────
    def step_score(self):
        if not getattr(self, "analysis", None):
            self.scores = []
            return
        self.scores = composite_score(self.analysis, self.market_regime, self.market_score, mtf_scheme=getattr(self, "mtf_scheme", "A"))
        ml_scorer = MLFactorScorer()
        for s in self.scores:
            kline = s.get("kline_df")
            if kline is not None:
                ml_score = ml_scorer.predict_score(kline)
                s["ml_score"] = round(ml_score, 1)
                s["composite"] = round(s["composite"] * 0.9 + ml_score * 0.1, 1)
        self.log.info(f"[Step3] {len(self.scores)} scored (ML enhanced)")

    # ──────── step 6: position planning ────────
    def step_position(self):
        if not getattr(self, "scores", None):
            self.plans = []
            return
        # ── P1升级: 不交易规则 ──
        try:
            from risk.budget import RiskBudget
            budget = RiskBudget(self.cfg, self.capital)
            no_trade = False
            no_trade_reason = ""
            # 规则1: 极端熊市不交易
            if self.market_score < 20:
                no_trade = True
                no_trade_reason = f"极端熊市(market_score={self.market_score:.0f}<20)"
            # 规则2: 熔断激活时不交易 (由controls.py check_all维护)
            # 规则3: 连续3次止损后暂停一天
            consec = getattr(self, '_consec_losses', 0)
            if consec >= 3:
                from datetime import datetime as _dt, timedelta
                last_trade = getattr(self, '_last_trade_time', None)
                if last_trade and (_dt.now() - last_trade).total_seconds() < 86400:
                    no_trade = True
                    no_trade_reason = f"连续{consec}次止损, 暂停至明日"
            # 规则4: 空仓+弱市+走弱=继续空
            if no_trade is False and hasattr(self, "account") and self.account:
                if not self.account.positions and self.market_score < 30:
                    try:
                        trend = getattr(self, '_market_trend', 0)
                        if trend < 0:
                            no_trade = True
                            no_trade_reason = f"空仓+弱市(market_score={self.market_score:.0f}<30)+走弱"
                    except:
                        pass
            # 规则5: 周预算触发warn级别后只允许≤1只
            budget_check = budget.check()
            if budget_check["triggered"] and budget_check["action"] in ("warn", "reduce_half"):
                pass  # budget模块已经处理, 这里不再重复
            if no_trade:
                self.log.warning(f"[NoTrade] {no_trade_reason}")
                self.plans = []
                self.alerts.append({"type": "no_trade", "reason": no_trade_reason})
                self.log.info(f"[Step4] 0 plans (no-trade)")
                return
            # 规则6: Agent熊市交易限制(P0修复)
            agent_style = getattr(self, 'agent_trading_style', {})
            bear_allow = agent_style.get("bear_allow_trade", True)
            bear_max = agent_style.get("bear_max_positions", 99)
            regime = getattr(self, 'market_regime', 'range')
            if "bear" in regime and not bear_allow:
                self.log.warning(f"[BearTrade] Agent禁止熊市交易")
                self.plans = []
                return
            if "bear" in regime and bear_max < 99:
                existing = len(getattr(self.account, 'positions', {}) or {}) if hasattr(self, 'account') else 0
                if self.plans:
                    # 熊市限制开仓数
                    self.plans = self.plans[:max(0, bear_max - existing)]
                    self.log.info(f"[BearTrade] 熊市持仓≤{bear_max}, 现有{existing}, 开{len(self.plans)}")
        except Exception as e:
            self.log.debug(f"[NoTrade] check: {e}")
        bt = get_backtest_engine()
        codes = [s.get("code", "") for s in (self.scores or [])[:5] if s.get("code")]
        if codes:
            wf = bt.walk_forward(codes, train_days=150, test_days=40, windows=2)
            for code, params in wf.items():
                self.log.info(f"[WF] {code}: kelly={params.get('kelly',0.08):.2f} wr={params.get('win_rate',0):.0%}")
        self.plans = plan_positions(self.scores, self.capital, self.cfg, bt)
        # [Opt] 时间窗口开仓规则 — regime自适应
        # bull_strong/bull_weak: 全天开仓(强势行情)
        # range: 盘中正常开仓
        # bear_weak/bear_strong: 仅尾盘14:30-14:55(T+1友好,减少隔夜风险)
        now_hour = datetime.now().hour
        now_min = datetime.now().minute
        time_min = now_hour * 60 + now_min
        regime = getattr(self, 'market_regime', 'range')
        if regime in ("bull_strong", "bull_weak"):
            # 强势行情: 仅上午10:00前过滤(开盘波动大), 之后全天开仓
            if time_min < 9 * 60 + 30:
                self.log.info(f"[TimeGate] {now_hour:02d}:{now_min:02d}, 盘前, 清除计划")
                self.plans = []
            elif time_min < 10 * 60:
                # 开盘30分钟: 仅保留评分≥75的强信号(过滤开盘杂波)
                before = len(self.plans)
                self.plans = [p for p in self.plans if p.get("score", 0) >= 75]
                if before > len(self.plans):
                    self.log.info(f"[TimeGate] {now_hour:02d}:{now_min:02d}, 开盘初期过滤{before-len(self.plans)}个弱信号")
                self.log.info(f"[TimeGate] {now_hour:02d}:{now_min:02d}, 强势行情全天开仓 ✓")
        elif regime == "range":
            # 震荡市: 10:00后开仓, 14:57后清理(保留集合竞价窗口)
            if time_min < 10 * 60:
                self.log.info(f"[TimeGate] {now_hour:02d}:{now_min:02d}, 震荡市10:00后开仓")
                self.plans = []
            elif time_min >= 14 * 60 + 57:
                self.log.info(f"[TimeGate] {now_hour:02d}:{now_min:02d}, 尾盘尾声, 清除计划")
                self.plans = []
            else:
                self.log.info(f"[TimeGate] {now_hour:02d}:{now_min:02d}, 震荡市开仓 ✓")
        else:  # bear_weak, bear_strong
            # 熊市: 仅尾盘14:30-14:57开仓
            TAIL_START = 14 * 60 + 30
            TAIL_END = 14 * 60 + 57
            if time_min < TAIL_START:
                self.log.info(f"[TimeGate] {now_hour:02d}:{now_min:02d}, 熊市仅尾盘14:30-14:57开仓")
                self.plans = []
            elif time_min >= TAIL_START and time_min < TAIL_END:
                self.log.info(f"[TimeGate] {now_hour:02d}:{now_min:02d}, 尾盘窗口开仓 ✓")
            else:
                self.log.info(f"[TimeGate] {now_hour:02d}:{now_min:02d}, 尾盘尾声, 清除计划")
                self.plans = []

        # [CloseGate] 收盘保护: ≥15:00不执行新开仓 (候选留档次日竞价执行)
        # 防止review阶段以收盘价买入, 消除次日跳空风险
        if self.plans and time_min >= 15 * 60:
            kept = len(self.plans)
            codes_kept = [p.get("code", "") for p in self.plans][:5]
            self.log.warning(f"[CloseGate] {now_hour:02d}:{now_min:02d}, 已收盘(≥15:00), "
                             f"清空{kept}个计划 → 次日竞价执行: {codes_kept}")
            self.plans = []

        # [Opt] 板块集中度上限40%: 单板块持仓不超过总仓位40%
        if self.plans:
            try:
                from data.sources import get_tencent_quotes
                plan_codes = [p.get("code","") for p in self.plans if p.get("code")]
                q = get_tencent_quotes(plan_codes) if plan_codes else {}
                sector_value = {}
                for p in self.plans:
                    c = p.get("code","")
                    ind = q.get(c,{}).get("name","").split("(")[0] if q.get(c,{}).get("name") else ""
                    # 股名取前3字符做板块归类简化版
                    sv = p.get("shares",0) * p.get("entry_price",0)
                    sector_key = ind[:4] if ind else "其他"
                    sector_value[sector_key] = sector_value.get(sector_key,0) + sv
                total_val = sum(sector_value.values())
                if total_val > 0:
                    cap40 = self.capital * 0.40
                    for sk, sv in sorted(sector_value.items(), key=lambda x: -x[1]):
                        if sv > cap40 and total_val > 0:
                            over = sv - cap40
                            scale = cap40 / sv if sv > 0 else 1.0
                            for p in self.plans:
                                c = p.get("code","")
                                pk = q.get(c,{}).get("name","")[:4] if q.get(c,{}).get("name") else "其他"
                                if pk == sk:
                                    p["shares"] = max(100, int(p["shares"] * scale / 100) * 100)
                            self.log.warning(f"[SectorCap] {sk}仓位{sv:,.0f}>{cap40:,.0f}, 缩放到{scale:.0%}")
            except Exception as e:
                self.log.debug(f"[SectorCap] skip: {e}")

        # [Soul] 仓位硬上限50%(黑天鹅防护)
        try:
            total_planned = sum(p.get("shares", 0) * p.get("entry_price", 0) for p in self.plans)
            if hasattr(self, "account") and self.account:
                for _p in self.account.positions.values():
                    total_planned += _p.get("shares", 0) * _p.get("current_price", _p.get("avg_cost", 0))
            cap = self.capital * 0.50
            if total_planned > cap and total_planned > 0:
                scale = cap / total_planned
                for p in self.plans:
                    p["shares"] = max(100, int(p["shares"] * scale / 100) * 100)
                self.log.warning(f"[Soul] 仓位硬上限50%: 缩放中")
        except Exception:
            pass

        # 去重: 已有持仓不再开同股
        existing = set()
        if hasattr(self, "account") and self.account:
            existing = set(self.account.positions.keys())
        if existing:
            before = len(self.plans)
            self.plans = [p for p in self.plans if p.get("code") not in existing]
            if before > len(self.plans):
                self.log.info(f"[Dedup] 过滤{before-len(self.plans)}只已有持仓")

        # 暂停股票过滤
        if self.paused_stocks:
            before = len(self.plans)
            self.plans = [p for p in self.plans if p.get("code") not in self.paused_stocks]
            if before > len(self.plans):
                self.log.warning(f"[Fuse] filtered {before-len(self.plans)} paused")

        # 交易间隔限制
        today = datetime.now().strftime("%Y-%m-%d")
        min_interval = 5 if self.market_score >= 50 else 10
        if self.last_trade_date:
            from datetime import timedelta
            last = datetime.strptime(self.last_trade_date, "%Y-%m-%d")
            if (datetime.now() - last).days < min_interval:
                self.log.info(f"[Fuse] throttle: {(datetime.now()-last).days}d < {min_interval}d")
                self.plans = []
                return
        if self.plans:
            self.last_trade_date = today
        self.log.info(f"[Step4] {len(self.plans)} plans (Kelly adapted)")

        # 加仓检查(只做盈利股)
        if hasattr(self, "account") and self.account:
            for code, pos in list(self.account.positions.items()):
                cur = pos.get("current_price", pos.get("avg_cost", 0))
                add = check_add_position(pos, cur)
                if add["should_add"]:
                    for p in self.plans:
                        if p.get("code") == code:
                            p["shares"] += add.get("shares", 0)
                            p["weight"] = round((p["shares"] * p["entry_price"]) / self.capital, 3)
                            self.log.info(f"  [Add] {code}: {add['reason']}")

    # ──────── step 7: risk control ────────
    def step_risk(self):
        if not self.plans:
            return
        self.plans, self.alerts = check_all(self.plans, cfg=self.cfg)
        try:
            for p in self.plans:
                code = p.get("code", "")
                entry = p.get("entry_price", 0)
                try:
                    kline = get_kline(code, 30)
                    from risk.atr_stop import get_risk_adjusted_stop, atr_take_profit, calc_atr
                    rp = get_regime_config(self.market_regime).get("risk", {})
                    atr_s = get_risk_adjusted_stop(entry, entry, kline, self.market_regime)
                    aft = calc_atr(kline)
                    if atr_s:
                        p["stop_loss"] = atr_s
                        p["stop_type"] = "atr"
                    else:
                        # 兜底止损收紧: 默认5% (原8%)
                        p["stop_loss"] = entry * (1 - rp.get("stop_loss_pct", 0.05))
                        p["stop_type"] = "fixed"
                    if aft:
                        tp = atr_take_profit(entry, entry, aft, self.market_regime)
                        if tp:
                            p["take_profit"] = tp["tp2"]
                            p["take_profit_levels"] = tp
                    else:
                        p["take_profit"] = entry * (1 + rp.get("take_profit_pct", 0.20))
                except:
                    rp = get_regime_config(self.market_regime).get("risk", {})
                    # 兜底止损收紧: 默认5% (原8%)
                    p["stop_loss"] = entry * (1 - rp.get("stop_loss_pct", 0.05))
                    p["take_profit"] = entry * (1 + rp.get("take_profit_pct", 0.20))
        except Exception:
            pass
        day_start = getattr(self, "_day_start_value", self.capital)
        current = getattr(self.account, "total_value", day_start)
        daily_loss = (current - day_start) / day_start if day_start > 0 else 0
        if daily_loss < -0.03:
            self.log.warning(f"[Fuse] daily loss {daily_loss*100:.1f}% > 3%")
            self.plans = []
            self.alerts.append({"type": "fuse_daily", "reason": f"loss{daily_loss*100:.0f}%"})
        # ── P0升级: 总风险预算检查 ──
        try:
            from risk.budget import RiskBudget
            budget = RiskBudget(self.cfg, self.capital)
            budget.record_pnl(daily_loss, current)
            budget_check = budget.check()
            if budget_check["triggered"]:
                action = budget_check["action"]
                reason = budget_check["reason"]
                self.log.warning(f"[Budget] {action}: {reason}")
                self.alerts.append({"type": f"budget_{action}", "reason": reason})
                if action == "close_all":
                    self.plans = []
                    # 同时清空所有持仓
                    if hasattr(self, "account") and self.account:
                        for c, p in list(self.account.positions.items()):
                            sh = p.get("shares", 0)
                            if sh >= 100:
                                self.account.sell(c, p.get("current_price", p.get("avg_cost", 0)),
                                                  sh, f"budget_close:{reason[:20]}")
                                self.log.warning(f"  [Budget EXEC] {c} 清仓: {reason}")
                        self.positions = dict(self.account.positions)
                elif action == "reduce_half":
                    if self.plans:
                        self.plans = self.plans[:max(1, len(self.plans)//2)]
                    # 持仓减半
                    if hasattr(self, "account") and self.account:
                        half_positions = list(self.account.positions.keys())
                        import random
                        random.shuffle(half_positions)
                        sell_codes = half_positions[:len(half_positions)//2]
                        for c in sell_codes:
                            p = self.account.positions.get(c)
                            if p:
                                sh = p.get("shares", 0)
                                if sh >= 100:
                                    self.account.sell(c, p.get("current_price", p.get("avg_cost", 0)),
                                                      sh, f"budget_reduce:{reason[:20]}")
                                    self.log.warning(f"  [Budget EXEC] {c} 减仓: {reason}")
                        self.positions = dict(self.account.positions)
                elif action == "warn":
                    pass  # 只记录告警, 不执行操作
                self.log.info(f"[Budget] {budget.get_summary()}")
        except Exception as e:
            self.log.debug(f"[Budget] check: {e}")
        before = len(self.plans)
        self.plans = [p for p in self.plans if check_liquidity(p.get("code", ""), p.get("entry_price", 0))]
        if before > len(self.plans):
            self.log.info(f"[Liq] filtered {before-len(self.plans)} low-liquidity")
        self.log.info(f"[Step5] {len(self.plans)} passed, {len(self.alerts)} alerts")

        # ── P1: 系统健康检查 ──
        try:
            from notify.alert_system import check_system_health
            health = check_system_health(self)
            if not health.get("healthy", True):
                self.log.warning(f"[Health] 系统异常: {health.get('issues', [])}")
                self.alerts.append({"type": "system_health", "issues": health.get("issues", [])})
            else:
                self.log.info(f"[Health] 管线健康 ✓ ({health.get('alert_level', 'INFO')})")
        except Exception as e:
            self.log.debug(f"[Health] check: {e}")

    # ──────── step 8: simulate execution ────────
    def step_simulate(self):
        if not getattr(self, "account", None):
            self.account = SimAccount(self.capital, self.cfg)
        acc = self.account
        # ── 每日PnL记录到预算(即使无交易) ──
        try:
            from risk.budget import RiskBudget
            day_start = getattr(self, "_day_start_value", self.capital)
            current = getattr(acc, "total_value", day_start)
            daily_pnl = (current - day_start) / day_start if day_start > 0 else 0
            budget = RiskBudget(self.cfg, self.capital)
            budget.record_pnl(daily_pnl, current)
        except Exception:
            pass
        if not self.plans:
            self.positions = dict(acc.positions)
            self.log.info(f"[Step6] 无新交易, 已有持仓: {len(self.positions)}只")
            return
        for p in self.plans:
            # ── 六问证据链: 买入决策上下文 ──
            now_hhmm = datetime.now().strftime("%H:%M")
            buy_ctx = {
                "regime": getattr(self, "market_regime", "?"),
                "signal": p.get("signal", p.get("mtf_decision", {}).get("action", "?")),
                "strategy": p.get("strategy", ""),
                "time_gate": f"{now_hhmm}@{getattr(self, 'phase', '?')}",
                "kelly": p.get("kelly", 0),
                "consensus": p.get("agent_consensus", 0),
                "phase": getattr(self, "phase", "?"),
                "score": p.get("score", 0),
            }
            acc.buy(p["code"], p["entry_price"], p["shares"],
                    p.get("strategy", ""), context=buy_ctx)
        self.positions = dict(acc.positions)
        for p in self.plans:
            record_trade_result(p.get("strategy", "?"), 0, True)
            bt = get_backtest_engine()
            bt.update_stats(p.get("strategy", "?"), 0, True)
        for p in self.plans:
            record_entry(p)
        wd = check_withdraw(acc.total_value, self.capital)
        if wd.get("should_withdraw"):
            self.log.warning(f"[Withdraw] {wd['reason']}")

        # 加减仓实盘执行
        for code, pos in list(acc.positions.items()):
            cur = pos.get("current_price", pos.get("avg_cost", 0))
            add = check_add_position(pos, cur)
            if add["should_add"]:
                add_shares = add.get("shares", 0)
                add_price = add.get("price", cur)
                if add_shares >= 100:
                    acc.buy(code, add_price, add_shares, f"pyramid_add")
                    self.log.info(f"  [Add执行] {code}: +{add_shares}")
            scale = check_scale_out(pos, cur)
            if scale.get("should_scale"):
                sell_shares = scale.get("shares", 0)
                sell_price = scale.get("price", cur)
                if sell_shares >= 100:
                    acc.sell(code, sell_price, sell_shares, f"scale_out")
                    self.log.info(f"  [Scale执行] {code}: -{sell_shares}")
        self.log.info(f"[Step6] {len(self.plans)} opened")
        # [Push] 交易执行推送
        try:
            from notify.pusher import push_trade_execution
            push_trade_execution(self)
        except Exception:
            pass

    # ──────── step 9: position monitoring ────────
    def step_monitor(self):
        alerts = watch_positions(self.positions, self.cfg)
        self.alerts.extend(alerts)
        # 突发事件检查
        idx_data = get_index_snapshot(["000001"])
        idx_chg = idx_data.get("000001", {}).get("change_pct", 0) if idx_data else 0
        market_status = {"index_change": idx_chg}
        kline_cache = {}
        for code in self.positions:
            df = get_kline(code, 30)
            if not getattr(df, 'empty', True):
                kline_cache[code] = df
        contingency_alerts = check_contingency(self.positions, market_status, kline_cache)
        if contingency_alerts:
            self.alerts.extend(contingency_alerts)
            for ca in contingency_alerts:
                self.log.warning(f"  [ALERT] {ca['type']}: {ca['reason']}")
        # MTF多周期分析
        for pc in list(self.positions.keys()):
            try:
                r = analyze_stock(pc, has_position=True)
                act = r.get("decision", {}).get("action", "wait")
                desc = r.get("decision", {}).get("desc", "")
                if act in ("close_long", "reduce"):
                    self.log.warning(f"  [MTF SELL] {pc}: {desc}")
                    px = r.get("decision", {}).get("price", 0)
                    self.alerts.append({"type": "mtf", "code": pc, "desc": desc, "action": act, "price": px})
            except Exception as e:
                self.log.debug(f"  [MTF] {pc}: {e}")
        # [Opt] 自动执行卖出(告警触发) — 带持仓天数保护 + 保本止损失
        acc = getattr(self, "account", None)
        if acc:
            from datetime import datetime as _dt, timedelta
            min_hold_days = getattr(self, 'cfg', {}).get('risk', {}).get('min_hold_days', 3)
        for a in self.alerts:
            a_type = a.get("type", "")
            code = a.get("code", "")
            price = a.get("price", 0)
            shares = a.get("shares", 0)
            # [Opt] 持仓天数保护: 按agent_style差异化
            if acc and code in acc.positions and a_type not in ("stop_loss", "breach_stop"):
                try:
                    ed = acc.positions[code].get("entry_date", "")
                    if ed:
                        from datetime import datetime as _dt
                        ed_d = _dt.strptime(ed[:10], "%Y-%m-%d").date()
                        held = (_dt.now().date() - ed_d).days
                        # 按agent风格差异化: max_hold_days/3为最短持有天数
                        agent_style = getattr(self, 'agent_trading_style', {})
                        amhd = agent_style.get("max_hold_days", 10)
                        min_hold = max(0, min(amhd // 3, min_hold_days))
                        if held < min_hold:
                            self.log.info(f"  [HoldProtect] {code}: 仅持{held}天<{min_hold}, 跳过卖出({a_type})")
                            continue
                except:
                    pass
        acc = getattr(self, "account", None)
        for a in self.alerts:
            a_type = a.get("type", "")
            code = a.get("code", "")
            price = a.get("price", 0)
            shares = a.get("shares", 0)
            if a_type == "breach_stop" and acc and code in acc.positions:
                acc.sell(code, price, acc.positions[code]["shares"], f"trailing_stop@{price:.2f}")
            elif a_type == "stop_loss" and acc and code in acc.positions:
                acc.sell(code, price, acc.positions[code]["shares"], f"stop_loss@{price:.2f}")
            elif a_type == "take_profit" and acc and code in acc.positions:
                acc.sell(code, price, acc.positions[code]["shares"], f"take_profit@{price:.2f}")
            elif a_type == "scale_out" and shares > 0 and acc and code in acc.positions:
                acc.sell(code, price, shares, f"scale_out@{price:.2f}")
            elif a_type == "trailing_stop" and acc and code in acc.positions:
                acc.sell(code, price, acc.positions[code]["shares"], f"trailing@{price:.2f}")
            elif a_type == "mtf" and acc and code in acc.positions:
                action = a.get("action", "close_long")
                desc = a.get("desc", "")
                if action == "close_long":
                    acc.sell(code, price or acc.positions[code].get("current_price", 0),
                             acc.positions[code]["shares"], f"mtf_close:{desc[:30]}")
                    self.log.warning(f"  [MTF EXEC] {code} 全仓卖出: {desc}")
                elif action == "reduce":
                    total_shares = acc.positions[code]["shares"]
                    if total_shares <= 200:
                        # P0: 幽灵持仓修复 — ≤200股直接全卖，避免减半仓永远清不掉
                        acc.sell(code, price or acc.positions[code].get("current_price", 0),
                                 total_shares, f"mtf_close_ghost:{desc[:25]}")
                        self.log.warning(f"  [MTF EXEC] {code} 幽灵持仓全卖{total_shares}股: {desc}")
                    else:
                        half = max(100, total_shares // 2)
                        acc.sell(code, price or acc.positions[code].get("current_price", 0),
                                 half, f"mtf_reduce:{desc[:30]}")
                        self.log.warning(f"  [MTF EXEC] {code} 减半仓: {desc}")
            # ATR移动止盈检查
            try:
                from risk.atr_stop import check_moving_tp, calc_atr
                tn = getattr(self, "_atr_tp", {})
                for c, pos in (self.positions if hasattr(self, "positions") else {}).items():
                    if c in tn:
                        continue
                    ep = pos.get("avg_cost", 0)
                    cp = pos.get("current_price", ep)
                    hp = tn.get(c + "_high", cp)
                    if cp > hp:
                        tn[c + "_high"] = cp
                    k = get_kline(c, 30)
                    res = check_moving_tp(ep, tn.get(c + "_high", cp), cp, k)
                    if res == "partial":
                        sh = pos.get("shares", 0)
                        half = max(100, sh // 2)
                        if acc and c in acc.positions and half >= 100:
                            acc.sell(c, cp, half, "atr_tp_partial")
                            self.log.info(f"  [ATR-TP] {c}: 减仓{half}股")
                            tn[c] = True
                    elif res == "full":
                        sh = pos.get("shares", 0)
                        if acc and c in acc.positions and sh >= 100:
                            acc.sell(c, cp, sh, "atr_tp_full")
                            self.log.info(f"  [ATR-TP] {c}: 全出{sh}股")
                            tn[c] = True
                self._atr_tp = tn
            except Exception as ez:
                self.log.debug(f"[ATR] tp: {ez}")
        if acc:
            self.positions = dict(acc.positions)
        # ── 瀑布止损(短线客专用) ──
        if acc and self.positions:
            try:
                agent_style = getattr(self, 'agent_trading_style', {})
                if agent_style.get('exit_style') == 'aggressive':
                    from strategies.fulltime_battle import waterfall_stop
                    from data.sources import get_tencent_quotes
                    for code, pos in list(self.positions.items()):
                        price = get_tencent_quotes([code]).get(code, {}).get('price', pos.get('current_price', 0))
                        if price <= 0:
                            continue
                        result = waterfall_stop(code, pos, price, None)
                        if result.get('action') in ('stop_loss', 'close'):
                            shares = pos.get('shares', 0)
                            if shares >= 100:
                                acc.sell(code, price, shares, f"waterfall_{result['action']}")
                                self.log.warning(f"  [Waterfall] {code}: {result['action']} (layer={result.get('layer')})")
                    self.positions = dict(acc.positions)
            except Exception as we:
                self.log.debug(f"[Waterfall] batch: {we}")
        # T+0日内做T
        if acc and self.positions:
            try:
                from risk.t0_trading import detect_t0_signal, execute_t0
                t0_quotes = get_tencent_quotes(list(self.positions.keys()))
                for code, pos in self.positions.items():
                    q = t0_quotes.get(code, {})
                    if not q.get("price", 0):
                        continue
                    signal = detect_t0_signal(code, q, pos)
                    if signal.get("signal"):
                        self.log.info(f"  [T+0] {code}: {signal['reason']} conf={signal.get('confidence',0)}%")
                        execute_t0(acc, code, signal)
                        self.log.info(f"  [T+0] {code}: 执行{signal['action']} {signal.get('shares',0)}股")
                self.positions = dict(acc.positions)
            except Exception as e:
                self.log.debug(f"  [T+0] batch: {e}")
        # [Push] 交易执行推送(含平仓/减仓)
        try:
            from notify.pusher import push_trade_execution
            push_trade_execution(self)
        except Exception:
            pass
        # ── P1升级: 趋势健康度检查 ──
        if acc and self.positions:
            try:
                from risk.trend_health import calc_trend_health, get_health_action
                agent_style = getattr(self, 'agent_trading_style', {})
                health_threshold = agent_style.get("trend_health_threshold", 40)
                for code, pos in list(self.positions.items()):
                    k = get_kline(code, 30)
                    health, dims = calc_trend_health(code, k, self.market_regime)
                    action_info = get_health_action(health, self.market_regime)
                    self.log.info(f"  [TrendHealth] {code}: 健康度={health} {action_info['reason']} ma={dims.get('ma','?')} macd={dims.get('macd','?')} vol={dims.get('volume','?')}")
                    # 低于Agent健康度阈值 → 执行减仓/清仓
                    if health < health_threshold:
                        shares = pos.get("shares", 0)
                        if shares < 100:
                            continue
                        act = action_info["action"]
                        if act in ("close", "reduce_half"):
                            sell_shares = shares if act == "close" else max(100, shares // 2)
                            acc.sell(code, pos.get("current_price", pos.get("avg_cost", 0)),
                                     sell_shares, f"trend_health_{act}:{action_info['reason']}")
                            self.log.warning(f"  [TrendHealth EXEC] {code}: {act} {sell_shares}股 (health={health})")
                        elif act == "reduce_third":
                            sell_shares = max(100, shares // 3)
                            acc.sell(code, pos.get("current_price", pos.get("avg_cost", 0)),
                                     sell_shares, f"trend_health_{act}:{action_info['reason']}")
                            self.log.info(f"  [TrendHealth EXEC] {code}: {act} {sell_shares}股 (health={health})")
                    # 健康度预警(60-79): 收紧止损(P0修复)
                    elif 60 <= health < 80:
                        try:
                            from risk.atr_stop import calc_atr
                            k = get_kline(code, 30)
                            atr = calc_atr(k)
                            if atr and atr > 0:
                                current_sl = pos.get("stop_loss", 0)
                                entry_px = pos.get("avg_cost", 0)
                                if current_sl > 0:
                                    # 止损收紧到当前价的ATR×1.5
                                    tight_stop = pos.get("current_price", entry_px) - atr * 1.5
                                    if tight_stop > current_sl:
                                        pos["stop_loss"] = tight_stop
                                        self.log.info(f"  [TrendHealth] {code}: 止损收紧至{tight_stop:.2f}(ATR×1.5)")
                        except Exception as atr_e:
                            self.log.debug(f"[TrendHealth] stop_adjust: {atr_e}")
                self.positions = dict(acc.positions)
            except Exception as ez:
                self.log.debug(f"[TrendHealth] batch: {ez}")
        # ── [合并] 板块排名检查(原step_rebalance逻辑, 减少一次全市场API调用) ──
        if self.positions:
            try:
                sectors_list = get_sector_ranking(50) or []
                sectors = {s["name"]: {"pct": s.get("change_pct", 0), "rank": i + 1}
                           for i, s in enumerate(sectors_list)}
                if sectors:
                    quotes = get_tencent_quotes(list(self.positions.keys()))
                    sell_list = []
                    for code, pos in self.positions.items():
                        shares = pos.get("shares", 0)
                        if shares <= 0:
                            continue
                        industry = pos.get("industry", "")
                        cur_price = quotes.get(code, {}).get("price", pos.get("current_price", pos.get("avg_cost", 0)))
                        if industry and industry in sectors:
                            rank = sectors[industry]["rank"]
                            if rank > 20:
                                sell_list.append({"code": code, "shares": shares, "price": cur_price, "reason": f"板块排{rank}>20清仓"})
                            elif rank > 10:
                                half = max(100, shares // 2)
                                sell_list.append({"code": code, "shares": half, "price": cur_price, "reason": f"板块排{rank}>10减半"})
                    regime_cfg = get_regime_config(self.market_regime)
                    max_pos = regime_cfg.get("max_positions", 5)
                    cur_pos = len(self.positions)
                    if cur_pos > max_pos:
                        extra = cur_pos - max_pos
                        ranked = []
                        for code in self.positions:
                            ind = self.positions[code].get("industry", "")
                            r = sectors.get(ind, {}).get("rank", 99)
                            ranked.append((r, code))
                        for _, code in sorted(ranked)[:extra]:
                            pos = self.positions[code]
                            shares = pos.get("shares", 0)
                            cur_price = quotes.get(code, {}).get("price", pos.get("current_price", 0))
                            if shares >= 100:
                                sell_list.append({"code": code, "shares": shares, "price": cur_price,
                                                  "reason": f"超持仓上限{max_pos}只"})
                    acc = getattr(self, "account", None)
                    if acc is None:
                        acc = SimAccount(self.capital)
                        self.account = acc
                    for s in sell_list:
                        result = acc.sell(s["code"], s["price"], s["shares"], s["reason"])
                        if result and result.get("success"):
                            self.alerts.append({"type": "rebalance", "code": s["code"], "msg": s["reason"]})
                            self.log.info(f"  [Sell] {s['code']} {s['shares']}")
                    if sell_list:
                        try:
                            from notify.pusher import push_trade_execution
                            push_trade_execution(self)
                        except Exception:
                            pass
            except Exception as ez:
                self.log.debug(f"[Rebalance] sector_check: {ez}")

    # ──────── step 10: rebalance (简化版 — 仅调用dispatch, 不做全市场板块扫描) ────────
    def step_rebalance(self):
        if not self.positions:
            return
        # [Soul] 自适应参数 (原step_rebalance保留的逻辑, 无需全市场API调用)
        try:
            acc = getattr(self, "account", None)
            if acc and hasattr(acc, "get_trades"):
                trades = acc.get_trades() if callable(getattr(acc, "get_trades")) else []
                if trades and len(trades) >= 5:
                    wins = [t for t in trades[-20:] if t.get("pnl_pct", 0) > 0]
                    wr = len(wins) / max(len(trades[-20:]), 1)
                    ap = AdaptiveParams()
                    ap.update_from_trades(trades[-50:], wr)
                    self.adaptive_params = ap.params
                    self.log.info(f"[Soul] style_adaptive: wr={wr:.0%}")
        except Exception as e:
            self.log.debug(f"[Soul] style_adaptive: {e}")

    # ──────── step 11: evaluate ────────
    def step_evaluate(self):
        bt = get_backtest_engine()
        self.log.info(f"[Step8]\n{bt.summary()}")
        health = get_all_health()
        dead = [n for n, h in health.items() if h.get("status") == "dead"]
        if dead:
            self.log.warning(f"[Evolve] Dead strategies: {dead}")
            from strategies.evolution import mark_strategy_inactive
            for n in dead:
                h = health.get(n, {})
                mark_strategy_inactive(n, reason=f"WR={h.get('win_rate',0):.0%} composite={h.get('composite',0)}")
        # [Soul] 贝叶斯信念更新
        try:
            if hasattr(self, "analysis") and self.analysis:
                for a in self.analysis:
                    strat = a.get("best_strategy", "")
                    if strat and a.get("signal"):
                        outcome = a.get("best_score", 0) >= 60 or a.get("confidence", 0) >= 0.6
                        update_belief(strat, outcome)
        except Exception:
            pass
        # [Soul] ML因子IC校准
        try:
            from strategies.scoring import calibrate_ml_weights
            if hasattr(self, "analysis") and self.analysis:
                history = [{"score": a.get("best_score", 50), "future_return": 0, "factors": {}}
                           for a in self.analysis if a.get("signal")]
                if len(history) >= 5:
                    adj = calibrate_ml_weights(history)
        except Exception:
            pass
        # ── P1升级: 卖飞检测 ──
        try:
            acc = getattr(self, "account", None)
            if acc and hasattr(acc, "get_trades"):
                trades = acc.get_trades() if callable(getattr(acc, "get_trades")) else []
                recent_sells = [t for t in trades[-50:] if t.get("action") == "sell"
                                and t.get("code") and t.get("time", "").startswith(datetime.now().strftime("%Y-%m-%d")[:10])
                                and (datetime.now() - datetime.strptime(t["time"][:10], "%Y-%m-%d")).days <= 5]
                # 更准确: 用K线检查卖出后5天走势
                sold_well = 0
                sold_wrong = 0
                for t in recent_sells[-10:]:
                    code = t.get("code", "")
                    sell_price = t.get("price", 0)
                    sell_date = t.get("time", "")[:10]
                    if not code or not sell_price:
                        continue
                    k = get_kline(code, 30)
                    if k is None or getattr(k, 'empty', True):
                        continue
                    closes = k["close"].values
                    if len(closes) < 5:
                        continue
                    # 找卖出日后第5个交易日的收盘价
                    future_high = max(closes[-5:])
                    future_5d = closes[-1] if len(closes) >= 1 else 0
                    if future_5d > sell_price * 1.05:
                        sold_wrong += 1  # 卖飞: 卖出后涨超5%
                        self.log.info(f"  [SellOff] 卖飞 {code}: 卖@{sell_price:.2f} 后高点{future_high:.2f}")
                    elif future_5d < sell_price * 0.97:
                        sold_well += 1   # 卖对: 卖出后跌超3%
                        self.log.debug(f"  [SellOff] 卖对 {code}: 卖@{sell_price:.2f} 后{future_5d:.2f}")
                total_checked = sold_well + sold_wrong
                if total_checked >= 3:
                    sell_off_ratio = sold_wrong / total_checked
                    self.log.warning(f"[SellOff] 最近{total_checked}笔: 卖飞{sold_wrong}/{sold_well}卖对, 卖飞率{sell_off_ratio:.0%}")
                    if sell_off_ratio > 0.6:
                        self.log.warning(f"[SellOff] 卖飞率>60%, 建议审视退出条件")
        except Exception as e:
            self.log.debug(f"[SellOff] analyze: {e}")
        # 每周五自进化
        if datetime.now().weekday() == 4:
            from weekly_evolution import clear_suspensions, run_weekly_evolution
            clear_suspensions()
            report = run_weekly_evolution()
            self.log.info(f"[Evolution] {report}")
        # 每月1日自动调参
        try:
            from strategies.auto_tune import run_monthly_tune
            if datetime.now().day == 1:
                adj = run_monthly_tune(self)
                if adj:
                    self.log.info(f"[AutoTune] {len(adj)}因子调整")
        except Exception:
            pass
        # 每月1日生成月报
        try:
            if datetime.now().day == 1:
                from notify.monthly_report import save_monthly_report
                save_monthly_report()
                self.log.info("[Monthly] 月报已生成")
        except Exception:
            pass
        # [Soul] 交易反思
        try:
            acc = getattr(self, "account", None)
            if acc and hasattr(acc, "get_trades"):
                trades = acc.get_trades() if callable(getattr(acc, "get_trades")) else []
                if trades:
                    reflector = TradeReflector()
                    reflections = [reflector.analyze(t) for t in trades[-20:]]
                    weekly = reflector.weekly_summary(trades[-50:])
                    self.trade_reflections = reflections
                    self.log.info(f"[Soul] trade_reflector: {len(reflections)}笔反思完成")
                    self.log.info(f"[Soul] {weekly}")
        except Exception as e:
            self.log.warning(f"[Soul] trade_reflector: {e}")

        # ── P1: 策略滚动胜率更新 ──
        try:
            from strategies.rolling_stats import update_rolling_stats
            acc = getattr(self, "account", None)
            if acc and hasattr(acc, "get_trades"):
                trades = acc.get_trades() if callable(getattr(acc, "get_trades")) else []
                recent = [t for t in trades[-20:] if t.get("pnl_pct") is not None and t.get("strategy")]
                for t in recent:
                    update_rolling_stats(t["strategy"], t["pnl_pct"])
                if recent:
                    self.log.info(f"[RollingStats] 已更新{len(recent)}笔交易胜率")
        except Exception as e:
            self.log.debug(f"[RollingStats] update: {e}")

    # ──────── step 12: review ────────
    def step_review(self):
        diag = diagnose()
        if diag.get("issues"):
            self.log.warning(f"[Step9] Bias: {'; '.join(diag['issues'])}")
        self.log.info(f"[Step9] {len(self.plans)} trades, {len(self.alerts)} alerts, bias={diag.get('status','?')}")

        # ── P1: 候选股追踪记录 ──
        try:
            from data.candidate_tracker import record_candidates
            record_candidates(self)
        except Exception as e:
            self.log.debug(f"[CandidateTracker] record: {e}")

    def step_prep(self):
        self.log.info("[Step9.5] Watchlist generated")

    def _push_summary(self):
        if not self.plans and not self.alerts and self.market_score < 60:
            return
        token = self.cfg.get("notify", {}).get("sct_token", "")
        if not token:
            return
        try:
            import requests
            token = _os.environ.get("SCT_TOKEN", token)
            if not token or len(token) < 10:
                return
            health = get_all_health()
            health_str = "\n".join(f"  {n}: {h['status']} wr={h.get('win_rate','?')}"
                                   for n, h in list(health.items())[:5] if h.get("trades", 0) > 0)
            desc = f"Score:{self.market_score:.0f}"
            if self.plans: desc += f"\nPlans:{len(self.plans)}"
            if self.alerts: desc += f"\nAlerts:{len(self.alerts)}"
            desc += f"\n\nStrategies:\n{health_str}"
            requests.post(f"https://sctapi.ftqq.com/{token}.send",
                          json={"title": f"Aurora {self.market_regime} {datetime.now():%m-%d %H:%M}",
                                "desp": desc}, timeout=10)
        except Exception:
            pass

    # ── P2升级: 日终批量处理(15:30收盘后) ──
    def step_close(self):
        """收盘后批量处理: 更新持仓收盘价 + 生成市场快照 + 预热次日候选"""
        try:
            if not is_trading_day():
                self.log.info("[Close] 非交易日, 跳过")
                return
            now_hour = datetime.now().hour
            if now_hour < 15:
                self.log.info("[Close] 未收盘, 跳过")
                return
            self.log.info("[Close] ===== 日终批量处理开始 =====")
        except:
            pass
        
        # 1. 更新所有持仓收盘价 + 趋势健康度
        try:
            acc = getattr(self, "account", None)
            if acc and self.positions:
                quotes = get_tencent_quotes(list(self.positions.keys()))
                for code, pos in list(self.positions.items()):
                    q = quotes.get(code, {})
                    if q.get("price"):
                        pos["current_price"] = q["price"]
                    # 收盘后重新计算趋势健康度
                    k = get_kline(code, 30)
                    if k is not None and not getattr(k, 'empty', True):
                        from risk.trend_health import calc_trend_health
                        health, dims = calc_trend_health(code, k, self.market_regime)
                        self.log.info(f"  [Close] {code} 收盘健康度={health}")
                if hasattr(acc, '_save'):
                    acc._save()
                self.positions = dict(acc.positions)
                self.log.info(f"[Close] 已更新{len(self.positions)}只持仓收盘价")
        except Exception as e:
            self.log.debug(f"[Close] 更新持仓: {e}")
        
        # 2. 生成市场快照(情绪面板)
        try:
            snapshot = self._gen_market_snapshot()
            snapshot_path = Path(__file__).resolve().parent.parent / "data" / "market_snapshot.json"
            snapshot_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))
            self.log.info(f"[Close] 市场快照已保存: {snapshot_path.name}")
        except Exception as e:
            self.log.debug(f"[Close] 快照: {e}")
        
        # 3. 预热次日候选(离线缓存)
        try:
            from screening.cascade import cascade_screen
            old_phase = getattr(self, 'phase', 'monitor')
            self.phase = 'morning'
            warmup = cascade_screen(self.cfg, phase='morning')
            self.phase = old_phase
            if warmup:
                self.log.info(f"[Close] 预热次日候选: {len(warmup)}只")
                # 保存前50只到缓存文件
                cache_path = Path(__file__).resolve().parent.parent / "data" / "warmup_cache.json"
                cache_path.write_text(json.dumps([
                    {"code": c.get("code"), "name": c.get("name", ""), "score": c.get("sector_heat", 0)}
                    for c in warmup[:50]
                ], indent=2, ensure_ascii=False))
            else:
                self.log.info("[Close] 预热候选为空")
        except Exception as e:
            self.log.debug(f"[Close] 预热: {e}")
        
        # 4. 保存PnL到预算
        try:
            from risk.budget import RiskBudget
            budget = RiskBudget(self.cfg, self.capital)
            day_start = getattr(self, "_day_start_value", self.capital)
            current = getattr(self.account, "total_value", day_start) if hasattr(self, "account") else day_start
            daily_pnl = (current - day_start) / day_start if day_start > 0 else 0
            budget.record_pnl(daily_pnl, current)
            self.log.info(f"[Close] PnL入账: {daily_pnl*100:+.2f}%")
        except Exception as e:
            self.log.debug(f"[Close] PnL: {e}")
        
        self.log.info("[Close] ===== 日终批量处理完成 =====")

    def _gen_market_snapshot(self) -> dict:
        """生成市场快照(情绪面板数据)"""
        snapshot = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "time": datetime.now().strftime("%H:%M"),
            "market_score": getattr(self, "market_score", 50),
            "regime": getattr(self, "market_regime", "range"),
            "sentiment": getattr(self, "sentiment_score", 50),
            "positions": {},
            "indices": {},
            "sectors": [],
        }
        # 持仓
        for code, pos in (getattr(self, "positions", {}) or {}).items():
            snapshot["positions"][code] = {
                "shares": pos.get("shares", 0),
                "cost": round(pos.get("avg_cost", 0), 2),
                "price": round(pos.get("current_price", 0), 2),
                "pnl_pct": round((pos.get("current_price", 0) / max(pos.get("avg_cost", 1), 0.01) - 1) * 100, 2),
            }
        # 主要指数
        try:
            idx = get_index_snapshot(["000001", "399001", "399006", "000300", "000688"])
            if idx:
                for k, v in idx.items():
                    snapshot["indices"][{"000001": "上证", "399001": "深证", "399006": "创业板", "000300": "沪深300", "000688": "科创50"}.get(k, k)] = {
                        "price": v.get("price", 0), "chg_pct": v.get("change_pct", 0)
                    }
        except: pass
        # 板块TOP5
        try:
            sectors = get_sector_ranking(5) or []
            snapshot["sectors"] = [{"name": s.get("name"), "chg_pct": s.get("change_pct", 0)} for s in sectors]
        except: pass
        return snapshot

    def run(self):
        if not is_trading_day():
            self.log.info("非交易日,跳过")
            return
        if not is_market_open():
            self.log.info("非交易时段,跳过")
            return
        t0 = time.time()
        acct = getattr(self, "account", None)
        self._day_start_value = acct.total_value if acct is not None else self.capital
        steps = [
            # P0修复: 市场体检先于选股, 让cascade知道当前regime
            ("step_market", "市场体检"), ("step_cascade", "选股"), ("step_screen", "CAN SLIM"),
            ("step_analyze", "信号分析"),
            ("step_score", "综合评分"), ("step_position", "仓位计划"),
            ("step_risk", "风控"), ("step_simulate", "模拟交易"),
            ("step_monitor", "实时监控"), ("step_rebalance", "动态调仓"),
            ("step_evaluate", "评估进化"), ("step_review", "复盘"),
        ]
        for step_name, label in steps:
            self.pipeline_validator.validate_before(step_name)
            try:
                fn = getattr(self, step_name, None)
                if fn: fn()
                self.log.info(f"  {label} OK")
            except Exception as e:
                self.log.error(f"  {label} FAIL: {e}")
            self.pipeline_validator.validate_after(step_name)
        self.log.info(f"Done in {time.time()-t0:.1f}s")
        report = self.pipeline_validator.report()
        if report["summary"]["total_errors"] > 0 or report["summary"]["total_warnings"] > 0:
            self.log.warning(self.pipeline_validator.summary_str())
        self._push_summary()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    AuroraEngine().run()


if __name__ == "__main__":
    main()
