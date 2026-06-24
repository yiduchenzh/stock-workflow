
"""风控审核 — VaR + 压力测试 + 熔断 · 斯波朗迪+格雷厄姆"""
import json, logging, numpy as np, time
from pathlib import Path
logger = logging.getLogger("aurora.risk")
STATE_FILE = Path(__file__).resolve().parent.parent / "data" / "risk_state.json"

def _load(): 
    try: return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    except Exception: return {}
def _save(s): 
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2))

def check_all(plans: list, _positions=None, cfg: dict = None) -> tuple:
    state = _load()
    state.setdefault("breaker", False); state.setdefault("consec", 0)
    state.setdefault("daily_pnl", 0.0); state.setdefault("peak_value", 0.0)
    state.setdefault("prev_day_value", 0.0)
    if state.get("breaker"):
        # 自动恢复: 如果熔断已触发超过24小时, 自动重置
        from datetime import datetime as _dt
        try:
            breaker_time = state.get("breaker_time", 0)
            if breaker_time > 0 and (time.time() - breaker_time) > 86400:
                logger.warning("[AutoRecovery] 熔断已超24h, 自动重置")
                state["breaker"] = False
                state["consec"] = 0
                state["breaker_time"] = 0
                _save(state)
                # 继续执行而非返回空
            else:
                return [], [{"type": "breaker", "msg": f"熔断中(距自动恢复还有{max(0, 86400 - int(time.time() - breaker_time))}s)"}]
        except Exception:
            return [], [{"type": "breaker", "msg": "熔断已触发，需人工恢复"}]

    risk_cfg = cfg.get("risk", {})
    max_pos = risk_cfg.get("max_positions", 5)
    max_consec = risk_cfg.get("max_consecutive_losses", 3)
    alerts = []
    # 连续亏损
    if state.get("consec", 0) >= max_consec:
        state["breaker"] = True
        state["breaker_time"] = time.time()
        _save(state)
        return [], [{"type": "consec", "msg": f"连续{state['consec']}次亏损,触发熔断"}]
    # 仓位上限
    filtered = plans[:max_pos]
    if len(plans) > max_pos:
        alerts.append({"type": "cap", "msg": f"仓位超限({len(plans)}→{max_pos})"})
    # ATR动态止损 + GARCH-VaR: 单笔风险不超过总资本3%
    capital = risk_cfg.get("capital", 1_000_000)
    for p in filtered:
        # ATR动态止损: 用ATR替代固定百分比
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
                atr_sl_pct = min(max(atr / entry * 2.5, 0.02), 0.10)  # 2.5倍ATR, 2%-10%
                p["stop_loss"] = entry * (1 - atr_sl_pct)
                stop_loss_pct = atr_sl_pct
            else:
                stop_loss_pct = abs(p.get("stop_loss", entry * 0.95) / entry - 1) if entry > 0 else 0.05
        else:
            stop_loss_pct = abs(p.get("stop_loss", p.get("entry_price", 10) * 0.95) / p.get("entry_price", 10) - 1) if p.get("entry_price", 10) > 0 else 0.05

        # 流动性检查: 日均成交量<500万时告警
        if kline_df is not None and len(kline_df) >= 20:
            avg_vol = np.mean(kline_df["volume"].values[-20:])
            avg_price = np.mean(kline_df["close"].values[-20:])
            avg_dollar_vol = avg_vol * avg_price
            if avg_dollar_vol < 5_000_000:  # 日均成交额<500万
                alerts.append({"type": "liquidity", "code": p.get("code"),
                              "msg": f"流动性不足: 日均成交额{avg_dollar_vol/1e4:.0f}万<500万"})
                continue
        risk_amount = p.get("entry_price", 0) * p.get("shares", 0) * min(stop_loss_pct, 1.0)
        # GARCH-VaR: 如果可用，用动态VaR替代
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
    # 日亏损限额检查 (Quant审计修复: 之前定义了但从未执行)
    daily_limit = risk_cfg.get("daily_loss_limit_pct", -3.0) / 100
    if state.get("daily_pnl", 0) < daily_limit * capital:
        alerts.append({"type": "daily_loss", 
                      "msg": f"日亏损{state['daily_pnl']/capital*100:.1f}%超过上限{daily_limit*100:.0f}%, 触发熔断"})
        state["breaker"] = True
        state["breaker_time"] = time.time()
        _save(state)
        return [], alerts
    return filtered, alerts

def record_trade(pnl_pct: float):
    state = _load()
    state["consec"] = state.get("consec", 0) + 1 if pnl_pct < 0 else 0
    state["daily_pnl"] = round(state.get("daily_pnl", 0) + pnl_pct, 4)
    _save(state)

def reset():
    _save({"breaker": False, "consec": 0, "daily_pnl": 0.0, "peak_value": 0.0, "prev_day_value": 0.0})
