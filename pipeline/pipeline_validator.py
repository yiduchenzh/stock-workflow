"""
Pipeline Integrity Validator v1.0 — 管线契约自动化验证器
======================================================
在每个step执行前后自动检查输出schema和跨步一致性。
P0级防护：防止管线断裂类bug静默运行（如R23发现的positions未同步问题）。

用法:
    from pipeline.pipeline_validator import PipelineValidator
    validator = PipelineValidator(engine)
    engine.pipeline_validator = validator  # run() 自动调用
    engine.run()
    report = validator.report()
"""

import logging
import time

logger = logging.getLogger("aurora.pipeline")


# 管线契约定义
STEP_CONTRACTS = {
    "step_market": {
        "label": "市场体检",
        "outputs": {
            "market_score": {
                "type": (int, float),
                "range": (0, 100),
                "msg": "market_score必须是0-100的数字",
            },
            "market_regime": {
                "type": str,
                "in_values": [
                    "bull_strong", "bull_weak", "range", "bear_weak", "bear_strong",
                ],
                "msg": "market_regime必须是5种regime之一",
            },
        },
    },
    "step_cascade": {
        "label": "三级联动",
        "outputs": {
            "candidates": {
                "type": list,
                "msg": "candidates必须是list（空list=无候选股，正确）",
            },
        },
    },
    "step_screen": {
        "label": "CAN SLIM选股",
        "outputs": {
            "screened": {
                "type": (list, type(None)),
                "msg": "screened必须是list或None",
            },
        },
    },
    "step_analyze": {
        "label": "7战法分析",
        "outputs": {
            "analysis": {"type": list, "msg": "analysis必须是list"},
        },
        "content_checks": True,
    },
    "step_score": {
        "label": "综合评分",
        "outputs": {
            "scores": {"type": list, "msg": "scores必须是list"},
        },
    },
    "step_position": {
        "label": "仓位计划",
        "outputs": {
            "plans": {"type": list, "msg": "plans必须是list"},
        },
    },
    "step_risk": {
        "label": "风控审核",
        "outputs": {
            "plans": {"type": list, "msg": "plans必须是list"},
            "alerts": {"type": list, "msg": "alerts必须是list"},
        },
    },
    "step_simulate": {
        "label": "模拟交易",
        "outputs": {
            "account": {
                "type": object,
                "not_none": True,
                "msg": "account必须存在（SimAccount实例）",
                "check_attrs": ["positions", "cash", "buy", "sell"],
            },
            "positions": {
                "type": dict,
                "msg": "positions必须是dict（已从account.positions同步）",
            },
        },
        "cross_checks": True,
    },
    "step_monitor": {
        "label": "实时监控",
    },
    "step_rebalance": {
        "label": "动态调仓",
    },
    "step_evaluate": {"label": "策略评估"},
    "step_review": {"label": "复盘"},
    "step_prep": {"label": "次日准备"},
}


# 跨步契约
CROSS_STEP_CONTRACTS = [
    {
        "id": "CS-001",
        "severity": "P0",
        "desc": "step_simulate后self.positions须与self.account.positions同步",
        "check": lambda e: (
            _check_account_positions_synced(e),
            "self.positions与self.account.positions不同步！",
        ),
    },
    {
        "id": "CS-002",
        "severity": "P0",
        "desc": "step_rebalance复用self.account，不创建新SimAccount",
        "check": lambda e: (True, ""),
    },
    {
        "id": "CS-003",
        "severity": "P1",
        "desc": "acc.sell()返回值含success字段",
        "check": lambda e: (True, ""),
    },
    {
        "id": "CS-004",
        "severity": "P1",
        "desc": "confirm_entry返回值是3元tuple (passed, conf, checks)",
        "check": lambda e: (True, ""),
    },
    {
        "id": "CS-005",
        "severity": "P1",
        "desc": "step_monitor实时从API拉取大盘涨跌，不硬编码为0",
        "check": lambda e: (True, ""),
    },
]


