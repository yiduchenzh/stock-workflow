"""
交易月报 — P3升级
=================
每月1日自动生成: 6Agent月度收益率排名 + 策略胜率汇总 + 盈亏归因

使用方式:
    from notify.monthly_report import generate_monthly_report
    report = generate_monthly_report()
    # → markdown格式报告
"""
import json, logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("aurora.monthly_report")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def generate_monthly_report() -> str:
    """生成月度交易报告(markdown)"""
    now = datetime.now()
    month_str = now.strftime("%Y年%m月")
    
    lines = []
    lines.append(f"# 📊 Aurora 月度交易报告 — {month_str}")
    lines.append(f"> 生成时间: {now.strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    
    # 1. 6Agent月度表现
    lines.append("---")
    lines.append("## 一、6Agent月度表现")
    lines.append("")
    lines.append("| 排名 | 交易员 | 总资产 | 收益额 | 收益率 | 持仓数 |")
    lines.append("|:---:|:------|:-----:|:-----:|:-----:|:-----:|")
    
    try:
        agent_file = DATA_DIR / "agent_comparison.json"
        if agent_file.exists():
            data = json.loads(agent_file.read_text())
            if isinstance(data, list) and data:
                latest = data[-1]
                agents = latest.get("agents", {})
                ranked = sorted(agents.items(), key=lambda x: -x[1].get("return_pct", 0))
                for i, (name, info) in enumerate(ranked, 1):
                    lines.append(f"| {i} | {name} | {info.get('total_value', 0):,.0f} | {info.get('pnl', 0):,.0f} | {info.get('return_pct', 0)*100:.2f}% | {info.get('positions', 0)} |")
                total_val = latest.get("total_capital", 0)
                total_pnl = sum(a.get("pnl", 0) for a in agents.values())
                lines.append(f"| - | **合计** | **{total_val:,.0f}** | **{total_pnl:,.0f}** | **{total_pnl/6_000_000*100:.2f}%** | - |")
        else:
            lines.append("| - | 无数据 | - | - | - | - |")
    except Exception as e:
        lines.append(f"| - | 数据加载失败: {e} | - | - | - | - |")
    
    # 2. 策略胜率统计
    lines.append("")
    lines.append("---")
    lines.append("## 二、策略胜率统计")
    lines.append("")
    lines.append("| 策略 | 交易数 | 胜率 | 状态 |")
    lines.append("|:-----|:-----:|:----:|:----:|")
    
    try:
        # 从behavior_journal读取策略胜率
        bj_file = DATA_DIR / "behavior_journal.json"
        if bj_file.exists():
            bj = json.loads(bj_file.read_text())
            strategy_stats = {}
            for entry in bj:
                strat = entry.get("strategy", "?")
                if strat not in strategy_stats:
                    strategy_stats[strat] = {"trades": 0, "wins": 0}
                strategy_stats[strat]["trades"] += 1
                if entry.get("pnl_pct", 0) > 0:
                    strategy_stats[strat]["wins"] += 1
            for strat, stats in sorted(strategy_stats.items(), key=lambda x: -x[1]["trades"]):
                wr = stats["wins"] / max(stats["trades"], 1) * 100
                status = "✅" if wr >= 50 else "⚠️" if wr >= 30 else "❌"
                lines.append(f"| {strat} | {stats['trades']} | {wr:.0f}% | {status} |")
    except Exception as e:
        lines.append(f"| - | 加载失败: {e} | - | - |")
    
    # 3. 月度盈亏汇总
    lines.append("")
    lines.append("---")
    lines.append("## 三、月度盈亏汇总")
    lines.append("")
    try:
        pnl_file = DATA_DIR / "pnl_tracker.json"
        if pnl_file.exists():
            pnl = json.loads(pnl_file.read_text())
            daily = pnl.get("daily", [])
            month_days = [d for d in daily if d.get("date", "").startswith(now.strftime("%Y-%m"))]
            if month_days:
                total_pnl = sum(d.get("pnl", 0) for d in month_days)
                total_cum = month_days[-1].get("cum", 0)
                win_days = sum(1 for d in month_days if d.get("pnl", 0) > 0)
                loss_days = sum(1 for d in month_days if d.get("pnl", 0) < 0)
                lines.append(f"- 交易天数: {len(month_days)}天")
                lines.append(f"- 盈利天数: {win_days}天 ({win_days/max(len(month_days),1)*100:.0f}%)")
                lines.append(f"- 亏损天数: {loss_days}天 ({loss_days/max(len(month_days),1)*100:.0f}%)")
                lines.append(f"- 月度盈亏: {total_pnl:+,.0f}元")
                lines.append(f"- 累计盈亏: {total_cum:+,.0f}元")
                lines.append(f"- 累计收益率: {total_cum/1_000_000*100:.2f}%")
                lines.append("")
                lines.append("| 日期 | 日盈亏 | 累计 | 持仓 |")
                lines.append("|:----:|:-----:|:----:|:----:|")
                for d in month_days[-20:]:  # 最近20天
                    lines.append(f"| {d['date'][-5:]} | {d.get('pnl',0):+,.0f} | {d.get('cum',0):+,.0f} | {d.get('positions',0)} |")
    except Exception as e:
        lines.append(f"- 加载失败: {e}")
    
    lines.append("")
    lines.append("---")
    lines.append(f"*报告自动生成于 {now.strftime('%Y-%m-%d %H:%M')}*")
    
    return "\n".join(lines)


def save_monthly_report():
    """保存月报到文件"""
    report = generate_monthly_report()
    report_path = DATA_DIR / "reports" / f"monthly_{datetime.now().strftime('%Y-%m')}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    logger.info(f"[Monthly] 月报已保存: {report_path.name}")
    return report
