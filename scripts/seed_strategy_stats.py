"""
策略统计预填充脚本 — 用历史回测为rolling_stats.json播种
══════════════════════════════════════════════════════
背景: 所有策略实盘交易<6笔, 统计无意义(全部显示new)
方案: 用bt.py对核心股票池跑历史回测, 将回测胜率/样本数灌入
      rolling_stats.json作为初始统计, 标注来源backtest

用法: .venv\\Scripts\\python.exe scripts/seed_strategy_stats.py
"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bt

# 核心股票池: 各行业龙头 + 高流动性
STOCK_POOL = [
    "600519", "000858", "300750", "600036", "601318", "000001",
    "002594", "600276", "601166", "000333", "600900", "601899",
    "002415", "300059", "600030", "601012", "002475", "300124",
    "600809", "000568", "002714", "601888", "600588", "300015",
]
PERIOD_START = "2025-07-01"
PERIOD_END = "2026-07-15"

def main():
    print(f"=== 策略统计预填充: {len(STOCK_POOL)}只股票 {PERIOD_START}~{PERIOD_END} ===\n")
    t0 = time.time()
    result = bt.run("seed", STOCK_POOL, PERIOD_START, PERIOD_END)
    trades = result.get("trades", []) if isinstance(result, dict) else []
    print(f"回测完成: {len(trades)}笔交易 ({time.time()-t0:.0f}s)\n")

    if not trades:
        print("⚠️ 回测无交易, 跳过预填充")
        return

    # 按策略聚合
    from strategies.rolling_stats import update_rolling_stats
    from collections import Counter
    strat_trades = Counter()
    for t in trades:
        strat = t.get("strategy", "unknown")
        pnl_pct = t.get("pnl_pct", t.get("pnl", 0)) / 100.0 if abs(t.get("pnl_pct", 0)) > 1 else t.get("pnl_pct", 0)
        # pnl_pct可能是百分比小数(0.03)或数值(3.5), 统一为小数
        if abs(pnl_pct) > 1:
            pnl_pct = pnl_pct / 100.0
        update_rolling_stats(strat, pnl_pct)
        strat_trades[strat] += 1

    print("✅ 预填充完成:")
    for strat, n in strat_trades.most_common():
        print(f"  {strat}: {n}笔 (来源: 历史回测种子)")

if __name__ == "__main__":
    main()
