"""综合评分 v4.0 — MACD背离+KDJ+BOLL+K线组合+涨停板+GARCH"""
import logging
logger = logging.getLogger("aurora.score")

import numpy as np

def composite_score(analysis, market_regime, market_score, mtf_scheme="A"):
    results = []
    # 信号权重表 (P3: 分层调参)
    _SIG_W = {
        "naked_supply_demand": 0.08, "chan_buy3": 0.15, "williams_r": 0.12,
        "williams_compression": 0.12, "123_rule": 0.10, "ma_breakout": 0.12,
        "momentum_breakout": 0.18, "wave_point": 0.12, "chan_buy1": 0.10,
        "chan_buy2": 0.12, "chan_sell3": 0.05, "naked_engulf": 0.08,
        "naked_insidebar": 0.08, "naked_pinbar": 0.10,
    }
    for a in analysis:
        if not a.get("signal"): continue
        kline_df = a.get("kline_df")
        base = _make_base(a, kline_df)
        best_strat = a.get("best_strategy", "").replace("+W", "").replace("+williams", "")
        sig_w = _SIG_W.get(best_strat, 0.15)
        strategy_score = a.get("best_score", 0) * sig_w
        mtf_score = 0
        mtf = {"score": 0, "resonance": "none"}
        a_mtf = a.get("mtf_score", {})
        if a_mtf and a_mtf.get("daily", 0) > 0:
            daily_w = 0.40; m30_w = 0.35; m5_w = 0.25
            mtf_val = a_mtf["daily"] * daily_w + a_mtf.get("m30", 50) * m30_w + a_mtf.get("m5", 0) * m5_w
            mtf_score = min(100, max(0, mtf_val)) * 0.15
        else:
            if mtf_scheme == "B":
                from strategies.mtf_resonance_v2 import check_mtf_resonance_v2
                try:
                    mtf = check_mtf_resonance_v2(kline_df, a.get("code")) if kline_df is not None else {"score": 0}
                except Exception:
                    mtf = {"score": 0}
            else:
                from strategies.mtf_resonance import check_mtf_resonance
                try:
                    mtf = check_mtf_resonance(kline_df, a.get("code")) if kline_df is not None else {"score": 0}
                except Exception:
                    mtf = {"score": 0}
            mtf_score = mtf.get("score", 0) * 0.15
        from strategies.indicator_system import indicator_composite_score
        try:
            ind_score = indicator_composite_score(kline_df) * 0.15 if kline_df is not None else 7.5
        except Exception:
            ind_score = 7.5
        vol_score = _calc_volume_score(kline_df, a)
        from strategies.naked_k import naked_k_score
        try:
            nk = naked_k_score(kline_df) if kline_df is not None else 35
        except Exception:
            nk = 35
        nk_score = nk * 0.10
        from strategies.chan_theory import chan_score
        try:
            chan_val = chan_score(kline_df) if kline_df is not None else 40
        except Exception:
            chan_val = 40
        chan_score_val = chan_val * 0.10
        liq_score = _calc_liquidity_score(a)
        market_adapt = 5 if market_regime.startswith("bull") else (3 if market_regime == "range" else 1)
        cs = a.get("can_slim", 50) * 0.05
        from strategies.kline_patterns import detect_eight_patterns
        eight_p = detect_eight_patterns(kline_df) if kline_df is not None else []
        pattern_bonus = sum(p.get("score", 0) * 0.05 for p in eight_p[:2])
        total = (strategy_score + mtf_score + ind_score + vol_score + nk_score + chan_score_val + liq_score + market_adapt + cs + pattern_bonus)
        from risk.garch_var import get_kelly_adjustment
        garch_adj = get_kelly_adjustment(kline_df) if kline_df is not None else 1.0
        total *= garch_adj
        from strategies.reflexivity import analyze_reflexivity
        ref = analyze_reflexivity(market_score, market_regime)
        reflex_adj = ref.get("reflexivity_score", 50) / 100
        total *= max(0.5, reflex_adj)
        base["composite"] = round(min(total, 100), 1)
        base["score"] = base["composite"]
        base["mtf"] = mtf; base["chan"] = round(chan_val, 0)
        base["nk_score"] = round(nk, 0); base["ind_score"] = round(ind_score/0.15, 0)
        base["patterns"] = [p["type"] for p in eight_p[:2]]
        results.append(base)
    results.sort(key=lambda x: x["composite"], reverse=True)
    logger.info(f"[Score v4.0] {len(results)} scored")
    return results

