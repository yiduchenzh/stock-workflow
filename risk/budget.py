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

    def _sane_value(self, v):
        """⭐ v14.48 净值合理性校验 (2026-08-19): 防 peak_value 被污染
        现象: risk_budget.json peak_value=20,529,521 (08-07 异常注入) → drawdown 永久 -95.3%
              → Budget pause 误触发, 系统被误锁
        防护: 净值超过 [capital*0.01, capital*5] 视为数据异常, 拒绝作为峰值基准
        """
        try:
            v = float(v)
            lo = self.capital * 0.01
            hi = self.capital * 5.0
            if v <= 0 or v < lo or v > hi:
                return None
            return v
        except Exception:
            return None

    def record_pnl(self, daily_pnl_pct: float, current_value: float = None):
        """每日记录PnL — v14.49(2026-09-11, P1-2): 改为【按日期覆盖】口径.

        背景: 原实现"同一自然日只累加一次", 而引擎每日多次扫描(morning/monitor/noon/close),
        首次调用多在开盘前 → 记下 ≈0 的值后当日不再更新 → weekly_pnl 恒 ~1e-9
        (2026-09-11 复盘实测 risk_budget*.json weekly_pnl=1e-9~1e-10) → 周-5%/月-8%闸永不触发。
        现在: state["daily"][date] = daily_pnl_pct(覆盖写, 天然幂等, 同日多次调用不虚增);
              weekly_pnl = 近7天求和, monthly_pnl = 近30天求和(每次重算, 自动滚动)。
        兼容: 保留 weekly_start/monthly_start/last_record_date 字段(旧文件可直接读)。
        """
        today_str = time.strftime("%Y-%m-%d")
        sane_cur = self._sane_value(current_value) if current_value else None

        # ① 每日盈亏按日期覆盖写(幂等)
        daily = self.state.get("daily")
        if not isinstance(daily, dict):
            daily = {}
        daily[today_str] = float(daily_pnl_pct or 0.0)
        # 只保留近 40 天
        if len(daily) > 40:
            for k in sorted(daily)[:-40]:
                daily.pop(k, None)
        self.state["daily"] = daily

        # ② 周/月 = 近 7 / 近 30 天求和
        def _sum_days(n: int) -> float:
            import datetime as _dt
            today = _dt.date.today()
            tot = 0.0
            for k, v in daily.items():
                try:
                    d = _dt.date.fromisoformat(k)
                except Exception:
                    continue
                if 0 <= (today - d).days < n:
                    tot += float(v or 0)
            return max(-1.0, min(1.0, tot))

        self.state["weekly_pnl"] = _sum_days(7)
        self.state["monthly_pnl"] = _sum_days(30)
        self.state["weekly_start"] = self.state.get("weekly_start") or time.time()
        self.state["monthly_start"] = self.state.get("monthly_start") or time.time()

        # 最大回撤
        if sane_cur is not None:
            self.state["current_value"] = sane_cur
            peak = self._sane_value(self.state.get("peak_value", 0))
            if peak is None:
                peak = self.capital
            if sane_cur > peak:
                self.state["peak_value"] = sane_cur
                peak = sane_cur
            self.state["drawdown_pct"] = (sane_cur - peak) / max(peak, 1)
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
