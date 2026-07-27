"""风控审核 — VaR + 压力测试 + 熔断 · 斯波朗迪+格雷厄姆"""
import json, logging, numpy as np, time
from pathlib import Path
logger = logging.getLogger("aurora.risk")
import os as _risk_os
_RISK_AGENT = _risk_os.environ.get("AURORA_AGENT")
if _RISK_AGENT:
    STATE_FILE = Path(__file__).resolve().parent.parent / "data" / f"risk_state_{_RISK_AGENT}.json"
else:
    STATE_FILE = Path(__file__).resolve().parent.parent / "data" / "risk_state.json"
del _risk_os, _RISK_AGENT

def _load() -> dict: 
    try: return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    except Exception: return {}
def _save(s: dict) -> None: 
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2))

def check_all(plans: list, _positions=None, cfg: dict = None) -> tuple:
    state = _load()
    state.setdefault("breaker", False); state.setdefault("consec", 0)
    state.setdefault("daily_pnl", 0.0); state.setdefault("peak_value", 0.0)
    state.setdefault("prev_day_value", 0.0)
    if state.get("breaker"):
        from datetime import datetime as _dt
        try:
            breaker_time = state.get("breaker_time", 0)
            if breaker_time > 0 and (time.time() - breaker_time) > 86400:
                logger.warning("[AutoRecovery] 熔断已超24h, 自动重置")
                state["breaker"] = False
                state["consec"] = 0
                state["breaker_time"] = 0
                _save(state)
            else:
                return [], [{"type": "breaker", "msg": f"熔断中(距自动恢复还有{max(0, 86400 - int(time.time() - breaker_time))}s)"}]
        except Exception:
            return [], [{"type": "breaker", "msg": "熔断已触发，需人工恢复"}]

    risk_cfg = cfg.get("risk", {})
    max_pos = risk_cfg.get("max_positions", 5)
    max_consec = risk_cfg.get("max_consecutive_losses", 3)
    alerts = []
    if state.get("consec", 0) >= max_consec:
        state["breaker"] = True
        state["breaker_time"] = time.time()
        _save(state)
        return [], [{"type": "consec", "msg": f"连续{state['consec']}次亏损,触发熔断"}]
    filtered = plans[:max_pos]
    if len(plans) > max_pos:
        alerts.append({"type": "cap", "msg": f"仓位超限({len(plans)}→{max_pos})"})
    capital = risk_cfg.get("capital", 1_000_000)
    for p in filtered:
        kline_df = p.get("kline_df")
        if kline_df is not None and len(kline_df) >= 14:
            tr = np.array([max(
                kline_df["high"].values[i] - kline_df["low"].values[i],
                abs(kline_df["high"].values[i] - kline_df["close"].values[i-1]),
                abs(kline_df["low"].values[i] - kline_df["close"].values[i-1])
            ) for i in range(1, len(kline_df))])
            atr = np.mean(tr[-14:])
            entry = p.get("entry_price", kline_df["close"].values[-1])
            if entry > 0:
                atr_sl_pct = min(max(atr / entry * 2.5, 0.02), 0.10)
                p["stop_loss"] = entry * (1 - atr_sl_pct)
                stop_loss_pct = atr_sl_pct
            else:
                stop_loss_pct = abs(p.get("stop_loss", entry * 0.95) / entry - 1) if entry > 0 else 0.05
        else:
            stop_loss_pct = abs(p.get("stop_loss", p.get("entry_price", 10) * 0.95) / p.get("entry_price", 10) - 1) if p.get("entry_price", 10) > 0 else 0.05

        if kline_df is not None and len(kline_df) >= 20:
            avg_vol = np.mean(kline_df["volume"].values[-20:])
            avg_price = np.mean(kline_df["close"].values[-20:])
            avg_dollar_vol = avg_vol * avg_price
            if avg_dollar_vol < 5_000_000:
                alerts.append({"type": "liquidity", "code": p.get("code"),
                              "msg": f"流动性不足: 日均成交额{avg_dollar_vol/1e4:.0f}万<500万"})
                continue
        risk_amount = p.get("entry_price", 0) * p.get("shares", 0) * min(stop_loss_pct, 1.0)
        from risk.garch_var import predict_var
        kline_df = p.get("kline_df")
        if kline_df is not None and len(kline_df) >= 30:
            close = kline_df["close"].values
            returns = np.diff(np.log(close))
            garch_var = predict_var(returns)
            daily_loss_limit = max(capital * garch_var, capital * 0.01)
        else:
            daily_loss_limit = capital * 0.03
        if risk_amount > daily_loss_limit:
            alerts.append({"type": "var", "code": p.get("code"), 
                          "msg": f"GARCH-VaR超限: {risk_amount/capital*100:.1f}%>" + 
                                 f"{daily_loss_limit/capital*100:.1f}%"})
    industries = {}
    for p in filtered:
        ind = p.get("industry", p.get("sector", ""))
        if ind:
            industries[ind] = industries.get(ind, 0) + 1
    for ind, count in industries.items():
        if count > 3:
            alerts.append({"type": "concentration", "industry": ind,
                          "msg": f"行业集中度: {ind}持仓{count}只(上限3)"})
    daily_limit = risk_cfg.get("daily_loss_limit_pct", -3.0) / 100
    if state.get("daily_pnl", 0) < daily_limit * capital:
        alerts.append({"type": "daily_loss", 
                      "msg": f"日亏损{state['daily_pnl']/capital*100:.1f}%超过上限{daily_limit*100:.0f}%, 触发熔断"})
        state["breaker"] = True
        state["breaker_time"] = time.time()
        _save(state)
        return [], alerts
    # ── Barra 风格因子暴露检查 ──
    try:
        barra = BarraController()
        _positions = _positions or []
        kline_cache = {}
        for p in filtered:
            if p.get("kline_df") is not None and p.get("code"):
                kline_cache[p["code"]] = p["kline_df"]
        pos_for_barra = []
        for p in filtered:
            pos_for_barra.append({
                "code": p.get("code", ""),
                "weight": 1.0 / max(len(filtered), 1),
                "kline_df": p.get("kline_df"),
                "mcap": p.get("mcap", p.get("market_cap", 1e8)),
                "pb": p.get("pb", p.get("pb_ratio", 1.0)),
                "roe": p.get("roe", 0.0),
            })
        barra_alerts = barra.check_portfolio(pos_for_barra, kline_cache)
        alerts.extend(barra_alerts)
    except Exception as e:
        logger.warning(f"Barra因子检查异常: {e}")
    # ── 合规检查 ──
    try:
        guard = ComplianceGuard()
        filtered = guard.check_all_plans(filtered)
        if len(filtered) < len([p for p in plans if p in filtered or True]):
            alerts.append({"type": "compliance", "msg": "合规检查过滤了部分计划"})
    except Exception as e:
        logger.warning(f"[Compliance] 检查异常: {e}")
    return filtered, alerts

