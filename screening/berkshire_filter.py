"""
AI Berkshire 价值投资质量预筛模块 v1.0
────────────────────────────────────────
集成巴菲特/芒格/段永平/李录四大师框架到 Aurora 选股流程。
在 cascade_screen 之前执行，排除不满足一流公司标准的标的。

来源: https://github.com/xbtlin/ai-berkshire
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("aurora.berkshire")

# ═══════════════════════════════════════════════════════════════
# 7条去劣指标（来自 AI Berkshire quality-screen）
# ═══════════════════════════════════════════════════════════════

BERKSHIRE_FILTERS = {
    "roe_10yr": {
        "name": "10年平均ROE",
        "threshold": 8.0,           # < 8% 排除
        "description": "资本效率——股东的钱能不能跑赢机会成本",
        "weight": 0.25,
    },
    "fcf_5yr_cumulative": {
        "name": "5年累计自由现金流",
        "threshold": 0.0,           # < 0 排除（为负）
        "description": "真金白银——利润是不是纸面富贵",
        "weight": 0.25,
    },
    "interest_coverage": {
        "name": "利息覆盖倍数(EBIT/利息)",
        "threshold": 2.0,           # < 2倍 排除
        "description": "偿债安全——还利息的能力",
        "weight": 0.10,
    },
    "gross_margin_lt": {
        "name": "长期毛利率",
        "threshold": 15.0,          # < 15% 排除
        "description": "定价权——产品/服务有没有差异化",
        "weight": 0.15,
    },
    "ocf_to_ni_5yr": {
        "name": "经营现金流/净利润(5年均值)",
        "threshold": 0.7,           # < 0.7 排除
        "description": "利润质量——赚到的利润能不能收回现金",
        "weight": 0.10,
    },
    "net_margin_lt": {
        "name": "长期净利率",
        "threshold": 5.0,           # < 5% 排除
        "description": "抗风险能力——收入波动时利润是否归零",
        "weight": 0.10,
    },
    "share_dilution_5yr": {
        "name": "5年总股本膨胀",
        "threshold": 20.0,          # > 20%(非并购) 排除
        "description": "股东利益——管理层是否在稀释你的权益",
        "weight": 0.05,
    },
}


# ═══════════════════════════════════════════════════════════════
# 豁免规则（来自 AI Berkshire）
# ═══════════════════════════════════════════════════════════════

def check_strategic_exemption(metrics: dict) -> bool:
    """豁免A：战略投入期豁免（适用于ROE不达标）
    条件：上市<10年 + 毛利率>30% + 近2年经营现金流为正
    """
    return (
        metrics.get("listed_years", 100) < 10
        and metrics.get("gross_margin", 0) > 30
        and metrics.get("ocf_recent_positive", False)
    )


def check_low_margin_exemption(metrics: dict) -> bool:
    """豁免B：主动低利润率豁免（适用于净利率不达标）
    条件：毛利率>30% + 净利率回升趋势
    """
    return (
        metrics.get("gross_margin", 0) > 30
        and metrics.get("net_margin_recovering", False)
    )


def check_high_turnover_exemption(metrics: dict) -> bool:
    """豁免C：高周转薄利豁免（适用于毛利率+净利率不达标）
    条件：ROE>20% + 经营现金流/净利润>1.0 + 平台型商业模式
    """
    return (
        metrics.get("roe", 0) > 20
        and metrics.get("ocf_to_ni", 0) > 1.0
        and metrics.get("is_platform_model", False)
    )


# ═══════════════════════════════════════════════════════════════
# 核心过滤引擎
# ═══════════════════════════════════════════════════════════════

def berkshire_quality_filter(
    stocks: List[dict],
    cfg: dict = None,
) -> Tuple[List[dict], List[dict]]:
    """
    对候选股票列表执行 AI Berkshire 质量过滤。

    Args:
        stocks: 候选股票列表，每个包含:
            - code: 股票代码
            - name: 名称
            - pe: PE(TTM)
            - mcap: 市值(亿)
            - roe: ROE
            - gross_margin: 毛利率
            - net_margin: 净利率
            - fcf_per_share: 每股自由现金流
            - ocf_to_ni: 经营现金流/净利润
            - interest_coverage: 利息覆盖倍数
            - share_dilution_5yr: 5年股本变化%
            - listed_years: 上市年数
            （缺失字段自动跳过对应检查）
        cfg: 配置字典

    Returns:
        (passed, filtered_out): 通过和未通过的股票列表
    """
    if cfg is None:
        cfg = {}

    berkshire_cfg = cfg.get("screening", {}).get("berkshire", {})
    if not berkshire_cfg.get("enabled", True):
        logger.info("[Berkshire] 质量预筛未启用，跳过")
        return stocks, []

    min_score = berkshire_cfg.get("min_quality_score", 3)

    passed = []
    filtered_out = []

    for stock in stocks:
        code = stock.get("code", "?")
        name = stock.get("name", "?")

        # 计算质量评分
        quality = _evaluate_quality(stock, berkshire_cfg)

        if quality["passed"]:
            # 将质量评分附加到股票数据
            stock["berkshire_score"] = quality["score"]
            stock["berkshire_grade"] = quality["grade"]
            stock["berkshire_checks"] = quality["checks_passed"]
            stock["berkshire_total_checks"] = quality["total_checks"]
            passed.append(stock)
            logger.debug(
                f"[Berkshire] ✓ {name}({code}) 评分={quality['score']:.1f}/7 "
                f"等级={quality['grade']}"
            )
        else:
            filtered_out.append({
                **stock,
                "berkshire_score": quality["score"],
                "berkshire_grade": quality["grade"],
                "filter_reason": quality["reasons"],
            })
            logger.info(
                f"[Berkshire] ✗ {name}({code}) 评分={quality['score']:.1f}/7 "
                f"原因: {'; '.join(quality['reasons'][:3])}"
            )

    logger.info(
        f"[Berkshire] 质量预筛完成: {len(passed)}/{len(stocks)} 通过 "
        f"(最低评分要求={min_score})"
    )
    return passed, filtered_out


def _evaluate_quality(stock: dict, cfg: dict) -> dict:
    """对单只股票执行质量评估"""
    score = 0
    total = 0
    checks_passed = []
    checks_failed = []
    exemptions_used = []

    for key, rule in BERKSHIRE_FILTERS.items():
        total += 1
        value = stock.get(key)
        if value is None:
            continue  # 数据缺失，跳过该检查

        threshold = cfg.get(f"{key}_threshold", rule["threshold"])

        # 判断通过/不通过
        passed_check = value >= threshold

        # 应用豁免规则
        if not passed_check:
            exemption_applied = False

            if key == "roe_10yr" and check_strategic_exemption(stock):
                passed_check = True
                exemption_applied = True
                exemptions_used.append("豁免A(战略投入期):ROE")
            elif key == "net_margin_lt" and check_low_margin_exemption(stock):
                passed_check = True
                exemption_applied = True
                exemptions_used.append("豁免B(主动低利润):净利率")
            elif key in ("gross_margin_lt", "net_margin_lt") and check_high_turnover_exemption(stock):
                passed_check = True
                exemption_applied = True
                exemptions_used.append("豁免C(高周转薄利):毛利率/净利率")

        if passed_check:
            score += 1
            checks_passed.append(rule["name"])
        else:
            checks_failed.append(rule["name"])

    # 综合评分 (0-7分制)
    score = min(score, 7)

    # 等级判定
    if score >= 6:
        grade = "A"  # 一流公司
    elif score >= 4:
        grade = "B"  # 合格
    elif score >= 2:
        grade = "C"  # 需进一步研究
    else:
        grade = "D"  # 排除

    min_score = cfg.get("min_quality_score", 3)
    passed = score >= min_score

    return {
        "score": score,
        "grade": grade,
        "total_checks": total,
        "checks_passed": checks_passed,
        "checks_failed": checks_failed,
        "exemptions": exemptions_used,
        "passed": passed,
        "reasons": checks_failed if not passed else [],
    }


# ═══════════════════════════════════════════════════════════════
# 快速否决清单（六关中最后一关的8条红线）
# ═══════════════════════════════════════════════════════════════

VETO_CHECKS = [
    {
        "id": "mgmt_integrity",
        "name": "管理层诚信污点",
        "check": lambda s: not s.get("mgmt_integrity_redflag", False),
    },
    {
        "id": "persistent_loss",
        "name": "持续亏损无好转",
        "check": lambda s: not s.get("persistent_loss_no_recovery", False),
    },
    {
        "id": "fraud_suspect",
        "name": "财务造假嫌疑",
        "check": lambda s: not s.get("fraud_suspect", False),
    },
    {
        "id": "tech_obsolescence",
        "name": "技术过时风险",
        "check": lambda s: not s.get("tech_obsolescence_risk", False),
    },
    {
        "id": "regulatory_death",
        "name": "监管死刑风险",
        "check": lambda s: not s.get("regulatory_death_risk", False),
    },
    {
        "id": "customer_concentration",
        "name": "客户集中度极端",
        "check": lambda s: not s.get("customer_concentration_extreme", False),
    },
    {
        "id": "unsustainable_debt",
        "name": "债务不可持续",
        "check": lambda s: not s.get("unsustainable_debt", False),
    },
    {
        "id": "opaque_related_party",
        "name": "看不懂的关联交易",
        "check": lambda s: not s.get("opaque_related_party", False),
    },
]


def veto_check(stocks: List[dict]) -> Tuple[List[dict], List[dict]]:
    """
    执行8条快速否决清单检查。任何一条触发即排除。

    Returns:
        (passed, vetoed)
    """
    passed = []
    vetoed = []

    for stock in stocks:
        veto_reasons = []
        for check in VETO_CHECKS:
            if not check["check"](stock):
                veto_reasons.append(check["name"])

        if veto_reasons:
            stock["veto_reasons"] = veto_reasons
            vetoed.append(stock)
            logger.warning(
                f"[Berkshire] 🚫 否决 {stock.get('name','?')}({stock.get('code','?')}): "
                f"{'; '.join(veto_reasons)}"
            )
        else:
            passed.append(stock)

    if vetoed:
        logger.info(f"[Berkshire] 否决清单: {len(vetoed)} 只被一票否决")
    return passed, vetoed


# ═══════════════════════════════════════════════════════════════
# 一键全流程质量过滤
# ═══════════════════════════════════════════════════════════════

def berkshire_full_filter(
    stocks: List[dict],
    cfg: dict = None,
) -> Tuple[List[dict], dict]:
    """
    一键执行 AI Berkshire 完整质量过滤流程:
    1. 否决清单检查 (8条红线)
    2. 7条去劣指标评分
    3. A/B/C/D 等级分类

    Returns:
        (passed_stocks, summary_report)
    """
    if cfg is None:
        cfg = {}

    result = {
        "input_count": len(stocks),
        "vetoed": 0,
        "quality_failed": 0,
        "passed": 0,
        "grade_distribution": {"A": 0, "B": 0, "C": 0, "D": 0},
        "details": [],
    }

    # Step 1: 否决清单
    stocks, vetoed = veto_check(stocks)
    result["vetoed"] = len(vetoed)
    for v in vetoed:
        result["details"].append({
            "code": v.get("code"), "name": v.get("name"),
            "result": "vetoed", "reasons": v.get("veto_reasons", []),
        })

    # Step 2: 7条指标质量过滤
    passed, filtered = berkshire_quality_filter(stocks, cfg)
    result["quality_failed"] = len(filtered)
    result["passed"] = len(passed)

    for p in passed:
        grade = p.get("berkshire_grade", "?")
        result["grade_distribution"][grade] = result["grade_distribution"].get(grade, 0) + 1
        result["details"].append({
            "code": p.get("code"), "name": p.get("name"),
            "result": "passed",
            "score": p.get("berkshire_score", 0),
            "grade": grade,
        })

    for f in filtered:
        result["details"].append({
            "code": f.get("code"), "name": f.get("name"),
            "result": "quality_failed",
            "score": f.get("berkshire_score", 0),
            "grade": f.get("berkshire_grade", "?"),
            "reasons": f.get("filter_reason", []),
        })

    logger.info(
        f"[Berkshire] 全流程完成: {result['passed']}/{result['input_count']} 通过 "
        f"(否决{result['vetoed']} + 质量淘汰{result['quality_failed']})"
    )
    return passed, result
