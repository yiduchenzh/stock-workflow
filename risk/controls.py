"""风控审核 — VaR + 压力测试 + 熔断 · 斯波朗迪+格雷厄姆"""
import json, logging, numpy as np, time, os
from pathlib import Path
logger = logging.getLogger("aurora.risk")


# ═══ P2b (2026-09-28) 熔断/净值口径统一 — 路径动态化 + 隔离 ═══
# 2026-09-27 事故(实测): tests/test_risk.py 调 record_trade()/check_all() → 直接写
#   生产 data/risk_state.json, 内容 = 测试常量
#   {"breaker": true, "consec": 3, "daily_pnl": -0.1, "peak_value": 0.0, "prev_day_value": 0.0}
#   (daily_pnl=-0.1 = -0.05+-0.03+-0.02; breaker_time = 测试运行时刻 18:08:11)
#   → 生产熔断为 True + peak_value=0.0 → 引擎 step_risk 清空全部开仓计划。
# 修法: ①路径改为动态函数(与 risk/budget.py 同款), 支持 AURORA_AGENT(6Agent 隔离)与
#        AURORA_RISK_STATE(测试/验证脚本显式隔离, 见 tests/conftest.py)
#      ②daily_pnl/consec 统一为「当日」口径(跨日归零)
#      ③peak_value/prev_day_value 必须来自真实净值序列(_sane_value 限幅 [0.01,5]×capital)
def _state_file() -> Path:
    _override = os.environ.get("AURORA_RISK_STATE")
    if _override:
        return Path(_override)
    _agent = os.environ.get("AURORA_AGENT")
    _base = Path(__file__).resolve().parent.parent / "data"
    return _base / (f"risk_state_{_agent}.json" if _agent else "risk_state.json")


STATE_FILE = _state_file()          # 兼容外部直接引用(单引擎场景)


def _load() -> dict:
    # v14.50 P2-B: 显式utf-8(原默认GBK读utf-8文件可能崩)
    try:
        p = _state_file()
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        return {}


def _save(s: dict) -> None:
    p = _state_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")


def _cap_of(cfg: dict = None) -> float:
    try:
        return float(((cfg or {}).get("risk", {}) or {}).get("capital", 1_000_000) or 1_000_000)
    except Exception:
        return 1_000_000


def _sane_value(v, capital: float):
    """净值合理性: [0.01, 5]×capital (与 RiskBudget._sane_value 完全同口径)"""
    try:
        v = float(v)
    except Exception:
        return None
    if v <= 0 or v < capital * 0.01 or v > capital * 5.0:
        return None
    return v


def net_value_series(capital: float = 1_000_000) -> list:
    """真实净值序列 — 主源 data/pnl_tracker.json 的 daily[].total(升序);
    次源 data/risk_budget.json 的 peak_value/current_value。全部经 _sane_value 限幅,
    自动剔除污染点(如 2026-08-07 注入的 20,529,521.75)。"""
    base = Path(__file__).resolve().parent.parent / "data"
    out = []
    try:
        p = base / "pnl_tracker.json"
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            for row in (d.get("daily") or []):
                v = _sane_value(row.get("total"), capital)
                if v is not None:
                    out.append((str(row.get("date") or ""), v))
    except Exception as e:
        logger.debug(f"[Risk] net_value_series pnl_tracker: {e}")
    if len(out) < 2:
        try:
            p = base / "risk_budget.json"
            if p.exists():
                d = json.loads(p.read_text(encoding="utf-8"))
                for k in ("peak_value", "current_value"):
                    v = _sane_value(d.get(k), capital)
                    if v is not None:
                        out.append(("", v))
        except Exception as e:
            logger.debug(f"[Risk] net_value_series budget: {e}")
    # 保持**时间顺序**(升序 = 从最早到最新); 峰值由 sync_net_value 用 max() 计算,
    # 勿在此处排序 —— 否则 vals[-1] 会变成"历史最高净值"而不是"最新净值"。
    return out


