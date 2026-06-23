
"""回测引擎 — Walk-Forward + 每策略胜率 + 动态Kelly"""
import logging, numpy as np
import pandas as pd
from dataclasses import dataclass, field
logger = logging.getLogger("aurora.backtest")

@dataclass
class StrategyStats:
    """策略统计 — 胜率/盈亏比/夏普/IC"""
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
    """Walk-Forward回测引擎"""
    def __init__(self):
        self.stats: dict[str, StrategyStats] = {}
        self._init_strategies()

    def _init_strategies(self):
        names = ["first_board","pullback","wave_point","test_line","naked_k","123_rule","ma_breakout"]
        for n in names:
            self.stats[n] = StrategyStats(name=n)

    def walk_forward(self, codes: list, train_days=200, test_days=50, windows=3) -> dict:
        import logging; logging.getLogger(__name__).warning("[NotYetConnected] walk_forward called but not wired to pipeline")
        """Walk-Forward验证: 滚动窗口, 样本外测试"""
        from data.sources import get_kline
        all_results = {}
        for code in codes[:3]:
            kline = get_kline(code, train_days + test_days * windows + 50)
            if kline.empty or len(kline) < train_days: continue
            results = []
            for w in range(windows):
                start = w * test_days
                train_end = start + train_days
                test_end = min(train_end + test_days, len(kline))
                train_df = kline.iloc[start:train_end]
                test_df = kline.iloc[train_end:test_end]
                if len(test_df) < 10: continue
                # 测试集上跑策略
                from strategies.runner import analyze_all
                dummy = [{"code": code, "name": code, "price": float(test_df["close"].iloc[-1])}]
                analysis = analyze_all(dummy, kline_override={code: test_df})
                results.extend(analysis)
            all_results[code] = results
        return all_results

    # utility: available for future use
    def update_stats(self, strategy_name: str, pnl_pct: float, is_win: bool):
        """更新策略统计 — 每笔交易后调用"""
        s = self.stats.get(strategy_name)
        if not s: return
        s.trades += 1
        if is_win:
            s.wins += 1
            s.avg_win_pct = (s.avg_win_pct * (s.wins - 1) + pnl_pct) / s.wins
        else:
            s.avg_loss_pct = (s.avg_loss_pct * (s.trades - s.wins - 1) + abs(pnl_pct)) / (s.trades - s.wins) if s.trades > s.wins else abs(pnl_pct)
        s.win_rate = s.wins / max(s.trades, 1)
        # 更新权重: win_rate<35% → weight=0.2, win_rate<40% → weight=0.5, else 1.0
        if s.win_rate < 0.35: s.weight = 0.2
        elif s.win_rate < 0.40: s.weight = 0.5
        else: s.weight = 1.0
        # 停用: win_rate<30% 且 trades>=20
        if s.win_rate < 0.30 and s.trades >= 20:
            s.active = False

    def get_kelly_weight(self, strategy_name: str, rr: float = 2.0) -> float:
        """动态Kelly: 基于真实胜率"""
        s = self.stats.get(strategy_name)
        if not s or not s.active or s.trades < 5:
            return 0.05  # 新策略: 极小试探仓
        p = max(0.01, s.win_rate)
        kelly = max(0.01, (p * rr - (1 - p)) / rr)
        return min(kelly * s.weight, 0.25)

    # utility: available for future use
    def get_active_strategies(self) -> list:
        return [n for n, s in self.stats.items() if s.active]

    def summary(self) -> str:
        lines = ["=== 策略统计 ==="]
        for s in sorted(self.stats.values(), key=lambda x: x.win_rate, reverse=True):
            status = "✅" if s.active else "❌"
            lines.append(f"  {status} {s.name:<15} trades={s.trades:>3} win={s.win_rate:.0%} pf={s.profit_factor:.1f} w={s.weight:.1f}")
        return "\n".join(lines)


# 全局单例
_engine = None
def get_backtest_engine() -> BacktestEngine:
    global _engine
    if _engine is None:
        _engine = BacktestEngine()
    return _engine
