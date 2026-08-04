"""
总风险预算模块 — P0升级
========================
功能: 周度/月度总亏损上限 + 最大回撤熔断
确保"单笔止损"之上有"总盘子保护"。

使用方式:
    from risk.budget import RiskBudget
    budget = RiskBudget(cfg)
    budget.check()       # 检查是否超限,返回dict
    budget.record_pnl(daily_pnl)  # 每日记录
    budget.reset_weekly()  # 每周一重置
"""
import json, logging, time, os
from pathlib import Path

logger = logging.getLogger("aurora.budget")

# v14.41: 按AURORA_AGENT隔离budget文件(与risk_state/recovery_state一致), 防6Agent互相污染
# 注意: 6Agent在同一进程串行运行, 不能用模块级变量(首次import固定), 必须实例化时动态计算
def _budget_file_path():
    agent = os.environ.get("AURORA_AGENT")
    if agent:
        return Path(__file__).resolve().parent.parent / "data" / f"risk_budget_{agent}.json"
    return Path(__file__).resolve().parent.parent / "data" / "risk_budget.json"

BUDGET_FILE = _budget_file_path()  # 兼容外部直接引用(单引擎场景)


class RiskBudget:
    """总风险预算管理器"""

    def __init__(self, cfg: dict = None, capital: float = 1_000_000):
        self.capital = capital
        self.cfg = cfg or {}
        budget_cfg = self.cfg.get("risk_budget", {})
        self.weekly_limit = budget_cfg.get("weekly_loss_limit", -0.05)      # 周-5%
        self.monthly_limit = budget_cfg.get("monthly_loss_limit", -0.08)    # 月-8%
        self.max_drawdown = budget_cfg.get("max_drawdown", -0.12)           # 最大回撤-12%
        self.reset_on_friday = budget_cfg.get("reset_on_friday", True)
        self.state = self._load()

    def _file(self) -> Path:
        """v14.41: 动态文件路径 — 实例化时读AURORA_AGENT(6Agent同进程串行场景必须动态)"""
        return _budget_file_path()

    def _load(self) -> dict:
        try:
            if self._file().exists():
                return json.loads(self._file().read_text(encoding="utf-8"))
        except Exception:
            pass
        return {
            "weekly_pnl": 0.0,
            "weekly_start": time.time(),
            "monthly_pnl": 0.0,
            "monthly_start": time.time(),
            "peak_value": self.capital,
            "current_value": self.capital,
            "drawdown_pct": 0.0,
            "last_record_date": "",
            "last_update": "",
        }

    def _save(self):
        try:
            self._file().parent.mkdir(parents=True, exist_ok=True)
            self._file().write_text(json.dumps(self.state, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.debug(f"[Budget] save: {e}")

    def record_pnl(self, daily_pnl_pct: float, current_value: float = None):
        """每日记录PnL — v14.41: 按日期去重, 同日多次扫描只累加一次, 防虚增"""
        now = time.time()
        day_secs = 86400
        week_secs = day_secs * 7
        month_secs = day_secs * 30
        today_str = time.strftime("%Y-%m-%d")

        # 同日去重: 当天已记录过则只更新净值/回撤, 不重复累加盈亏
        if self.state.get("last_record_date") == today_str:
            if current_value:
                self.state["current_value"] = current_value
                if current_value > self.state.get("peak_value", 0):
                    self.state["peak_value"] = current_value
                peak = self.state.get("peak_value", 1) or 1
                self.state["drawdown_pct"] = (current_value - peak) / max(peak, 1)
                self.state["drawdown_pct"] = max(-1.0, min(0.0, self.state["drawdown_pct"]))
            self.state["last_update"] = str(time.strftime("%Y-%m-%d %H:%M"))
            self._save()
            return

        # 周预算滚动
        if now - self.state["weekly_start"] > week_secs:
            self.state["weekly_pnl"] = 0.0
            self.state["weekly_start"] = now
        self.state["weekly_pnl"] += daily_pnl_pct
        self.state["weekly_pnl"] = max(-1.0, min(1.0, self.state["weekly_pnl"]))

        # 月预算滚动
        if now - self.state["monthly_start"] > month_secs:
            self.state["monthly_pnl"] = 0.0
            self.state["monthly_start"] = now
        self.state["monthly_pnl"] += daily_pnl_pct
        self.state["monthly_pnl"] = max(-1.0, min(1.0, self.state["monthly_pnl"]))

        # 最大回撤
        if current_value:
            self.state["current_value"] = current_value
            if current_value > self.state["peak_value"]:
                self.state["peak_value"] = current_value
            self.state["drawdown_pct"] = (current_value - self.state["peak_value"]) / max(self.state["peak_value"], 1)
            self.state["drawdown_pct"] = max(-1.0, min(0.0, self.state["drawdown_pct"]))

        self.state["last_record_date"] = today_str
        self.state["last_update"] = str(time.strftime("%Y-%m-%d %H:%M"))
        self._save()

    def check(self) -> dict:
        """
        检查是否触发风险预算熔断。
        
        Returns:
            dict: {triggered: bool, level: str, reason: str, action: str}
                  action: 'warn' / 'reduce_half' / 'close_all' / 'pause'
        """
        result = {"triggered": False, "level": "normal", "reason": "", "action": "none"}

        # 检查1: 周亏损上限
        weekly = self.state.get("weekly_pnl", 0.0)
        if weekly <= self.weekly_limit:
            result.update({
                "triggered": True,
                "level": "weekly",
                "reason": f"周亏损{weekly*100:.1f}% ≤ {self.weekly_limit*100:.0f}%",
                "action": "reduce_half",
            })
            return result

        # 检查2: 月亏损上限
        monthly = self.state.get("monthly_pnl", 0.0)
        if monthly <= self.monthly_limit:
            result.update({
                "triggered": True,
                "level": "monthly",
                "reason": f"月亏损{monthly*100:.1f}% ≤ {self.monthly_limit*100:.0f}%",
                "action": "close_all",
            })
            return result

        # 检查3: 最大回撤
        dd = self.state.get("drawdown_pct", 0.0)
        if dd <= self.max_drawdown:
            # 回撤超过最大回撤 → 暂停系统
            result.update({
                "triggered": True,
                "level": "drawdown",
                "reason": f"最大回撤{dd*100:.1f}% ≤ {self.max_drawdown*100:.0f}%",
                "action": "pause",
            })
            return result

        # 检查4: 中等级别预警 — 周亏损已到80%上限
        weekly_80pct = self.weekly_limit * 0.8
        if weekly <= weekly_80pct:
            result.update({
                "triggered": True,
                "level": "weekly_warn",
                "reason": f"周亏损{weekly*100:.1f}% 已达{self.weekly_limit*100:.0f}%的80%",
                "action": "warn",
            })
            return result

        return result

    def get_summary(self) -> str:
        """获取预算摘要(打印用)"""
        w = self.state.get("weekly_pnl", 0.0)
        m = self.state.get("monthly_pnl", 0.0)
        dd = self.state.get("drawdown_pct", 0.0)
        return (f"Budget: 周{w*100:.1f}%[{self.weekly_limit*100:.0f}%] "
                f"月{m*100:.1f}%[{self.monthly_limit*100:.0f}%] "
                f"回撤{dd*100:.1f}%[{self.max_drawdown*100:.0f}%]")

    def reset_weekly(self):
        """每周重置(周一自动调用)"""
        self.state["weekly_pnl"] = 0.0
        self.state["weekly_start"] = time.time()
        self._save()
        logger.info(f"[Budget] 周预算重置")

    def reset_monthly(self):
        self.state["monthly_pnl"] = 0.0
        self.state["monthly_start"] = time.time()
        self._save()
        logger.info(f"[Budget] 月预算重置")
