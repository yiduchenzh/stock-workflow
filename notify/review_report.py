"""盘后复盘报告生成器 — Markdown输出 + 策略健康 + 行为偏误"""
import json, logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("aurora.report")
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPORT_DIR = DATA_DIR / "reports"

def generate_report(engine) -> str:
    """生成当日复盘Markdown报告"""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    lines = []

    # 标题
    lines.append(f"# Aurora Trading 复盘报告 — {today}")
    lines.append("")

    # 1. 市场概览
    lines.append("## 1. 市场概览")
    lines.append(f"- 市场状态: **{getattr(engine, 'market_regime', '?')}** ({getattr(engine, 'market_score', 0):.0f}/100)")
    if hasattr(engine, 'reflexivity'):
        lines.append(f"- 反身性阶段: {engine.reflexivity.get('stage', '?')[:50]}")
    if hasattr(engine, 'northbound'):
        nb = engine.northbound
        lines.append(f"- 北向资金: {nb.get('signal', '?')} (累计{nb.get('cumulative_yi', 0):.0f}亿)")
    lines.append("")

    # 2. 持仓 vs 计划
    plans = getattr(engine, 'plans', []) or []
    positions = getattr(engine, 'positions', {}) or {}
    lines.append("## 2. 交易计划")
    if plans:
        lines.append(f"| 代码 | 策略 | 入场价 | 仓位(股) | 止损 | 止盈 |")
        lines.append(f"|------|------|--------|---------|------|------|")
        for p in plans:
            lines.append(f"| {p.get('code','?')} | {p.get('strategy','?')} | {p.get('entry_price',0):.2f} | {p.get('shares',0)} | {p.get('stop_loss',0):.2f} | {p.get('take_profit',0):.2f} |")
    else:
        lines.append("_无交易计划_")
    lines.append("")

    # 3. 告警
    alerts = getattr(engine, 'alerts', []) or []
    lines.append("## 3. 告警")
    if alerts:
        for a in alerts:
            lines.append(f"- [{a.get('type','?')}] {a.get('msg','')} {a.get('reason','')}")
    else:
        lines.append("_无告警_")
    lines.append("")

    # 4. 策略健康度
    lines.append("## 4. 策略健康度")
    try:
        from strategies.evolution import get_all_health
        health = get_all_health()
        if health:
            lines.append(f"| 策略 | 状态 | 交易数 | 胜率 | 平均PnL | 建议 |")
            lines.append(f"|------|------|--------|------|--------|------|")
            for name, h in sorted(health.items()):
                wr = f"{h.get('win_rate',0)*100:.0f}%" if h.get('win_rate') is not None else "?"
                lines.append(f"| {name} | {h.get('status','?')} | {h.get('trades',0)} | {wr} | {h.get('avg_pnl',0):+.2%} | {h.get('recommendation','')} |")
        else:
            lines.append("_无策略数据_")
    except Exception as e:
        lines.append(f"_加载失败: {e}_")
    lines.append("")

    # 5. 行为偏误诊断
    lines.append("## 5. 行为偏误诊断")
    try:
        from strategies.behavior import diagnose
        diag = diagnose()
        if diag.get("issues"):
            for issue in diag["issues"]:
                lines.append(f"- ⚠️ {issue}")
        else:
            lines.append("_无显著偏误_")
    except Exception as e:
        lines.append(f"_诊断失败: {e}_")
    lines.append(f"- 系统模式: {'自动执行' if getattr(engine, 'mode', 'paper') == 'paper' else '人工干预'}")
    lines.append("")

    # 6. 观察池
    lines.append("## 6. 次日观察池")
    candidates = getattr(engine, 'candidates', []) or []
    if candidates:
        for c in candidates[:10]:
            lines.append(f"- {c.get('code','?')} {c.get('name','?')} (信号:{c.get('signal',False)})")
    else:
        lines.append("_无候选_")
    lines.append("")

    # 7. 汇总统计
    capital = getattr(engine, 'capital', 1_000_000)
    if hasattr(engine, 'account') and engine.account:
        acc = engine.account
        lines.append("## 7. 账户概览")
        lines.append(f"- 总资产: {acc.total_value:,.0f}")
        lines.append(f"- 现金: {acc.cash:,.0f}")
        lines.append(f"- 持仓数: {len(acc.positions)}")
        lines.append(f"- 收益率: {(acc.total_value/capital - 1)*100:+.2f}%")

    report = "\n".join(lines)
    report_path = REPORT_DIR / f"review_{today}.md"
    report_path.write_text(report, encoding="utf-8")
    logger.info(f"[Report] saved to {report_path}")
    return report


def push_report(engine):
    """生成并推送复盘报告"""
    report = generate_report(engine)
    try:
        token = getattr(engine, 'cfg', {}).get("notify", {}).get("sct_token", "")
        if token:
            import requests, os as _os
            token = _os.environ.get("SCT_TOKEN", token)
            if token and len(token) > 10:
                title = f"Aurora复盘 {datetime.now():%m-%d}"
                requests.post(f"https://sctapi.ftqq.com/{token}.send",
                             json={"title": title, "desp": report}, timeout=10)
                logger.info(f"[Report] pushed: {title}")
    except Exception:
        pass