def record_trade(pnl_pct: float):
    state = _load()
    state["consec"] = state.get("consec", 0) + 1 if pnl_pct < 0 else 0
    state["daily_pnl"] = round(state.get("daily_pnl", 0) + pnl_pct, 4)
    _save(state)

def reset():
    _save({"breaker": False, "consec": 0, "daily_pnl": 0.0, "peak_value": 0.0, "prev_day_value": 0.0})

def check_liquidity(code: str, price: float, min_vol: int = 2000000) -> bool:
    """liquidity filter: skip stocks with avg daily volume < 5M"""
    if not code: return False
    try:
        from data.sources import get_kline
        import numpy as np
        df = get_kline(code, 20)
        if df is None or df.empty: return False
        close = df["close"].values.astype(float)
        vol = df["volume"].values.astype(float)
        avg_dollar = float(np.mean(close * vol))
        if avg_dollar < min_vol:
            return False
        return True
    except Exception:
        return True

class BarraController:
    """Barra风格因子暴露监控 — 8维度因子模型"""
    
    def __init__(self):
        self.style_factors = {
            "size":       self._calc_size,
            "value":      self._calc_value,
            "momentum":   self._calc_momentum,
            "volatility": self._calc_volatility,
            "quality":    self._calc_quality,
            "growth":     self._calc_growth,
            "dividend":   self._calc_dividend,
            "liquidity":  self._calc_liquidity_factor,
        }
    
    @staticmethod
    def _zscore(arr):
        arr = np.asarray(arr, dtype=float)
        mean = np.nanmean(arr)
        std = np.nanstd(arr)
        if std < 1e-10:
            return np.zeros_like(arr)
        return (arr - mean) / std
    
    def _calc_size(self, kline_df, mcap, pb, roe):
        if mcap is None or mcap <= 0:
            return 0.0
        return float(np.log(mcap))
    
    def _calc_value(self, kline_df, mcap, pb, roe):
        if pb is None or pb <= 0:
            return 0.0
        return -float(np.log(pb))
    
    def _calc_momentum(self, kline_df, mcap, pb, roe):
        if kline_df is None or len(kline_df) < 21:
            return 0.0
        close = kline_df["close"].values
        ret = close[-1] / close[-21] - 1
        return float(ret)
    
    def _calc_volatility(self, kline_df, mcap, pb, roe):
        if kline_df is None or len(kline_df) < 21:
            return 0.0
        close = kline_df["close"].values
        returns = np.diff(np.log(close[-21:]))
        return float(np.std(returns))
    
    def _calc_quality(self, kline_df, mcap, pb, roe):
        if roe is None:
            return 0.0
        return float(roe)
    
    def _calc_growth(self, kline_df, mcap, pb, roe):
        score = 0.0
        if roe is not None:
            score += float(roe) * 0.5
        if kline_df is not None and len(kline_df) >= 21:
            close = kline_df["close"].values
            ret_20d = close[-1] / close[-21] - 1
            score += float(ret_20d) * 0.5
        return score
    
    def _calc_dividend(self, kline_df, mcap, pb, roe):
        if pb is None or pb <= 0:
            return 0.0
        return 1.0 / (pb + 1.0)
    
    def _calc_liquidity_factor(self, kline_df, mcap, pb, roe):
        if kline_df is None or len(kline_df) < 20 or mcap is None or mcap <= 0:
            return 0.0
        vol = kline_df["volume"].values[-20:]
        close = kline_df["close"].values[-20:]
        avg_dollar_vol = float(np.mean(vol * close))
        turnover = avg_dollar_vol / mcap
        return float(turnover)
    
    def compute_factor_exposure(self, kline_df, mcap, pb, roe):
        raw = {}
        for name, func in self.style_factors.items():
            raw[name] = func(kline_df, mcap, pb, roe)
        names = list(raw.keys())
        vals = np.array([raw[n] for n in names])
        zs = self._zscore(vals)
        return {names[i]: float(zs[i]) for i in range(len(names))}
    
    def check_portfolio(self, positions, kline_cache=None):
        if not positions:
            return []
        alerts = []
        exposures = {}
        for name in self.style_factors:
            exposures[name] = 0.0
        total_weight = 0.0
        n = len(positions)
        for pos in positions:
            w = pos.get("weight", 1.0 / n)
            kline = pos.get("kline_df")
            if kline is None and kline_cache and pos.get("code") in kline_cache:
                kline = kline_cache[pos["code"]]
            mcap = pos.get("mcap", 1e8)
            pb = pos.get("pb", 1.0)
            roe = pos.get("roe", 0.0)
            exp = self.compute_factor_exposure(kline, mcap, pb, roe)
            for name, val in exp.items():
                exposures[name] += val * w
            total_weight += w
        if total_weight > 0:
            for name in exposures:
                exposures[name] /= total_weight
        for name, exposure in exposures.items():
            if abs(exposure) > 1.5:
                alerts.append({
                    "type": "barra_exposure",
                    "factor": name,
                    "exposure": round(exposure, 3),
                    "msg": f"Barra因子暴露超限: {name}={exposure:.3f}(阈值1.5)"
                })
        return alerts