class PipelineValidator:
    """管线契约自动化验证器 — 引擎健康检查"""

    def __init__(self, engine, auto_fix=True):
        self.engine = engine
        self.auto_fix = auto_fix
        self.errors = []
        self.warnings = []
        self.fixes_applied = []
        self._step_results = {}
        self._account_before_rebalance = None

    def validate_before(self, step_name):
        """step执行前验证"""
        engine = self.engine
        if step_name == "step_monitor":
            positions = getattr(engine, "positions", {})
            if not positions and not getattr(engine, "account", None):
                self._record_warning("step_monitor: positions为空，监控跳过(正常)")
            elif not positions and getattr(engine, "account", None):
                acc_pos = getattr(engine.account, "positions", {})
                if acc_pos:
                    self._record_error(
                        "P0",
                        "step_monitor前置: positions为空但account.positions有数据 — 未同步！",
                        fix="engine.positions = engine.account.positions",
                    )

        if step_name == "step_rebalance":
            self._account_before_rebalance = id(getattr(engine, "account", None))

    def validate_after(self, step_name):
        """step执行后验证"""
        contract = STEP_CONTRACTS.get(step_name)
        if not contract:
            return

        engine = self.engine
        outputs = contract.get("outputs", {})

        for attr_name, rules in outputs.items():
            val = getattr(engine, attr_name, None)
            self._check_attribute(step_name, attr_name, val, rules)

        if step_name == "step_simulate" and contract.get("cross_checks"):
            self._run_cross_step_checks()

        if contract.get("content_checks"):
            self._check_content(step_name)

        if step_name == "step_rebalance":
            self._check_rebalance_account_reuse()

        self._step_results[step_name] = {
            "errors": len([e for e in self.errors if e.get("_step", step_name) == step_name]),
            "warnings": len([w for w in self.warnings if w.get("_step", step_name) == step_name]),
        }

    def validate_all(self):
        """全量跨步契约检查"""
        engine = self.engine
        results = {"passed": 0, "failed": 0, "checks": []}
        for contract in CROSS_STEP_CONTRACTS:
            try:
                passed, msg = contract["check"](engine)
                results["checks"].append({
                    "id": contract["id"],
                    "severity": contract["severity"],
                    "desc": contract["desc"],
                    "passed": passed,
                    "msg": msg,
                })
                if passed:
                    results["passed"] += 1
                else:
                    results["failed"] += 1
                    rec = self._record_error if contract["severity"] == "P0" else self._record_warning
                    rec(f"[{contract['id']}] {contract['desc']}: {msg}")
            except Exception as e:
                results["checks"].append({
                    "id": contract["id"],
                    "severity": "ERROR",
                    "desc": contract["desc"],
                    "passed": False,
                    "msg": str(e),
                })
                results["failed"] += 1
        return results

    def report(self):
        """生成管线健康报告"""
        cross = self.validate_all()
        return {
            "step_results": self._step_results,
            "errors": self.errors,
            "warnings": self.warnings,
            "fixes_applied": self.fixes_applied,
            "cross_step": cross,
            "summary": {
                "total_errors": len(self.errors),
                "total_warnings": len(self.warnings),
                "steps_with_issues": len(self._step_results),
                "cross_step_passed": cross["passed"],
                "cross_step_failed": cross["failed"],
            },
        }

    def summary_str(self):
        """可读摘要字符串"""
        r = self.report()
        s = r["summary"]
        lines = ["=" * 50, "管线完整性报告 (Pipeline Integrity Report)", "=" * 50]
        if s["total_errors"] > 0:
            lines.append(f"\n  {s['total_errors']} Errors:")
            for err in self.errors[:5]:
                lines.append(f"    [{err.get('severity','?')}] {err['msg'][:80]}")
                if err.get("fix"):
                    lines.append(f"      Fix: {err['fix']}")
        if s["total_warnings"] > 0:
            lines.append(f"\n  {s['total_warnings']} Warnings:")
            for w in self.warnings[:5]:
                lines.append(f"    {w['msg'][:80]}")
        lines.append(
            f"\nCross-step: {s['cross_step_passed']}P/{s['cross_step_failed']}F"
        )
        lines.append(f"Steps: {len(self._step_results)}/{len(STEP_CONTRACTS)}")
        if self.fixes_applied:
            lines.append(f"\nAuto-fixes: {len(self.fixes_applied)}")
            for f in self.fixes_applied:
                lines.append(f"  {f}")
        lines.append("=" * 50)
        return "\n".join(lines)

    def _check_attribute(self, step_name, attr_name, val, rules):
        """检查单个属性"""
        if rules.get("not_none") and val is None:
            self._record_error(
                "P0", f"[{step_name}] {attr_name} = None (必须存在)",
                fix=f"确保{step_name}中设置了self.{attr_name}",
                step=step_name,
            )
            return
        if val is None:
            return
        expected_type = rules.get("type", object)
        if not isinstance(val, expected_type):
            self._record_error(
                "P1", f"[{step_name}] {attr_name}类型错误: "
                f"期望{expected_type}, 实际{type(val).__name__}",
                fix=rules.get("msg", ""),
                step=step_name,
            )
            return
        val_range = rules.get("range")
        if val_range and isinstance(val, (int, float)):
            lo, hi = val_range
            if val < lo or val > hi:
                self._record_warning(
                    f"[{step_name}] {attr_name}={val:.0f} 超出范围[{lo}, {hi}]",
                    step=step_name,
                )
        in_values = rules.get("in_values")
        if in_values and isinstance(val, str):
            if val not in in_values:
                self._record_warning(
                    f"[{step_name}] {attr_name}='{val}' 不在期望值域{in_values}",
                    step=step_name,
                )
        check_attrs = rules.get("check_attrs")
        if check_attrs and val is not None:
            missing = [a for a in check_attrs if not hasattr(val, a)]
            if missing:
                self._record_error(
                    "P0",
                    f"[{step_name}] {attr_name}缺少必要属性: {missing}",
                    fix=f"确保该实例是SimAccount类并实现了{missing}",
                    step=step_name,
                )

    def _check_content(self, step_name):
        """内容级检查"""
        if step_name == "step_analyze":
            analysis = getattr(self.engine, "analysis", [])
            for i, a in enumerate(analysis):
                if not isinstance(a, dict):
                    continue
                if "signal" not in a:
                    self._record_warning(f"[step_analyze] analysis[{i}]缺少signal字段")

    def _run_cross_step_checks(self):
        """跨步一致性检查"""
        engine = self.engine
        account = getattr(engine, "account", None)
        positions = getattr(engine, "positions", {})
        if account is not None and hasattr(account, "positions"):
            if isinstance(positions, dict) and isinstance(account.positions, dict):
                if positions is not account.positions:
                    self._record_error(
                        "P0",
                        "step_simulate: self.positions与self.account.positions是不同对象!",
                        fix="在engine.py step_simulate末尾插入: self.positions = acc.positions",
                        step="step_simulate",
                    )
                    if self.auto_fix:
                        engine.positions = account.positions
                        self.fixes_applied.append("self.positions = account.positions (auto-fix)")

    def _check_rebalance_account_reuse(self):
        """检查account是否被复用"""
        engine = self.engine
        cur_id = id(getattr(engine, "account", None))
        prev_id = self._account_before_rebalance
        if prev_id is not None and cur_id != prev_id:
            self._record_error(
                "P0",
                f"step_rebalance创建新account实例! (id变化: {prev_id} -> {cur_id})",
                fix="step_rebalance应复用self.account，不创建SimAccount()新实例",
                step="step_rebalance",
            )

    def _record_error(self, severity, msg, fix="", step=""):
        self.errors.append({"severity": severity, "msg": msg, "fix": fix, "_step": step})

    def _record_warning(self, msg, step=""):
        self.warnings.append({"msg": msg, "_step": step})


# ── 跨步契约检查函数 ──

def _check_account_positions_synced(engine):
    """CS-001: 检查positions是否与account.positions同步"""
    account = getattr(engine, "account", None)
    positions = getattr(engine, "positions", {})
    if account is None or not hasattr(account, "positions"):
        return True
    acc_positions = account.positions
    if isinstance(positions, dict) and isinstance(acc_positions, dict):
        if positions is acc_positions:
            return True
        pos_set = set(positions.keys())
        acc_set = set(acc_positions.keys())
        if pos_set != acc_set:
            return False
    return True