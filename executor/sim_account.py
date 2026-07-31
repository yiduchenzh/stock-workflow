"""高仿真模拟账户 — 含滑点/冲击成本/排队模拟/费用精确计算

支持微结构执行增强模块 (executor.microstructure):
  - Almgren-Chriss动态冲击成本
  - VWAP/TWAP执行计划
  - 限价单/市价单智能选择
  - 增强滑点模型
"""
import json, logging, random, time
from pathlib import Path
from datetime import datetime
from typing import Optional
from executor.base import BaseExecutor
from executor.microstructure import (
    MicrostructureSlippage,
    AlmgrenChrissImpact,
    VWAPExecutionPlan,
    TWAPExecutionPlan,
    OrderTypeSelector,
    create_microstructure,
)
logger = logging.getLogger("aurora.sim")

DATA = Path(__file__).resolve().parent.parent / "data"
STATE = DATA / "sim_state.json"
TRADES = DATA / "sim_trades.json"
# 测试隔离: _test_/_fix_脚本使用隔离文件
import inspect as _insp
_TF = _insp.currentframe()
while _TF:
    _fn = _TF.f_code.co_filename
    if "_test" in _fn or "_fix_" in _fn or "tests" in _fn:
        STATE = DATA / "sim_state_test.json"
        TRADES = DATA / "sim_trades_test.json"
        break
    _TF = _TF.f_back
del _TF, _insp