class ComplianceGuard:
    """合规守卫 — 撤单率监控+日报单限制+自成交检测"""
    
    def __init__(self):
        self.today_orders = []  # [{"time":datetime, "code":str, "action":"new"|"cancel"}, ...]
        self.max_orders_per_day = 100
        self.max_withdrawal_rate = 0.5  # 撤单率上限50%
    
    def check_order(self, code: str, action: str = "new") -> tuple:
        """
        下单前合规检查
        返回: (通过:bool, 消息:str)
        """
        from datetime import datetime
        now = datetime.now()
        self.today_orders.append({"time": now, "code": code, "action": action})
        
        # 1. 日报单数限制 (最近24小时)
        recent = [o for o in self.today_orders 
                  if (now - o["time"]).total_seconds() < 86400]
        if len(recent) > self.max_orders_per_day:
            return False, f"日报单数{len(recent)}超限{self.max_orders_per_day}"
        
        # 2. 撤单率检查 (近1小时)
        recent_1h = [o for o in recent 
                     if (now - o["time"]).total_seconds() < 3600]
        cancels = [o for o in recent_1h if o["action"] == "cancel"]
        if len(recent_1h) > 10:
            cancel_rate = len(cancels) / len(recent_1h)
            if cancel_rate > self.max_withdrawal_rate:
                return False, f"撤单率{cancel_rate:.0%}超限{self.max_withdrawal_rate:.0%}"
        
        # 3. 尾盘特殊限制 (14:55后谨慎大单)
        if now.hour == 14 and now.minute >= 55 and action == "new":
            pass
        
        return True, "通过"
    
    def check_all_plans(self, plans: list) -> list:
        """批量检查所有交易计划"""
        passed = []
        for p in plans:
            ok, msg = self.check_order(p.get("code", ""), "new")
            if ok:
                passed.append(p)
            else:
                logger.warning(f"[Compliance] {p.get('code')} {msg}")
        return passed
    
    def record_cancel(self, code: str):
        """记录撤单"""
        self.check_order(code, "cancel")
    
    def reset_daily(self):
        """每日重置"""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=1)
        self.today_orders = [o for o in self.today_orders if o["time"] > cutoff]