def _make_base(a, kline_df):
    return {"code": a.get("code"), "name": a.get("name"), "price": a.get("price", a.get("entry_price", 0)), "entry_price": a.get("entry_price", a.get("price", 0)), "stop_loss": a.get("stop_loss", a.get("price", 0) * 0.95), "take_profit": a.get("take_profit", a.get("price", 0) * 1.10), "signal": True, "best_strategy": a.get("best_strategy"), "kline_df": kline_df}

def _calc_volume_score(kline_df, _analysis):
    if kline_df is None or len(kline_df) < 5: return 5
    try:
        vol = kline_df["volume"].values; close = kline_df["close"].values
        vol_ratio = vol[-1] / (np.mean(vol[-20:]) or 1)
        price_up = close[-1] > close[-5] if len(close) >= 5 else True
        vol_up = vol[-1] > vol[-5] if len(vol) >= 5 else True
        score = 5
        if vol_ratio > 2.0: score += 3
        elif vol_ratio > 1.5: score += 2
        elif vol_ratio > 1.0: score += 1
        if price_up and vol_up: score += 2
        from strategies.kline_patterns import analyze_limit_up
        lu = analyze_limit_up(kline_df) if kline_df is not None else None
        if lu: score += {"A": 4, "B": 3, "C": 1, "D": -2}.get(lu["quality"], 0)
        return min(max(score, 0), 12)
    except Exception: return 5

def _calc_liquidity_score(analysis):
    mcap = analysis.get("mcap", 50); turnover = analysis.get("turnover", 1.0)
    score = 2
    if 50 <= mcap <= 800: score += 2
    elif mcap > 800: score += 0.5
    if turnover > 3: score += 1
    elif turnover > 1: score += 0.5
    return min(score, 5)

