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
        names = ["first_board","pullback","wave_point","test_line","naked_k","123_rule","ma_breakout"]
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

    def walk_forward(self, codes: list, train_days=200, test_days=50, windows=3) -> dict:
        ck = self._cache_key(codes, train_days, test_days, windows)
        if ck in self._wf_results and all(self._wf_results.get(c, {}).get("kelly") for c in codes):
            logger.info(f"[WF] cache hit for {codes[:3]}... ({len(codes)} stocks)")
            return {c: self._wf_results.get(c, self._wf_results.get(ck, {})) for c in codes}

        from data.sources import get_kline
        all_results = {}
        for code in codes[:5]:
            kline = get_kline(code, train_days + test_days * windows + 50)
            if kline.empty or len(kline) < train_days:
                all_results[code] = {"kelly": 0.08, "win_rate": 0.0, "best_strategy": None, "rr": 2.0}
                continue
            results = []
            for w in range(windows):
                start = w * test_days
                train_end = start + train_days
                test_end = min(train_end + test_days, len(kline))
                test_df = kline.iloc[train_end:test_end]
                if len(test_df) < 10: continue
                from strategies.runner import analyze_all
                dummy = [{"code": code, "name": code, "price": float(test_df["close"].iloc[-1])}]
                analysis = analyze_all(dummy, kline_override={code: test_df})
                results.extend(analysis)
            best_params = self._compute_best_params(code, results)
            self._wf_results[code] = best_params
            all_results[code] = best_params
        self._wf_results[ck] = {"cached": True, "codes": codes, "train_days": train_days}
        self._save_cache()
        return all_results

    def _compute_best_params(self, code: str, analysis_results: list) -> dict:
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
        p = max(0.01, win_rate)
        kelly = max(0.01, (p * rr - (1 - p)) / rr)
        kelly = min(kelly, 0.25)
        return {"kelly": round(kelly, 4), "win_rate": round(win_rate, 4),
                "best_strategy": best_strat, "rr": rr}

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
        if s.win_rate < 0.30 and s.trades >= 20:
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