def sync_net_value(capital: float = None, current_value: float = None, persist: bool = True) -> dict:
    """P2b: 用**真实净值序列**刷新 risk_state 的 peak_value/prev_day_value/current_value。

    返回 {peak_value, prev_day_value, current_value, drawdown_pct, source, n_sample}
    """
    state = _load()
    cap = float(capital or state.get("capital") or 1_000_000)
    series = net_value_series(cap)
    vals = [v for _, v in series]
    cur = _sane_value(current_value, cap)
    if cur is None:
        cur = vals[-1] if vals else cap
    peak = max(vals + [cur, cap])
    # prev_day_value = 序列中最近一次记录日的净值(时间顺序的最后一个样本) = 当日基准
    prev = vals[-1] if vals else cur
    state.update({
        "capital": cap,
        "peak_value": round(peak, 2),
        "prev_day_value": round(prev, 2),
        "current_value": round(cur, 2),
        "drawdown_pct": round(max(-1.0, min(0.0, (cur - peak) / max(peak, 1))), 6),
        "net_value_source": "pnl_tracker.daily+risk_budget(经 _sane_value 限幅)",
        "net_value_n_sample": len(vals),
        "net_value_synced": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    if persist:
        _save(state)
    return {k: state[k] for k in ("peak_value", "prev_day_value", "current_value",
                                  "drawdown_pct", "net_value_source", "net_value_n_sample")}

def check_all(plans: list, _positions=None, cfg: dict = None) -> tuple:
    state = _load()
    state.setdefault("breaker", False); state.setdefault("consec", 0)
    state.setdefault("daily_pnl", 0.0); state.setdefault("peak_value", 0.0)
    state.setdefault("prev_day_value", 0.0)
    # ── P2b 口径统一 ──
    #  ①consec/daily_pnl 是「当日」口径: 跨日自动归零(原实现跨日累加 → 越累越易熔断)
    #  ②peak_value/prev_day_value 必须是真实净值: 为 0/越界(测试污染) → 现场同步
    _cap = _cap_of(cfg)
    _today = time.strftime("%Y-%m-%d")
    if state.get("daily_pnl_date") != _today:
        logger.info(f"[Risk] 跨日重置 当日熔断计数: consec {state.get('consec', 0)}→0, "
                    f"daily_pnl {state.get('daily_pnl', 0)}→0")
        state["daily_pnl_date"] = _today
        state["consec_date"] = _today
        state["daily_pnl"] = 0.0
        state["daily_pnl_pct"] = 0.0
        state["consec"] = 0
        _save(state)
    if _sane_value(state.get("peak_value"), _cap) is None or \
            _sane_value(state.get("prev_day_value"), _cap) is None:
        _nv = sync_net_value(capital=_cap, persist=True)
        logger.info(f"[Risk] 净值口径修复: peak_value/prev_day_value ← 真实净值序列 "
                    f"(peak={_nv['peak_value']}, prev_day={_nv['prev_day_value']}, n={_nv['net_value_n_sample']})")
        state = _load()
    # ──────── 熔断开关显式化 (2026-09-28 操作清单#1) ────────
    #   问题: 熔断状态只有"隐式"语义(超24h自愈 / 否则需人工恢复) →
    #         ① 陈旧熔断(如 09-25 前测试写坏的 breaker=true+peak=0)会静默冻结系统
    #         ② 想主动冻结时无处可设。现由 cfg.risk.breaker_override 三态显式控制:
    #         auto(默认)=现状逻辑 / freeze=强制熔断禁开仓 / release=强制解除(仅告警)
    _ov = str(((cfg or {}).get("risk") or {}).get("breaker_override", "auto") or "auto").strip().lower()
    if _ov not in ("auto", "freeze", "release"):
        _ov = "auto"
    if state.get("breaker_override") != _ov:
        state["breaker_override"] = _ov
        _save(state)
    if _ov == "freeze":
        return [], [{"type": "breaker", "msg": "熔断开关=freeze(显式冻结; 改回 auto/release 才恢复开仓)"}]
    if _ov == "release" and state.get("breaker"):
        logger.warning("[BreakerOverride] 熔断开关=release → 显式解除熔断状态")
        state["breaker"] = False
        state["consec"] = 0
        state["breaker_time"] = 0
        _save(state)
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
            # v14.49: 与 check_liquidity 统一口径(手→股 换算), 阈值 2000万/日
            _m = liquidity_metrics(p.get("code", ""), kline_df=kline_df)
            avg_dollar_vol = _m["avg_turnover"] or 0.0
            if avg_dollar_vol < MIN_DAILY_TURNOVER_YUAN:
                alerts.append({"type": "liquidity", "code": p.get("code"),
                              "msg": f"流动性不足: 日均成交额{avg_dollar_vol/1e4:.0f}万"
                                     f"<{MIN_DAILY_TURNOVER_YUAN/1e4:.0f}万"})
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
    # P2b: 日亏损口径统一 —— 用 daily_pnl_pct(百分数, 与画像 daily_loss_limit_pct 同单位)判定,
    #   同时把 daily_pnl 归一到「金额」口径, 消除「pct 写 / 金额 读」的单位混用。
    daily_limit_pct = float(risk_cfg.get("daily_loss_limit_pct", -3.0) or -3.0)
    _dpp = state.get("daily_pnl_pct")
    if _dpp is None:
        _dpp = state.get("daily_pnl", 0.0)            # 旧文件: 该字段按百分数记录
    try:
        _dpp = float(_dpp or 0.0)
    except Exception:
        _dpp = 0.0
    state["daily_pnl_pct"] = round(_dpp, 4)
    state["daily_pnl"] = round(_dpp / 100.0 * capital, 2)
    if _dpp < daily_limit_pct:
        alerts.append({"type": "daily_loss",
                      "msg": f"日亏损{_dpp:.1f}%超过上限{daily_limit_pct:.0f}%, 触发熔断"})
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

def record_trade(pnl_pct: float, capital: float = None):
    """记录一笔**已平仓**交易结果 (P2b 口径统一)

    pnl_pct 单位 = **百分数**(-0.49 表示 -0.49%), 与画像 daily_loss_limit_pct 同单位。
    写入: consec(当日连续亏损笔数) / daily_pnl_pct(当日累计, 百分数) /
          daily_pnl(当日累计, 金额 = pct/100×capital, 与 check_all 的比较口径一致)
    跨日自动归零。生产唯一调用点: executor/sim_account.py 整仓卖出后(与
    strategies.evolution.record_trade_result 同一处, 保证两侧口径同源)。
    """
    state = _load()
    today = time.strftime("%Y-%m-%d")
    cap = float(capital or state.get("capital") or 1_000_000)
    if state.get("daily_pnl_date") != today:
        state["daily_pnl_date"] = today
        state["consec_date"] = today
        state["daily_pnl"] = 0.0
        state["daily_pnl_pct"] = 0.0
        state["consec"] = 0
    try:
        p = float(pnl_pct)
    except Exception:
        p = 0.0
    state["consec"] = (state.get("consec", 0) + 1) if p < 0 else 0
    state["daily_pnl_pct"] = round(float(state.get("daily_pnl_pct", 0.0)) + p, 4)
    state["daily_pnl"] = round(state["daily_pnl_pct"] / 100.0 * cap, 2)
    state["capital"] = cap
    _save(state)


def reset(capital: float = None, sync_value: bool = False):
    """清空熔断状态

    P2b: peak_value/prev_day_value 不再写 0(0 = 无效口径, 曾被测试写成 0 后
    污染生产文件); sync_value=True 时立即用真实净值序列回填。
    """
    _save({"breaker": False, "consec": 0, "daily_pnl": 0.0, "daily_pnl_pct": 0.0,
           "daily_pnl_date": time.strftime("%Y-%m-%d"), "consec_date": time.strftime("%Y-%m-%d"),
           "breaker_time": 0})
    if sync_value:
        sync_net_value(capital=capital, persist=True)

# ── 流动性门槛 (v14.49 修正 2026-09-11) ────────────────────────────────
# 原实现: avg_dollar = mean(close × volume), 但 get_kline 日K 的 volume 单位是【手】
#   → 量值 = 真实成交额 ÷ 100, 而阈值写 2_000_000 → 实际要求"日均成交额 ≥ 2亿元",
#     比函数 docstring 声明的"5M股"严约 100 倍。
# 实证(2026-09-11 周复盘): 本周 [Liq] 触发 16 次砍掉 21/59 个开仓计划(36%),
#   例 003013 地铁设计(当日成交 3.47亿 / 20日均 1.92亿, kelly=0.25 wr=100% 的最佳候选)被判低流动;
#   002531 天顺风能(20日均 2.58亿) 通过。
# 修正: 显式 SHARES_PER_LOT 换算成【股】再乘价格 = 日均成交额(元); 阈值取 2000万/日
#   (≈ 2万手@10元, 与 docstring "5M股" 同量级: 500万股 × 4元 ≈ 2000万)。
SHARES_PER_LOT = 100          # A股 1手 = 100股 (日K volume 单位=手)
MIN_DAILY_TURNOVER_YUAN = 20_000_000   # 日均成交额下限 2000万元
MIN_DAILY_VOL_SHARES = 5_000_000       # 日均成交量下限 500万股 (docstring 原始意图)


def liquidity_metrics(code: str, days: int = 20, kline_df=None) -> dict:
    """返回 {avg_turnover(元), avg_vol_shares(股), bars} — 供过滤与日志共用(单一口径)"""
    import numpy as np
    if kline_df is None:
        from data.sources import get_kline
        kline_df = get_kline(code, days)
    if kline_df is None or getattr(kline_df, "empty", True):
        return {"avg_turnover": None, "avg_vol_shares": None, "bars": 0}
    close = kline_df["close"].values.astype(float)
    vol = kline_df["volume"].values.astype(float)
    vol_shares = vol * SHARES_PER_LOT               # 手 → 股 (关键修正)
    return {"avg_turnover": float(np.mean(close * vol_shares)),
            "avg_vol_shares": float(np.mean(vol_shares)), "bars": int(len(kline_df))}


def check_liquidity(code: str, price: float = 0,
                    min_turnover: float = MIN_DAILY_TURNOVER_YUAN,
                    min_vol_shares: float = MIN_DAILY_VOL_SHARES,
                    verbose: bool = False) -> bool:
    """流动性过滤: 日均成交额(元) ≥ min_turnover 或 日均成交量(股) ≥ min_vol_shares.

    v14.49: 单位修正(手→股), 阈值 2000万/日; 被拦截时记录实测值(原实现只记条数, 无法诊断)。
    """
    if not code:
        return False
    try:
        m = liquidity_metrics(code)
        if m["avg_turnover"] is None:
            return False
        ok = m["avg_turnover"] >= min_turnover or m["avg_vol_shares"] >= min_vol_shares
        if not ok and verbose:
            logger.info(f"[Liq] {code} 低流动: 日均成交额 {m['avg_turnover']/1e4:.0f}万 "
                        f"(<{min_turnover/1e4:.0f}万) 日均量 {m['avg_vol_shares']/1e4:.0f}万股")
        return ok
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