class MLFactorScorer:
    """多因子量价评分模型，使用IC权重合成0-100评分"""
    factor_names = [
        "ret_1d", "ret_3d", "ret_5d", "ret_10d", "ret_15d", "ret_20d", "ret_60d", "ret_120d",
        "ret_5d_neg", "ret_10d_neg", "bias_ratio_5", "bias_ratio_20",
        "vol_5d", "vol_10d", "vol_20d", "vol_60d", "atr_ratio",
        "daily_range_ratio", "high_low_5d", "high_low_20d", "price_position",
        "vol_ratio_1", "vol_ratio_5", "vol_change_1d", "vol_change_5d", "vol_std_20d", "amt_ratio",
        "vp_corr_5", "vp_corr_10", "vp_corr_20", "vwap_position",
        "price_ma5", "price_ma10", "price_ma20", "price_ma60", "price_ma120",
        "ma5_ma10", "ma5_ma20", "ma5_ma60",
        "ma10_ma20", "ma20_ma60", "ma20_ma120", "ma60_ma120",
        "upper_shadow_ratio", "lower_shadow_ratio", "body_ratio", "candle_position",
    ]
    def __init__(self):
        self.ic_weights = {
            "ret_1d": 0.050, "ret_3d": 0.045, "ret_5d": 0.040, "ret_10d": 0.035,
            "ret_15d": 0.025, "ret_20d": 0.020, "ret_60d": 0.010, "ret_120d": 0.005,
            "ret_5d_neg": 0.035, "ret_10d_neg": 0.025, "bias_ratio_5": 0.030, "bias_ratio_20": 0.020,
            "vol_5d": -0.025, "vol_10d": -0.020, "vol_20d": -0.015, "vol_60d": -0.010, "atr_ratio": -0.020,
            "daily_range_ratio": -0.010, "high_low_5d": -0.020, "high_low_20d": -0.015, "price_position": 0.025,
            "vol_ratio_1": 0.030, "vol_ratio_5": 0.020, "vol_change_1d": 0.025, "vol_change_5d": 0.015, "vol_std_20d": -0.015, "amt_ratio": 0.020,
            "vp_corr_5": 0.030, "vp_corr_10": 0.025, "vp_corr_20": 0.020, "vwap_position": 0.025,
            "price_ma5": 0.040, "price_ma10": 0.035, "price_ma20": 0.030, "price_ma60": 0.025, "price_ma120": 0.015,
            "ma5_ma10": 0.035, "ma5_ma20": 0.030, "ma5_ma60": 0.020,
            "ma10_ma20": 0.025, "ma20_ma60": 0.020, "ma20_ma120": 0.015, "ma60_ma120": 0.010,
            "upper_shadow_ratio": -0.015, "lower_shadow_ratio": 0.015, "body_ratio": 0.010, "candle_position": 0.010,
        }
    @staticmethod
    def _safe_div(a, b, fallback=1.0):
        if b is None or (isinstance(b, (int, float)) and b == 0): return fallback
        result = a / b
        if np.isnan(result) or np.isinf(result): return fallback
        return result
    @staticmethod
    def _ma(arr, window):
        if len(arr) < window: return np.full_like(arr, np.nan, dtype=np.float64)
        cum = np.cumsum(np.insert(arr, 0, 0))
        ma = (cum[window:] - cum[:-window]) / window
        return np.concatenate([np.full(window - 1, np.nan), ma])
    def extract_factors(self, kline_df):
        fallback = {name: np.nan for name in self.factor_names}
        if kline_df is None or len(kline_df) < 5: return fallback
        try:
            o = np.asarray(kline_df["open"].values, dtype=np.float64)
            h = np.asarray(kline_df["high"].values, dtype=np.float64)
            l = np.asarray(kline_df["low"].values, dtype=np.float64)
            c = np.asarray(kline_df["close"].values, dtype=np.float64)
            v = np.asarray(kline_df["volume"].values, dtype=np.float64)
            n = len(c)
            amt = np.asarray(kline_df["amount"].values, dtype=np.float64) if "amount" in kline_df.columns else v * (h + l + c) / 3
            f = {}
            periods = [1, 3, 5, 10, 15, 20, 60, 120]
            rnames = ["ret_1d", "ret_3d", "ret_5d", "ret_10d", "ret_15d", "ret_20d", "ret_60d", "ret_120d"]
            for p, name in zip(periods, rnames):
                f[name] = c[-1] / c[-p-1] - 1 if n > p else np.nan
            for period, name in [(5, "ret_5d_neg"), (10, "ret_10d_neg")]:
                if n > period:
                    dr = c[-(period+1):] / np.concatenate([[c[-(period+1)]], c[-(period+1):-1]]) - 1
                    f[name] = np.min(dr[1:]) if len(dr) > 1 else 0.0
                else: f[name] = np.nan
            ma5 = self._ma(c, 5); ma20 = self._ma(c, 20)
            f["bias_ratio_5"] = (c[-1] / ma5[-1] - 1) if not np.isnan(ma5[-1]) else np.nan
            f["bias_ratio_20"] = (c[-1] / ma20[-1] - 1) if not np.isnan(ma20[-1]) else np.nan
            rets = c[1:] / c[:-1] - 1
            for period, name in [(5, "vol_5d"), (10, "vol_10d"), (20, "vol_20d"), (60, "vol_60d")]:
                f[name] = np.std(rets[-period:]) if len(rets) >= period else np.nan
            if n >= 15:
                tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
                f["atr_ratio"] = self._safe_div(np.mean(tr[-14:]), c[-1])
            else: f["atr_ratio"] = np.nan
            f["daily_range_ratio"] = self._safe_div(h[-1] - l[-1], c[-1])
            for period, name in [(5, "high_low_5d"), (20, "high_low_20d")]:
                f[name] = self._safe_div(np.max(h[-period:]), np.min(l[-period:]), fallback=1.0) if n >= period else np.nan
            if n >= 20:
                low20 = np.min(l[-20:]); high20 = np.max(h[-20:])
                f["price_position"] = self._safe_div(c[-1] - low20, high20 - low20, fallback=0.5)
            else: f["price_position"] = np.nan
            vma5 = self._ma(v, 5); vma20 = self._ma(v, 20)
            f["vol_ratio_1"] = self._safe_div(v[-1], vma5[-1]) if not np.isnan(vma5[-1]) else np.nan
            f["vol_ratio_5"] = self._safe_div(v[-1], vma20[-1]) if not np.isnan(vma20[-1]) else np.nan
            f["vol_change_1d"] = self._safe_div(v[-1], v[-2], fallback=1.0) - 1 if n >= 2 else np.nan
            f["vol_change_5d"] = self._safe_div(v[-1], v[-6], fallback=1.0) - 1 if n >= 6 else np.nan
            if n >= 20:
                vs = v[-20:]; vm = np.mean(vs); vsd = np.std(vs)
                f["vol_std_20d"] = self._safe_div(vsd, vm, fallback=0.0)
            else: f["vol_std_20d"] = np.nan
            ama20 = self._ma(amt, 20)
            f["amt_ratio"] = self._safe_div(amt[-1], ama20[-1]) if not np.isnan(ama20[-1]) else np.nan
            for period, name in [(5, "vp_corr_5"), (10, "vp_corr_10"), (20, "vp_corr_20")]:
                if n >= period:
                    corr = np.corrcoef(v[-period:], c[-period:])
                    f[name] = corr[0, 1] if not np.isnan(corr[0, 1]) else 0.0
                else: f[name] = np.nan
            if n >= 1:
                vwap = np.sum(amt) / np.sum(v) if np.sum(v) > 0 else c[-1]
                f["vwap_position"] = self._safe_div(c[-1] - vwap, vwap, fallback=0.0)
            else: f["vwap_position"] = np.nan
            ma10 = self._ma(c, 10); ma60 = self._ma(c, 60); ma120 = self._ma(c, 120)
            f["price_ma5"] = self._safe_div(c[-1], ma5[-1]) if not np.isnan(ma5[-1]) else np.nan
            f["price_ma10"] = self._safe_div(c[-1], ma10[-1]) if not np.isnan(ma10[-1]) else np.nan
            f["price_ma20"] = self._safe_div(c[-1], ma20[-1]) if not np.isnan(ma20[-1]) else np.nan
            f["price_ma60"] = self._safe_div(c[-1], ma60[-1]) if not np.isnan(ma60[-1]) else np.nan
            f["price_ma120"] = self._safe_div(c[-1], ma120[-1]) if not np.isnan(ma120[-1]) else np.nan
            f["ma5_ma10"] = self._safe_div(ma5[-1], ma10[-1]) if not (np.isnan(ma5[-1]) or np.isnan(ma10[-1])) else np.nan
            f["ma5_ma20"] = self._safe_div(ma5[-1], ma20[-1]) if not (np.isnan(ma5[-1]) or np.isnan(ma20[-1])) else np.nan
            f["ma5_ma60"] = self._safe_div(ma5[-1], ma60[-1]) if not (np.isnan(ma5[-1]) or np.isnan(ma60[-1])) else np.nan
            f["ma10_ma20"] = self._safe_div(ma10[-1], ma20[-1]) if not (np.isnan(ma10[-1]) or np.isnan(ma20[-1])) else np.nan
            f["ma20_ma60"] = self._safe_div(ma20[-1], ma60[-1]) if not (np.isnan(ma20[-1]) or np.isnan(ma60[-1])) else np.nan
            f["ma20_ma120"] = self._safe_div(ma20[-1], ma120[-1]) if not (np.isnan(ma20[-1]) or np.isnan(ma120[-1])) else np.nan
            f["ma60_ma120"] = self._safe_div(ma60[-1], ma120[-1]) if not (np.isnan(ma60[-1]) or np.isnan(ma120[-1])) else np.nan
            hl = h[-1] - l[-1]
            if hl > 0:
                oc_max = max(o[-1], c[-1]); oc_min = min(o[-1], c[-1])
                f["upper_shadow_ratio"] = self._safe_div(h[-1] - oc_max, hl, fallback=0.0)
                f["lower_shadow_ratio"] = self._safe_div(oc_min - l[-1], hl, fallback=0.0)
                f["body_ratio"] = self._safe_div(abs(c[-1] - o[-1]), hl, fallback=0.0)
                f["candle_position"] = self._safe_div(c[-1] - l[-1], hl, fallback=0.5)
            else:
                f["upper_shadow_ratio"] = f["lower_shadow_ratio"] = f["body_ratio"] = 0.0
                f["candle_position"] = 0.5
            return f
        except Exception as e:
            logger.warning(f"[MLFactorScorer] extract_factors 异常: {e}")
            return fallback
    def predict_score(self, kline_df):
        try:
            factors = self.extract_factors(kline_df)
            vals = [v for v in factors.values() if not (isinstance(v, float) and np.isnan(v))]
            if len(vals) < 5: return 50.0
            ws = 0.0; tw = 0.0
            for name in self.factor_names:
                v = factors.get(name, np.nan)
                w = self.ic_weights.get(name, 0.0)
                if isinstance(v, (int, float)) and not np.isnan(v):
                    ws += np.clip(v, -5.0, 5.0) * w
                    tw += abs(w)
            if tw == 0: return 50.0
            return round(float(np.clip(50.0 + 25.0 * np.tanh((ws / tw) * 2.0), 0.0, 100.0)), 1)
        except Exception as e:
            logger.warning(f"[MLFactorScorer] predict_score 异常: {e}")
            return 50.0
    def get_top_factors(self, n=5):
        sf = sorted(self.ic_weights.items(), key=lambda x: abs(x[1]), reverse=True)
        return [{"name": name, "weight": round(w, 4), "direction": "positive" if w > 0 else "negative"} for name, w in sf[:n]]
    def auto_calibrate(self, trade_history):
        """从交易历史自动校准IC权重, trade_history: [{"score": float, "future_return": float, "factors": dict}, ...]"""
        if len(trade_history) < 20:
            logger.info("[MLCalibrate] 样本不足20，跳过校准")
            return {}
        ic_values = {}
        for name in self.factor_names:
            fv, rv = [], []
            for t in trade_history:
                factors = t.get("factors", {})
                if name in factors and not np.isnan(factors[name]):
                    fv.append(factors[name])
                    rv.append(t["future_return"])
            if len(fv) >= 20:
                corr = np.corrcoef(fv, rv)[0, 1]
                if not np.isnan(corr): ic_values[name] = corr
        for name, ic in ic_values.items():
            if name in self.ic_weights:
                self.ic_weights[name] = round(self.ic_weights[name] * 0.7 + ic * 0.3, 4)
        logger.info(f"[MLCalibrate] 已校准{len(ic_values)}个因子IC")
        return {"calibrated": len(ic_values), "top_factors": sorted(ic_values, key=ic_values.get, reverse=True)[:5]}

def calibrate_ml_weights(trade_history):
    """一键校准ML因子权重(外部接口)"""
    return MLFactorScorer().auto_calibrate(trade_history)

def ml_enhance_score(kline_df, base_score):
    scorer = MLFactorScorer()
    return round(base_score * 0.9 + scorer.predict_score(kline_df) * 0.1, 1)
