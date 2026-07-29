"""回测引擎 — Walk-Forward + 每策略胜率 + 动态Kelly + 缓存"""
import logging, json, numpy as np
import pandas as pd
from dataclasses import dataclass, field
from pathlib import Path
logger = logging.getLogger("aurora.backtest")

CACHE_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_FILE = CACHE_DIR / "wf_cache.json"

@dataclass
class StrategyStats:
    name: str = ""
    trades: int = 0
    wins: int = 0
    win_rate: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    profit_factor: float = 0.0
    sharpe: float = 0.0
    max_dd: float = 0.0
    ic_mean: float = 0.0
    ic_ir: float = 0.0
    active: bool = True
    weight: float = 1.0

class BacktestEngine:
    def __init__(self):
        self.stats: dict[str, StrategyStats] = {}
        self._wf_results: dict[str, dict] = {}
        self._init_strategies()
        self._load_cache()

    def _init_strategies(self):
        names = ["first_board","pullback","wave_point","test_line","naked_k","123_rule","ma_breakout","mean_reversion","momentum_breakout","sector_rotation"]
        for n in names:
            self.stats[n] = StrategyStats(name=n)

    def _cache_key(self, codes: list, train_days: int, test_days: int, windows: int) -> str:
        return f"{'-'.join(sorted(codes))}_{train_days}_{test_days}_{windows}"

    def _load_cache(self):
        try:
            if CACHE_FILE.exists():
                self._wf_results = json.loads(CACHE_FILE.read_text())
                logger.info(f"[WF Cache] loaded {len(self._wf_results)} cached results")
        except Exception:
            self._wf_results = {}

    def _save_cache(self):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(self._wf_results, indent=2, ensure_ascii=False))
        logger.debug(f"[WF Cache] saved {len(self._wf_results)} results")

    def walk_forward(self, codes: list, train_days=200, test_days=50, windows=3, oos_days=30) -> dict:
        """Walk-Forward + OOS验证: 保留最后oos_days做样本外确认"""
        ck = self._cache_key(codes, train_days, test_days, windows)
        if ck in self._wf_results and all(self._wf_results.get(c, {}).get("kelly") for c in codes):
            logger.info(f"[WF] cache hit for {codes[:3]}... ({len(codes)} stocks)")
            return {c: self._wf_results.get(c, self._wf_results.get(ck, {})) for c in codes}

        from data.sources import get_kline
        all_results = {}
        for code in codes[:5]:
            total_needed = train_days + test_days * windows + oos_days + 50
            kline = get_kline(code, total_needed)
            if kline.empty or len(kline) < train_days:
                all_results[code] = {"kelly": 0.08, "win_rate": 0.0, "best_strategy": None, "rr": 2.0}
                continue

            # 保留OOS段: 最后oos_days作为样本外验证
            oos_start = len(kline) - oos_days
            oos_df = kline.iloc[oos_start:] if oos_days > 0 else None
            train_data = kline.iloc[:oos_start] if oos_days > 0 else kline

            # Walk-Forward在训练数据上滚动
            results = []
            for w in range(windows):
                start = w * test_days
                train_end = start + train_days
                test_end = min(train_end + test_days, len(train_data))
                test_df = train_data.iloc[train_end:test_end]
                if len(test_df) < 10: continue
                from strategies.runner import analyze_all
                dummy = [{"code": code, "name": code, "price": float(test_df["close"].iloc[-1])}]
                analysis = analyze_all(dummy, kline_override={code: test_df})
                results.extend(analysis)

            best_params = self._compute_best_params(code, results)
            best_params["oos_days"] = oos_days

            # OOS验证: 在样本外数据上运行
            if oos_df is not None and len(oos_df) >= 10:
                from strategies.runner import analyze_all
                oos_dummy = [{"code": code, "name": code, "price": float(oos_df["close"].iloc[-1])}]
                try:
                    oos_result = analyze_all(oos_dummy, kline_override={code: oos_df})
                    if oos_result and oos_result[0].get("signal"):
                        best_params["oos_signal"] = True
                        best_params["oos_score"] = oos_result[0].get("best_score", 0)
                        logger.info(f"[WF OOS] {code}: signal={True} score={oos_result[0].get('best_score', 0)}")
                    else:
                        best_params["oos_signal"] = False
                        best_params["oos_score"] = 0
                except Exception as e:
                    logger.warning(f"[WF OOS] {code} fail: {e}")
                    best_params["oos_error"] = str(e)

            self._wf_results[code] = best_params
            all_results[code] = best_params

        self._wf_results[ck] = {"cached": True, "codes": codes, "train_days": train_days}
        self._save_cache()
        return all_results

    def _compute_best_params(self, code: str, analysis_results: list) -> dict:
        """基于PnL分布的Kelly计算 — 公式: f* = (avg_win*w_pct - avg_loss*(1-w_pct)) / (avg_win*w_pct)
        用模拟交易的PnL分布替代仅用胜率，更准确反映盈亏比结构"""
        rr = 2.0
        if not analysis_results:
            return {"kelly": 0.08, "win_rate": 0.0, "best_strategy": None, "rr": rr}
        strategy_counts = {}
        for r in analysis_results:
            strat = r.get("best_strategy")
            if strat:
                strategy_counts[strat] = strategy_counts.get(strat, 0) + 1
        if not strategy_counts:
            return {"kelly": 0.08, "win_rate": 0.0, "best_strategy": None, "rr": rr}
        total = len(analysis_results)
        best_strat = max(strategy_counts, key=strategy_counts.get)
        win_rate = strategy_counts[best_strat] / max(total, 1)

        # 真实PnL: 用K线收盘价计算买入持有收益率
        strat_results = [r for r in analysis_results if r.get("best_strategy") == best_strat]
        pnls = []
        for r in strat_results:
            sig = bool(r.get("signal", False))
            if sig:
                kline_df = r.get("kline_df")
                if kline_df is not None and hasattr(kline_df, 'close') and hasattr(kline_df, 'open'):
                    try:
                        close_vals = kline_df["close"].values
                        # 用测试窗口内的价格变化计算真实收益率
                        entry = float(close_vals[0])
                        exit_p = float(close_vals[-1])
                        if entry > 0:
                            pnl = (exit_p - entry) / entry
                        else:
                            pnl = -0.02
                    except (IndexError, ValueError, TypeError):
                        pnl = -0.02
                else:
                    pnl = -0.02
            else:
                pnl = -0.02
            pnls.append(pnl)

        if pnls:
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p <= 0]
            avg_win = np.mean(wins) if wins else 0.02
            avg_loss = abs(np.mean(losses)) if losses else 0.02
            w_pct = max(0.01, len(wins) / max(len(pnls), 1))
            # 原始Kelly: f* = (avg_win * w_pct - avg_loss * (1-w_pct)) / (avg_win * w_pct)
            denom = avg_win * w_pct
            if denom > 0:
                kelly = max(0.01, (avg_win * w_pct - avg_loss * (1 - w_pct)) / denom)
            else:
                kelly = 0.08
            kelly = min(kelly, 0.25)
        else:
            kelly = 0.08

        return {"kelly": round(kelly, 4), "win_rate": round(win_rate, 4),
                "best_strategy": best_strat, "rr": rr, "simulated_pnls": len(pnls)}

    def get_best_params(self, code: str) -> dict:
        return self._wf_results.get(code, {"kelly": 0.08, "win_rate": 0.0,
                                            "best_strategy": None, "rr": 2.0})

    def update_stats(self, strategy_name: str, pnl_pct: float, is_win: bool):
        s = self.stats.get(strategy_name)
        if not s: return
        s.trades += 1
        if is_win:
            s.wins += 1
            s.avg_win_pct = (s.avg_win_pct * (s.wins - 1) + pnl_pct) / s.wins
        else:
            s.avg_loss_pct = (s.avg_loss_pct * (s.trades - s.wins - 1) + abs(pnl_pct)) / (s.trades - s.wins) if s.trades > s.wins else abs(pnl_pct)
        s.win_rate = s.wins / max(s.trades, 1)
        if s.win_rate < 0.35: s.weight = 0.2
        elif s.win_rate < 0.40: s.weight = 0.5
        else: s.weight = 1.0
        if (s.win_rate < 0.30 and s.trades >= 10) or (s.win_rate < 0.20 and s.trades >= 6):
            s.active = False

    def get_kelly_weight(self, strategy_name: str, rr: float = 2.0) -> float:
        s = self.stats.get(strategy_name)
        if not s or not s.active or s.trades < 5:
            return 0.05
        p = max(0.01, s.win_rate)
        kelly = max(0.01, (p * rr - (1 - p)) / rr)
        return min(kelly * s.weight, 0.25)

    def get_active_strategies(self) -> list:
        return [n for n, s in self.stats.items() if s.active]

    def summary(self) -> str:
        lines = ["=== 策略统计 ==="]
        for s in sorted(self.stats.values(), key=lambda x: x.win_rate, reverse=True):
            status = "\u2705" if s.active else "\u274c"
            lines.append(f"  {status} {s.name:<15} trades={s.trades:>3} win={s.win_rate:.0%} pf={s.profit_factor:.1f} w={s.weight:.1f}")
        return "\n".join(lines)

_engine = None
def get_backtest_engine() -> BacktestEngine:
    global _engine
    if _engine is None:
        _engine = BacktestEngine()
    return _engine