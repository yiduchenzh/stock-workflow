"""
AI Berkshire 组合审视工作流 v1.0
─────────────────────────────────
基于巴菲特"如果今天没有持仓,还会买吗?"原则,
对 Aurora 持仓列表执行定期质量审视。

触发: 每日盘后/每周五/每次调仓前
来源: https://github.com/xbtlin/ai-berkshire
"""
from __future__ import annotations
import json, logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger("aurora.berkshire.review")

PROJ = Path(__file__).resolve().parent.parent


def review_portfolio(engine) -> dict:
    """
    对当前持仓执行 AI Berkshire 组合质量审视。
    返回审查报告 dict。
    """
    positions = getattr(engine, "positions", {})
    if not positions:
        return {"status": "empty", "message": "当前无持仓"}

    review_items = []
    alerts = []

    for code, pos in positions.items():
        item = _review_single_position(code, pos, engine)
        review_items.append(item)
        if item.get("alert"):
            alerts.append(item["alert"])

    # 组合层面审视
    portfolio_health = _check_portfolio_health(review_items, engine)

    report = {
        "timestamp": datetime.now().isoformat(),
        "position_count": len(positions),
        "review_items": review_items,
        "alerts": alerts,
        "portfolio_health": portfolio_health,
    }

    # 保存报告
    _save_report(report)

    return report


def _review_single_position(code: str, pos: dict, engine) -> dict:
    """审视单个持仓的论文健康度"""
    name = pos.get("name", code)
    entry_price = pos.get("avg_cost", pos.get("entry_price", 0))
    current_price = pos.get("current_price", 0)
    pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0

    # 关键检查
    checks = {
        "thesis_intact": _check_thesis(code, engine),        # 买入逻辑是否变化
        "would_buy_today": _would_buy_today(code, current_price, engine),  # 今天还会买吗
        "five_year_comfort": _five_year_comfort(code, engine),  # 持有5年舒服吗
        "position_sizing": _check_position_sizing(pos, engine),  # 仓位是否合理
    }

    health_score = sum(1 for v in checks.values() if v) / len(checks) * 10

    alert = None
    if health_score < 5:
        alert = f"⚠️ {name}({code}) 论文健康度={health_score:.0f}/10: 建议审视是否减仓/清仓"
    elif health_score < 7:
        alert = f"📋 {name}({code}) 论文健康度={health_score:.0f}/10: 关注变化,暂不操作"

    return {
        "code": code,
        "name": name,
        "entry_price": entry_price,
        "current_price": current_price,
        "pnl_pct": round(pnl_pct, 2),
        "checks": checks,
        "health_score": round(health_score, 1),
        "alert": alert,
    }


def _check_thesis(code: str, engine) -> bool:
    """检查原始买入论文是否仍然完整"""
    # 从引擎配置或历史记录中获取 thesis
    # 简化实现: 检查是否有 thesis_tracker 记录
    history = getattr(engine, "thesis_history", {})
    thesis = history.get(code, {})
    if not thesis:
        return True  # 无记录则假定正常
    return not thesis.get("broken", False)


def _would_buy_today(code: str, price: float, engine) -> bool:
    """巴菲特式追问: 如果今天没有持仓,还会在当前价格买入吗?"""
    # 检查是否有质量过滤记录
    stock_info = getattr(engine, "berkshire_scores", {}).get(code, {})
    if stock_info:
        score = stock_info.get("berkshire_score", 0)
        grade = stock_info.get("berkshire_grade", "?")
        return score >= 4 and grade in ("A", "B")
    return True  # 无评分则假定可买入


def _five_year_comfort(code: str, engine) -> bool:
    """李录式追问: 如果明天开始不能交易,持有5年舒服吗?"""
    stock_info = getattr(engine, "berkshire_scores", {}).get(code, {})
    if stock_info:
        return stock_info.get("berkshire_grade") in ("A", "B")
    return True


def _check_position_sizing(pos: dict, engine) -> bool:
    """检查仓位是否在合理范围"""
    cfg = getattr(engine, "cfg", {})
    max_pos_pct = cfg.get("risk", {}).get("position_weights", {}).get("strong", 0.3)
    actual_pct = pos.get("pct", pos.get("weight", 0))
    return actual_pct <= max_pos_pct * 1.5  # 允许一定灵活度


def _check_portfolio_health(items: List[dict], engine) -> dict:
    """组合层面健康度评估"""
    if not items:
        return {"score": 0, "grade": "N/A"}

    avg_score = sum(i["health_score"] for i in items) / len(items)
    alerts = sum(1 for i in items if i.get("alert"))

    if avg_score >= 8:
        grade = "A"; advice = "组合健康,论文完整"
    elif avg_score >= 6:
        grade = "B"; advice = "总体良好,关注预警项"
    elif avg_score >= 4:
        grade = "C"; advice = "部分持仓论文弱化,建议审视"
    else:
        grade = "D"; advice = "多只持仓论文存疑,建议大幅调整"

    return {
        "score": round(avg_score, 1),
        "grade": grade,
        "advice": advice,
        "alert_count": alerts,
        "total_positions": len(items),
    }


def _save_report(report: dict):
    """保存审视报告"""
    report_dir = PROJ / "reports"
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / f"berkshire_review_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"[Berkshire] 组合审视报告已保存: {report_path}")


# ═══════════════════════════════════════════════════════════════
# Cron 工作流入口: 每日盘后自动执行
# ═══════════════════════════════════════════════════════════════

def daily_berkshire_review(engine):
    """每日盘后自动执行 AI Berkshire 组合审视"""
    logger.info("[Berkshire] 开始每日组合审视...")
    report = review_portfolio(engine)

    summary = report.get("portfolio_health", {})
    logger.info(
        f"[Berkshire] 审视完成: 组合健康度={summary.get('score',0):.1f}/10 "
        f"等级={summary.get('grade','?')}, 预警{summary.get('alert_count',0)}项"
    )

    # 推送预警
    if report.get("alerts"):
        from notify.push import send_wechat
        msg = "📊 AI Berkshire 组合审视\n"
        msg += f"健康度: {summary.get('score',0):.1f}/10 ({summary.get('grade','?')})\n"
        for alert in report["alerts"]:
            msg += f"\n{alert}"
        try:
            send_wechat(msg, engine.cfg)
        except Exception:
            pass

    return report
