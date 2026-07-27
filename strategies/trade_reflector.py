"""交易反思引擎 — 每笔交易后自动分析得失
   像一个老交易员盘后复盘:"这笔为什么赚/为什么亏?"
"""
import json, logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("aurora.reflect")

class TradeReflector:
    """交易反思器"""
    
    @staticmethod
    def analyze(trade: dict) -> dict:
        """分析一笔交易,生成反思"""
        action = trade.get("action", "")
        code = trade.get("code", "")
        strategy = trade.get("strategy", "")
        price = trade.get("price", 0)
        shares = trade.get("shares", 0)
        pnl_pct = trade.get("pnl_pct", 0)
        pnl = trade.get("pnl", 0)
        reason = trade.get("reason", "")
        
        reflection = {
            "code": code,
            "strategy": strategy,
            "pnl_pct": round(pnl_pct, 2),
            "lessons": [],
            "rating": "",
        }
        
        if action == "buy":
            # 买入反思
            if pnl and pnl > 0:
                reflection["lessons"].append(f"买入{code}后盈利,说明{strategy}策略在当前市场有效")
                reflection["rating"] = "正确买入"
            elif pnl and pnl < 0:
                reflection["lessons"].append(f"买入后亏损,检查买入时机是否过早或确认信号是否充分")
                reflection["rating"] = "需改进"
                if reason: reflection["lessons"].append(f"当时买入原因是:{reason},回头看这个逻辑是否仍然成立?")
        
        elif action == "sell":
            if pnl and pnl > 0:
                reflection["lessons"].append(f"盈利卖出,止盈纪律执行到位")
                if pnl_pct > 5:
                    reflection["lessons"].append(f"盈利{pnl_pct:.1f}%,卖得不错")
                elif pnl_pct < 2:
                    reflection["lessons"].append(f"盈利仅{pnl_pct:.1f}%,是否卖早了?可以放宽止盈")
                reflection["rating"] = "正确卖出"
            elif pnl and pnl < 0:
                reflection["lessons"].append(f"止损卖出,纪律执行")
                reflection["rating"] = "止损"
                if abs(pnl_pct) > 5:
                    reflection["lessons"].append(f"亏损{abs(pnl_pct):.1f}%,止损是否设得太宽了?")
                else:
                    reflection["lessons"].append(f"亏损控制在{abs(pnl_pct):.1f}%,小亏是好事")
        
        # 策略维度反思
        strat_reflections = {
            "momentum_breakout": "突破策略:确认突破是否有效?成交量是否配合?",
            "mean_reversion": "均值回归:判断是否真的超卖?市场趋势是否已改变?",
            "wave_point": "低吸策略:回调是否到位?支撑是否有效?",
            "morning_gap": "早盘突破:跳空是否放量?板块其他股是否同步?",
        }
        if strategy in strat_reflections:
            reflection["lessons"].append(strat_reflections[strategy])
        
        return reflection
    
    @staticmethod
    def weekly_summary(trades: list) -> str:
        """周度总结"""
        if not trades: return "本周无交易"
        wins = [t for t in trades if t.get("pnl_pct", 0) > 0]
        losses = [t for t in trades if t.get("pnl_pct", 0) < 0]
        
        lines = []
        lines.append(f"本周交易{len(trades)}笔")
        lines.append(f"盈利: {len(wins)}笔 亏损: {len(losses)}笔")
        if wins:
            avg_win = np.mean([t["pnl_pct"] for t in wins]) if wins else 0
            lines.append(f"平均盈利: {avg_win:.1f}%")
        if losses:
            avg_loss = np.mean([t["pnl_pct"] for t in losses]) if losses else 0
            lines.append(f"平均亏损: {abs(avg_loss):.1f}%")
        
        # 策略表现
        by_strategy = {}
        for t in trades:
            s = t.get("strategy", "unknown")
            if s not in by_strategy: by_strategy[s] = {"trades": 0, "wins": 0, "pnl": 0}
            by_strategy[s]["trades"] += 1
            by_strategy[s]["pnl"] += t.get("pnl_pct", 0)
            if t.get("pnl_pct", 0) > 0: by_strategy[s]["wins"] += 1
        
        lines.append("\n各策略表现:")
        for s, d in sorted(by_strategy.items(), key=lambda x: x[1]["pnl"], reverse=True):
            wr = d["wins"]/max(d["trades"],1)*100
            lines.append(f"  {s}: {d['trades']}笔 胜率{wr:.0f}% 总盈亏{d['pnl']:.1f}%")
        
        return "\n".join(lines)

import numpy as np