class SimAccount(BaseExecutor):
    """高仿真模拟账户 — 模拟真实市场微观结构"""

    def __init__(self, capital: float = 1_000_000, config: dict = None):
        super().__init__(capital)
        self.config = config or {}
        self.commission = 0.0003      # 佣金0.03%
        self.stamp_tax = 0.001        # 印花税0.1% (仅卖出)
        self.slippage_base = 0.001     # 基础滑点0.1%
        self.slippage_tiers = {      # 按市值分层 (Quant审计)
            500: 0.001,   # >500亿: 0.1%
            100: 0.002,   # 100-500亿: 0.2%
            0:   0.003,   # <100亿: 0.3%
        }
        self.impact_factor = 0.0001   # 冲击成本(每100万成交额+0.01%) [legacy]
        self.today_buys: dict[str, int] = {}  # A股T+1: 今日买入不可卖出

        # ── 微结构执行增强模块 ──
        self._use_microstructure = self.config.get("use_microstructure", True)
        ms_config = self.config.get("microstructure", {})
        self._ms_slippage = MicrostructureSlippage(
            avg_daily_turnover=ms_config.get("avg_daily_turnover", 5e8),
            daily_volume_shares=ms_config.get("daily_volume_shares", 5_000_000),
            annual_volatility=ms_config.get("annual_volatility", 0.30),
            use_ac_model=ms_config.get("use_ac_model", True),
        )
        self._stock_micro_cache: dict[str, dict] = {}

        self._load()

    # ── 微结构增强核心方法 ──

    def register_stock_market_params(
        self,
        code: str,
        avg_daily_turnover: float,
        daily_volume_shares: float,
        annual_volatility: float = 0.30,
        mcap_hundred_million: float = 200.0,
    ):
        """注册个股市场参数, 用于精确滑点计算

        Args:
            code: 股票代码
            avg_daily_turnover: 日均成交额(元)
            daily_volume_shares: 日均成交量(股)
            annual_volatility: 年化波动率
            mcap_hundred_million: 市值(亿)
        """
        self._stock_micro_cache[code] = {
            "avg_daily_turnover": avg_daily_turnover,
            "daily_volume_shares": daily_volume_shares,
            "annual_volatility": annual_volatility,
            "mcap_hundred_million": mcap_hundred_million,
        }

    def _get_micro_slippage(self, code: str, shares: int, price: float,
                            is_buy: bool) -> dict:
        """获取微结构增强滑点, 含缓存回退"""
        params = self._stock_micro_cache.get(code)
        if params is not None and self._use_microstructure:
            self._ms_slippage.update_market_params(
                avg_daily_turnover=params["avg_daily_turnover"],
                daily_volume_shares=params["daily_volume_shares"],
                annual_volatility=params["annual_volatility"],
            )
            return self._ms_slippage.compute_slippage(
                shares=shares, price=price, is_buy=is_buy,
                mcap_hundred_million=params["mcap_hundred_million"],
            )
        else:
            # 回退到原始逻辑
            mcap = getattr(self, 'stock_mcap', 200)
            base_slip = 0.003
            for threshold, slip in sorted(self.slippage_tiers.items(), reverse=True):
                if mcap >= threshold: base_slip = slip; break
            now = datetime.now()
            t = now.hour * 60 + now.minute
            if 9*60+30 <= t < 9*60+45:
                tf = 2.0
            elif 9*60+45 <= t < 11*60:
                tf = 1.0
            elif 11*60 <= t < 11*60+30:
                tf = 1.2
            elif 13*60 <= t < 13*60+30:
                tf = 1.5
            elif 13*60+30 <= t < 14*60+30:
                tf = 1.0
            elif 14*60+30 <= t < 15*60:
                tf = 2.5
            else:
                tf = 1.0
            slip = base_slip * tf + random.uniform(0, 0.001)
            return {
                "slippage": slip,
                "base_slippage": base_slip,
                "time_factor": tf,
                "ac_impact": 0.0,
                "noise": random.uniform(0, 0.001),
                "fill_price": price * (1 + slip) if is_buy else price * (1 - slip),
                "impact_detail": {},
                "order_type_advice": {},
            }

    def buy(self, code: str, price: float, shares: int, reason: str = "",
            context: dict = None) -> dict:
        """模拟买入 — 含增强滑点+冲击成本 (支持微结构执行模块)

        Args:
            code: 股票代码
            price: 参考价
            shares: 股数
            reason: 触发原因
            context: 决策证据链(六问①-③), 可含:
                regime(市场状态), signal(信号名), strategy(策略),
                time_gate(时间门结果), kelly(凯利仓位), consensus(共识Agent数),
                phase(运行阶段), note(备注)
        """
        if shares < 100: return {"success": False, "error": "最小100股"}
        shares = int(shares / 100) * 100

        ms = self._get_micro_slippage(code, shares, price, is_buy=True)
        slippage = ms["slippage"]
        fill_price = ms["fill_price"]

        notional = fill_price * shares
        fee = notional * self.commission
        total_cost = notional + fee

        if total_cost > self.cash:
            max_shares = int(self.cash * 0.98 / (fill_price * (1 + self.commission)) / 100) * 100
            if max_shares < 100:
                return {"success": False, "error": f"资金不足(需{total_cost:.0f}>现金{self.cash:.0f})"}
            shares = max_shares
            notional = fill_price * shares
            fee = notional * self.commission
            total_cost = notional + fee

        self.cash -= total_cost

        today = str(datetime.now().date())
        if code in self.positions:
            p = self.positions[code]
            old_total = p["shares"] * p["avg_cost"]
            p["shares"] += shares
            p["avg_cost"] = round((old_total + total_cost) / p["shares"], 4)
        else:
            self.positions[code] = {
                "shares": shares, "avg_cost": round(total_cost / shares, 4),
                "current_price": fill_price, "entry_date": today,
            }
        self.today_buys[code] = self.today_buys.get(code, 0) + shares

        trade = {
            "action": "buy", "code": code, "shares": shares,
            "price": round(fill_price, 2),
            "slippage_pct": round(slippage * 100, 4),
            "base_slip_pct": round(ms.get("base_slippage", 0) * 100, 4),
            "time_factor": ms.get("time_factor", 1.0),
            "ac_impact_pct": round(ms.get("ac_impact", 0) * 100, 4),
            "fee": round(fee, 2), "total": round(total_cost, 2),
            "order_type": ms.get("order_type_advice", {}).get("order_type", "market"),
            "reason": reason, "time": datetime.now().isoformat(),
            # ── 六问证据链: 决策上下文 (buy_what/when/how_much) ──
            "context": context or {},
        }
        self.trades.append(trade)
        self._save()
        logger.info(f"[SIM BUY] {code} {shares}sh @{fill_price:.2f} "
                    f"slippage={slippage*100:.3f}% fee={fee:.2f}")
        return {"success": True, "trade": trade}

    # ── 卖出原因分类映射 (六问⑤: 错在哪) ──
    SELL_REASON_MAP = [
        # (子串, 分类, 中文说明)
        ("stop_loss", "risk_stop", "风控止损"),
        ("breach_stop", "risk_stop", "风控止损"),
        ("trailing", "risk_trail", "移动止盈回撤"),
        ("take_profit", "take_profit", "止盈"),
        ("tp", "take_profit", "止盈"),
        ("mtf_close", "signal_exit", "信号退出"),
        ("mtf", "signal_exit", "信号退出"),
        ("scale_out", "partial_exit", "分批减仓"),
        ("time", "time_exit", "超时退出"),
        ("ghost", "housekeeping", "幽灵清理"),
    ]

    @staticmethod
    def classify_sell_reason(reason: str) -> dict:
        """将卖出原因归类为六问⑤可诊断分类"""
        reason = reason or ""
        for sub, cat, label in SimAccount.SELL_REASON_MAP:
            if sub in reason:
                return {"category": cat, "label": label}
        return {"category": "manual_exit", "label": "手动/其他退出"}

    def sell(self, code: str, price: float, shares: int, reason: str = "") -> dict:
        """模拟卖出 — 含增强滑点+印花税 (A股T+1: 今日买入不可卖出)"""
        if code not in self.positions: return {"success": False, "error": f"无{code}持仓"}
        pos = self.positions[code]
        if shares > pos["shares"]: shares = pos["shares"]
        today_locked = self.today_buys.get(code, 0)
        sellable = pos["shares"] - today_locked
        if sellable < 100:
            return {"success": False, "error": f"T+1限制: {code}今日买入{today_locked}股不可卖,可卖{sellable}股"}
        if shares > sellable:
            shares = max(100, int(sellable / 100) * 100)
            logger.info(f"[T+1] {code}: 限制卖出{shares}股(今日买入{today_locked}股被锁定)")
        if shares < 100: return {"success": False, "error": "最小100股"}
        shares = int(shares / 100) * 100

        ms = self._get_micro_slippage(code, shares, price, is_buy=False)
        slippage = ms["slippage"]
        fill_price = ms["fill_price"]

        notional = fill_price * shares
        commission = notional * self.commission
        stamp = notional * self.stamp_tax
        net = notional - commission - stamp

        pnl = net - shares * pos["avg_cost"]
        avg_cost = pos["avg_cost"]
        pnl_pct = round(pnl / (shares * avg_cost) * 100, 2) if shares > 0 and avg_cost > 0 else 0

        self.cash += net
        pos["shares"] -= shares
        if pos["shares"] <= 0: del self.positions[code]

        # ── 六问证据链: 关联最近买入上下文 + 归因分类 ──
        buy_ctx = {}
        for t in reversed(self.trades):
            if t.get("action") == "buy" and t.get("code") == code:
                buy_ctx = t.get("context", {}) or {}
                break
        sell_cls = self.classify_sell_reason(reason)
        # 持仓天数
        holding_days = 0
        entry_date = pos.get("entry_date") or buy_ctx.get("buy_date", "")
        if entry_date:
            try:
                holding_days = (datetime.now() - datetime.strptime(str(entry_date)[:10], "%Y-%m-%d")).days
            except Exception:
                holding_days = 0

        trade = {
            "action": "sell", "code": code, "shares": shares,
            "price": round(fill_price, 2),
            "slippage_pct": round(slippage*100, 4),
            "base_slip_pct": round(ms.get("base_slippage", 0)*100, 4),
            "time_factor": ms.get("time_factor", 1.0),
            "ac_impact_pct": round(ms.get("ac_impact", 0)*100, 4),
            "commission": round(commission, 2), "stamp": round(stamp, 2),
            "net": round(net, 2), "pnl": round(pnl, 2),
            "pnl_pct": pnl_pct,
            "order_type": ms.get("order_type_advice", {}).get("order_type", "market"),
            "reason": reason, "time": datetime.now().isoformat(),
            # ── 六问证据链 ──
            "reason_category": sell_cls["category"],   # ⑤错在哪(分类)
            "reason_label": sell_cls["label"],           # ⑤中文说明
            "holding_days": holding_days,                # 持仓天数
            "buy_context": buy_ctx,                      # 关联①-③决策证据
        }
        self.trades.append(trade)
        self._save()
        logger.info(f"[SIM SELL] {code} {shares}sh @{fill_price:.2f} PnL={pnl:+.0f} "
                    f"[{sell_cls['label']}]")
        return {"success": True, "trade": trade}

    def sync_positions(self) -> dict:
        """同步持仓(模拟账户直接返回)"""
        return dict(self.positions)

    def get_account_info(self) -> dict:
        return {
            "cash": round(self.cash, 2),
            "total_value": round(self.total_value, 2),
            "positions": len(self.positions),
            "trades_today": sum(1 for t in self.trades if str(datetime.now().date()) in t.get("time", "")),
        }

    def _save(self):
        DATA.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({
            "capital": self.capital, "cash": round(self.cash, 2),
            "positions": self.positions, "total": round(self.total_value, 2),
            "today_buys": self.today_buys, "date": str(datetime.now().date()),
        }, indent=2, ensure_ascii=False))
        TRADES.write_text(json.dumps(self.trades[-500:], indent=2, ensure_ascii=False))

    def _load(self):
        if STATE.exists():
            try:
                d = json.loads(STATE.read_text())
                self.cash = d.get("cash", self.capital)
                self.positions = d.get("positions", {})
                saved_date = d.get("date", "")
                today = str(datetime.now().date())
                if saved_date != today:
                    self.today_buys = {}
                else:
                    self.today_buys = d.get("today_buys", {})
            except Exception:
                pass


