"""多因子Pipeline v1.0 — 对齐hikyuu trade_sys/multifactor
归一化(ZScore) → 行业中性化(组内去均值) → IC加权合成 → 截面排序

v14.43: 在MLFactorScorer(单股因子+静态IC权重)基础上增加跨股票截面处理:
- 截面归一化: 每个因子在当日全市场股票间ZScore(去极值)
- 行业中性化: 同行业股票组内去均值, 消除行业暴露 (对齐hikyuu industry_neutralize)
- 滚动IC加权: 用近期IC(因子-收益相关)动态调整权重 (对齐hikyuu ICMultiFactor)
"""
import logging
logger = logging.getLogger("aurora.multifactor")
import numpy as np


# ── 截面归一化 (对齐hikyuu NormZScore + quantile_trunc) ──
def cross_sectional_normalize(values: dict) -> dict:
    """截面ZScore归一化: {code: value} → {code: zscore}
    - 3倍标准差去极值 (winsorize)
    - NaN用0填充(中性)
    """
    if not values:
        return {}
    arr = np.array([v for v in values.values() if v is not None and not (isinstance(v, float) and np.isnan(v))],
                   dtype=np.float64)
    if len(arr) < 3:
        return {c: 0.0 for c in values}
    mean = np.nanmean(arr)
    std = np.nanstd(arr)
    if std < 1e-12:
        return {c: 0.0 for c in values}
    result = {}
    for code, v in values.items():
        if v is None or (isinstance(v, float) and np.isnan(v)):
            result[code] = 0.0
            continue
        z = (v - mean) / std
        result[code] = float(np.clip(z, -3.0, 3.0))  # 3σ去极值
    return result


# ── 行业中性化 (对齐hikyuu industry_neutralize: 组内去均值) ──
def industry_neutralize(zscores: dict, industry_map: dict) -> dict:
    """行业中性化: {code: zscore} × {code: industry} → {code: neutral_zscore}
    每个行业内减去该行业均值, 消除行业暴露(不因行业整体强势而加分)
    """
    if not zscores:
        return {}
    industry_values = {}
    for code, z in zscores.items():
        ind = industry_map.get(code, "unknown")
        industry_values.setdefault(ind, []).append(z)
    ind_mean = {ind: float(np.mean(vals)) for ind, vals in industry_values.items()}
    return {code: z - ind_mean.get(industry_map.get(code, "unknown"), 0.0)
            for code, z in zscores.items()}


# ── 滚动IC计算 (因子值 → 未来收益的截面相关, 对齐hikyuu IC指标) ──
def calc_ic(factor_values: dict, future_returns: dict) -> float:
    """计算单因子在截面的IC = corr(因子值, 未来收益)"""
    codes = [c for c in factor_values if c in future_returns
             and factor_values[c] is not None and future_returns[c] is not None]
    if len(codes) < 10:
        return 0.0
    fv = np.array([factor_values[c] for c in codes], dtype=np.float64)
    rv = np.array([future_returns[c] for c in codes], dtype=np.float64)
    if np.std(fv) < 1e-12 or np.std(rv) < 1e-12:
        return 0.0
    corr = np.corrcoef(fv, rv)[0, 1]
    return 0.0 if np.isnan(corr) else float(corr)


# ── 滚动IC加权合成 (对齐hikyuu ICMultiFactor: Σ(factor×|IC|)/Σ|IC|) ──
def ic_weighted_composite(factor_sets: list, ic_hist: dict) -> dict:
    """多因子IC加权合成: factor_sets=[{code: factor_value}, ...] 每个因子一组截面值
    ic_hist: {factor_name: 滚动平均IC}
    返回: {code: composite_score}
    权重 = IC / Σ|IC| — **带符号**: IC为负的因子(与收益反向)自动反向, 
    对齐hikyuu Σ(factor×IC)/Σ|IC| 的方向处理
    """
    if not factor_sets:
        return {}
    all_codes = set()
    for fs in factor_sets:
        all_codes.update(fs.keys())
    total_abs_ic = sum(abs(ic) for ic in ic_hist.values())
    if total_abs_ic < 1e-12:
        # IC全部无效时退化为等权
        weights = {name: 1.0 / len(factor_sets) for name in ic_hist} if ic_hist else {}
    else:
        # 带符号权重: w = IC/Σ|IC| (IC负 → 因子反向使用)
        weights = {name: ic / total_abs_ic for name, ic in ic_hist.items()}
    result = {}
    for code in all_codes:
        total = 0.0
        tw = 0.0
        for fs, (fname, w) in zip(factor_sets, weights.items()):
            v = fs.get(code)
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                total += v * w
                tw += abs(w)
        result[code] = total / tw if tw > 0 else 0.0
    return result


# ── 截面排序 (对齐hikyuu _buildIndex: 按日并行排序, 确定性比较器) ──
def rank_cross_section(composite: dict, top_n: int = 30) -> list:
    """截面排序取TopN: 返回[{code, score, rank}] 降序
    NaN沉底, 同分按代码字典序(确定性比较器)
    """
    items = [(code, score) for code, score in composite.items()
             if score is not None and not (isinstance(score, float) and np.isnan(score))]
    items.sort(key=lambda x: (-x[1], x[0]))  # 值降序, 代码升序(确定性)
    return [{"code": code, "score": round(score, 4), "rank": i + 1}
            for i, (code, score) in enumerate(items[:top_n])]


# ── 完整Pipeline入口 ──
def run_multifactor_pipeline(factor_sets: dict, industry_map: dict = None,
                             future_returns: dict = None, top_n: int = 30) -> dict:
    """执行多因子pipeline:
    factor_sets: {factor_name: {code: value}} — 每个因子的全市场截面值
    industry_map: {code: industry_name} — 行业中性化用(可空=跳过)
    future_returns: {code: future_return} — IC计算用(可空=用静态权重)

    返回: {top: [...], ic_summary: {...}, weights: {...}}
    """
    # 1. 截面归一化 (每因子ZScore)
    normalized = {}
    for fname, values in factor_sets.items():
        normalized[fname] = cross_sectional_normalize(values)
    # 2. 行业中性化 (每因子组内去均值)
    if industry_map:
        for fname in list(normalized):
            normalized[fname] = industry_neutralize(normalized[fname], industry_map)
    # 3. 滚动IC加权: 有未来收益数据时算IC, 否则用因子等权
    ic_hist = {}
    if future_returns:
        for fname, values in factor_sets.items():
            ic_hist[fname] = calc_ic(values, future_returns)
        logger.info(f"[MultiFactor] 计算{len(ic_hist)}个因子IC: "
                    f"{sorted(ic_hist.items(), key=lambda x: -abs(x[1]))[:3]}")
    else:
        for fname in factor_sets:
            ic_hist[fname] = 1.0  # 无未来数据时等权
    # 4. 合成
    composite = ic_weighted_composite(list(normalized.values()), ic_hist)
    # 5. 排序取TopN
    top = rank_cross_section(composite, top_n)
    return {
        "top": top,
        "ic_summary": {k: round(v, 4) for k, v in ic_hist.items()},
        "weights": {k: round(v / (sum(abs(x) for x in ic_hist.values()) or 1), 4)
                    for k, v in ic_hist.items()},
        "composite_all": composite,
    }