def trade_autopsy(trade: dict) -> dict:
    """六问交易诊断 — 对每笔已完成交易生成可诊断结论

    六问框架:
      ① 买什么   buy_what: 股票/策略/信号
      ② 何时买   buy_when: 市场状态/时间门/阶段
      ③ 买多少   buy_how_much: 仓位/Kelly
      ④ 结果     result: PnL/收益率/持仓天数
      ⑤ 错在哪   where_wrong: 归因分类(选股/择时/风控/执行)
      ⑥ 为什么对 why_right: 正收益归因(信号/策略/市场配合)

    Args:
        trade: sim_trades.json 中的卖单记录(含buy_context/reason_category)

    Returns:
        dict: 六问诊断结论
    """
    if not trade or trade.get("action") != "sell":
        return {"verdict": "仅诊断已完成(卖出)交易"}

    ctx = trade.get("buy_context", {}) or {}
    reason_cls = trade.get("reason_category", "manual_exit")
    pnl_pct = trade.get("pnl_pct", 0)
    pnl = trade.get("pnl", 0)
    code = trade.get("code", "?")

    # ④ 结果
    result = {
        "pnl": round(pnl, 2),
        "pnl_pct": pnl_pct,
        "holding_days": trade.get("holding_days", 0),
        "verdict": "盈利" if pnl > 0 else "亏损",
    }

    # ⑤ 错在哪 — 亏损归因
    where_wrong = None
    if pnl < 0:
        blame_map = {
            "risk_stop": "止损执行正确,但入场后趋势反向 → 选股/择时问题(①/②)",
            "risk_trail": "止盈回撤未保住利润 → 出场纪律问题(⑤)",
            "signal_exit": "信号反转退出 → 信号质量/择时问题(②)",
            "time_exit": "超时未启动 → 选股失败(①)",
            "take_profit": "止盈后继续上涨 → 止盈过早(⑤, 非错误)",
            "partial_exit": "减仓后继续跌 → 部分正确",
            "housekeeping": "幽灵持仓清理 → 系统状态问题",
            "manual_exit": "手动/其他 → 需人工复盘",
        }
        where_wrong = blame_map.get(reason_cls, "需人工复盘")

    # ⑥ 为什么对 — 盈利归因
    why_right = None
    if pnl > 0:
        credit_map = {
            "take_profit": "信号正确+止盈纪律执行到位",
            "risk_trail": "移动止盈锁住利润",
            "signal_exit": "信号反转及时退出,落袋为安",
            "risk_stop": "小亏止损控制风险(保护性正确)",
        }
        why_right = credit_map.get(reason_cls, "信号+策略综合正确")

    return {
        "code": code,
        "q1_buy_what": {
            "signal": ctx.get("signal", "?"),
            "strategy": ctx.get("strategy", "?"),
            "consensus": ctx.get("consensus", 0),
        },
        "q2_buy_when": {
            "regime": ctx.get("regime", "?"),
            "time_gate": ctx.get("time_gate", "?"),
            "phase": ctx.get("phase", "?"),
        },
        "q3_buy_how_much": {
            "kelly": ctx.get("kelly", 0),
            "shares": trade.get("shares", 0),
            "entry_price": trade.get("price", 0),
        },
        "q4_result": result,
        "q5_where_wrong": where_wrong,
        "q6_why_right": why_right,
    }


def build_trade_autopsies(trades: list) -> list:
    """批量生成六问诊断(供盘后复盘报告使用)"""
    return [trade_autopsy(t) for t in trades
            if isinstance(t, dict) and t.get("action") == "sell"]
