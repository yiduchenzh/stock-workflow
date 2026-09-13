# -*- coding: utf-8 -*-
"""
screener.py — 涨停打板选股（文字①蒸馏：涨停前一日量能三分类）

核心逻辑（摘自用户提供的交易体系，规则量化化）：
  主力不会毫无铺垫直接拉涨停，涨停前一天的量能变化是主力真实意图的体现。
  涨停前一日成交量只会归为三类固定走势：

  1. 缩量地量（洗盘完毕，连板潜力最高）
     - 量能 ≤ 5日均量×0.6（缩减40%以上）
     - 振幅 ≤ 3%，小阴小阳十字星
     - 站稳 5/10 日均线
     - 位置：低位/上涨中途（高位缩量 = 无人接盘 = 下跌前兆，必须排除）

  2. 温和放量（悄悄吸筹，安全度最高）
     - 量能 = 5日均量×(1.3~1.8)（放量30%-80%，不翻倍）
     - 收阳，实体中等，无长上影（长上影放量 = 借涨出货，排除）
     - 涨幅 1%-4%
     - 分时“跌少涨多”（日K近似：缩量下跌日少）
     - 位置：低位启动/上涨初期，均线多头

  3. 翻倍爆量（试盘洗盘，短线博弈）
     - 量能 ≥ 5日均量×2.0
     - 振幅 ≥ 6%，冲高回落（长上影）
     - 收盘站稳 5 日均线
     - 逼近前期高点/箱体上沿（试抛压）
     - 位置：低位首板试盘优先，累计涨幅 >40% 后爆量长上影 = 出货，排除
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple

from concurrent.futures import ThreadPoolExecutor, as_completed

from datafeed import attach_prev_close, fetch_daily_kline, is_limit_up, limit_pct


# ------------------------------------------------------------------ 基础 ----

def _ma(values: List[float], n: int, idx: int) -> Optional[float]:
    """第 idx 根往前 n 根收盘均价（不含 idx）。"""
    if idx < n:
        return None
    seg = values[idx - n:idx]
    return sum(seg) / n


def classify_prev_volume(rows: List[Dict[str, Any]], idx: int) -> Dict[str, Any]:
    """判断第 idx 根K线（作为"涨停前一日"）的量能形态。

    返回 {type, name, detail}，type ∈ 缩量地量/温和放量/翻倍爆量/无形态。
    量比基准 = 前5日均量（不含当日），避免自我引用。
    """
    need = 25  # 至少需要 25 根前置数据
    if idx < need:
        return {"type": "无形态", "name": "数据不足", "detail": {}}

    r = rows[idx]
    pc = r.get("prev_close", r["open"])
    if pc <= 0:
        return {"type": "无形态", "name": "数据异常", "detail": {}}

    vols = [x["volume"] for x in rows[idx - 6:idx]]
    if not vols or mean(vols) <= 0:
        return {"type": "无形态", "name": "数据异常", "detail": {}}
    ma5_vol = mean(vols)
    vol_ratio = r["volume"] / ma5_vol

    closes = [x["close"] for x in rows[:idx + 1]]
    ma5 = _ma(closes, 5, idx)
    ma10 = _ma(closes, 10, idx)
    ma20 = _ma(closes, 20, idx)

    amplitude = (r["high"] - r["low"]) / pc * 100.0          # 振幅%
    chg = (r["close"] - pc) / pc * 100.0                     # 涨幅%
    body = abs(r["close"] - r["open"]) / pc * 100.0          # 实体%
    upper_shadow = (r["high"] - max(r["open"], r["close"])) / pc * 100.0  # 上影%
    lower_shadow = (min(r["open"], r["close"]) - r["low"]) / pc * 100.0   # 下影%

    pos = position_of(rows, idx)

    # ⭐ 2026-08-20 P2/P3 A/B 实证(2年1884只全市场 92万逐日样本): "尾盘企稳"是独立于量能形态的加分维度——
    #   守5/10日线 × 收盘位置≥0.7 × 上影比例≤0.3 → 次日涨停率 3.73% (全市场1.58%的2.36倍, 分年度稳健)
    #   放量收高(vol_ratio≥1.3+收阳+收盘位置≥0.8) → 16.75% (6.2倍); 放量×企稳 → 23.85% (最强)
    #   文章"缩量洗盘"宣称被证伪(缩量反而拖累: 2.87% < 不限量3.73%)——只加尾盘维度, 不动已验证形态。
    _hl = (r["high"] - r["low"]) or 1e-9
    close_pos = (r["close"] - r["low"]) / _hl          # 收盘位置(高=尾盘强/收在高位)
    tail_up_shadow = (r["high"] - r["close"]) / _hl    # 上影比例(低=尾盘不跳水)
    tail_stable = close_pos >= 0.7 and tail_up_shadow <= 0.3

    detail = {
        "vol_ratio": round(vol_ratio, 2),
        "amplitude": round(amplitude, 2),
        "chg": round(chg, 2),
        "body": round(body, 2),
        "upper_shadow": round(upper_shadow, 2),
        "lower_shadow": round(lower_shadow, 2),
        "close_pos": round(close_pos, 2), "tail_up_shadow": round(tail_up_shadow, 2),
        "tail_stable": tail_stable,
        "ma5": round(ma5, 2) if ma5 else None,
        "ma10": round(ma10, 2) if ma10 else None,
        "ma20": round(ma20, 2) if ma20 else None,
        "position": pos["name"],
        "pos_detail": pos,
    }

    # 位置一票否决：高位一律不算有效形态（文字①核心避坑：脱离位置谈量能全失效）
    if pos["name"] == "高位":
        return {"type": "无形态", "name": "高位排除", "detail": detail}

    # 一字板排除（文字②误区6：一字涨停/跌停流动性枯竭，昨收价信号失真）
    if amplitude < 0.5 and abs(chg) >= 8.0:
        return {"type": "无形态", "name": "一字板·信号失真", "detail": detail}

    # ---- 形态1：缩量地量 ----
    if vol_ratio <= 0.6 and amplitude <= 3.0 and body <= 2.0:
        # 站稳 5/10 日线（close 不低于其 99% 容差）
        if ma5 is not None and ma10 is not None and \
           r["close"] >= ma5 * 0.99 and r["close"] >= ma10 * 0.99:
            return {"type": "缩量地量", "name": "缩量地量·浮筹清洗完毕", "detail": detail}

    # ---- 形态2：温和放量 ----
    if 1.3 <= vol_ratio <= 1.8:
        ok_yang = r["close"] > r["open"]                       # 收阳
        ok_chg = 1.0 <= chg <= 4.0                           # 涨幅1%-4%
        ok_shadow = upper_shadow <= 1.0                       # 无长上影（排除出货）
        ok_ma = ma5 is not None and ma20 is not None and \
            ma5 > ma10 > ma20 and r["close"] >= ma5 * 0.99    # 均线多头
        if ok_yang and ok_chg and ok_shadow and ok_ma:
            return {"type": "温和放量", "name": "温和放量·主力悄悄吸筹", "detail": detail}

    # ---- 形态3：翻倍爆量 ----
    if vol_ratio >= 2.0 and amplitude >= 6.0:
        ok_pressure = pos.get("dist_to_high60", 1.0) <= 0.12  # 逼近60日高点（≤12%）
        ok_hold = ma5 is not None and r["close"] >= ma5 * 0.99  # 收盘站稳5日线
        ok_shadow = upper_shadow >= 2.0 or (r["high"] - r["close"]) / pc * 100.0 >= 1.5  # 冲高回落
        if ok_pressure and ok_hold and ok_shadow:
            return {"type": "翻倍爆量", "name": "翻倍爆量·主力试盘洗盘", "detail": detail}

    return {"type": "无形态", "name": "无主流形态", "detail": detail}


def position_of(rows: List[Dict[str, Any]], idx: int) -> Dict[str, Any]:
    """股价位置判断（文字①核心：位置决定信号性质）。

    - 高位：距60日高点回撤 <5%，或 20日涨幅 >30%（连续大涨后）
    - 低位：距60日高点回撤 ≥15% 且 20日涨幅 <10%
    - 上涨中途：其他
    """
    if idx < 25:
        return {"name": "低位", "dist_to_high60": 0.5, "chg20": 0.0, "note": "数据不足默认低位"}
    closes = [x["close"] for x in rows[:idx + 1]]
    highs = [x["high"] for x in rows[:idx + 1]]
    high60 = max(highs[-60:])
    close = closes[-1]
    dist = (high60 - close) / high60 if high60 > 0 else 0.0
    chg20 = (close - closes[-21]) / closes[-21] * 100.0 if len(closes) >= 21 and closes[-21] > 0 else 0.0

    if dist < 0.05 or chg20 > 30:
        return {"name": "高位", "dist_to_high60": round(dist, 3), "chg20": round(chg20, 1),
                "note": "高位：距高点<5%或20日涨幅>30%（缩量=无人接盘，爆量=出货）"}
    if dist >= 0.15 and chg20 < 10:
        return {"name": "低位", "dist_to_high60": round(dist, 3), "chg20": round(chg20, 1),
                "note": "低位：距高点回撤≥15%且20日涨幅<10%"}
    return {"name": "上涨中途", "dist_to_high60": round(dist, 3), "chg20": round(chg20, 1),
            "note": "上涨中途：趋势进行中"}


# ------------------------------------------------------------------ 评分 ----

def score_signal(rows: List[Dict[str, Any]], idx: int) -> Dict[str, Any]:
    """对第 idx 根K线（通常是最后一根=今日）做"明日涨停潜力"评分。"""
    cls = classify_prev_volume(rows, idx)
    typ = cls["type"]
    det = cls["detail"]
    base = {"缩量地量": 45, "温和放量": 40, "翻倍爆量": 35}.get(typ, 0)
    if typ == "无形态":
        return {
            "type": "无形态", "level": "D", "score": 0,
            "position": det.get("position", "—"),
            "logic": "今日量能不属于三类主流形态，明日涨停概率低，放弃",
            "detail": det,
        }

    pos_name = det.get("position", "低位")
    pos_score = {"低位": 25, "上涨中途": 15, "高位": -100}.get(pos_name, 0)

    bonus = 0
    logic = []
    # ⭐ 2026-08-20 P2/P3 A/B 实证(2年1884只全市场 92万逐日样本): 尾盘企稳(收盘位置≥0.7 且 上影比例≤0.3)
    #   是独立于量能形态的加分维度——守5/10日线×尾盘企稳 次日涨停率 3.73% vs 全市场 1.58%(2.36倍),
    #   分年度 2024 3.5x / 2025 2.1x / 2026 1.8x 稳健。收盘位置≥0.9(光头强收) 时 6.60%(4.2倍)。
    #   放量收高(vol_ratio≥1.3+收阳+收盘位置≥0.8) → 16.75% (6.2倍); 放量×企稳 → 23.85% (最强)。
    #   注意: 文章宣称"前一日缩量洗盘"反而拖累(缩量2.87% < 不限量3.73%), 已不额外加分。
    if det.get("tail_stable"):
        bonus += 8
        logic.append(f"尾盘企稳: 收盘位置{det.get('close_pos')} 上影{det.get('tail_up_shadow')}(研究: 次日涨停率2.4倍)")
        if det.get("close_pos", 0) >= 0.9:
            bonus += 4
            logic.append("光头强收: 收盘贴近日高(研究: 涨停率6.6%)")
        if (det.get("vol_ratio") or 0) >= 1.3:
            bonus += 6
            logic.append("放量尾盘拉升(收高): 次日涨停率6.2倍(研究)")
    if typ == "缩量地量":
        if det.get("chg", 0) < 0:
            bonus += 5
            logic.append("缩量+小阴十字：抛压枯竭")
        else:
            logic.append("缩量+小阳十字：浮筹清洗")
        logic.append(f"量比{det.get('vol_ratio')} 振幅{det.get('amplitude')}% 站稳5/10日线")
    elif typ == "温和放量":
        bonus += 5
        logic.append(f"量比{det.get('vol_ratio')} 收阳{det.get('chg')}% 无长上影 均线多头")
    elif typ == "翻倍爆量":
        if det.get("position") == "低位":
            bonus += 10
            logic.append("低位首板试盘：抛压一次性释放")
        else:
            bonus += 5
            logic.append("上涨中途试盘：逼近前高")
        logic.append(f"量比{det.get('vol_ratio')} 振幅{det.get('amplitude')}% 冲高回落")

    # ⭐ 2026-08-21 前2周全面研究融合 (修正口径 v2: T-1收盘特征 → T日次日涨停, 18.9万全市场样本)
    # 研究结论见 limitup-research/研究结论-前2周版.md (v2 修正: v1 误用 T+1 结果错位一天已废弃):
    #   ① 突破前夜(距60日高≤3%): T日涨停率19.24% (8.3x) → +12
    #   ② 涨停基因(近60日涨停次数): 2次3.77% / 4次6.14% / 6次7.66% 单调递增 → +6/+10
    #   ③ 前2周动量(w2>20%): 5.67% (2.4x) → +5
    #   ④ 前2周放量天数(≥3天): 3.52% / 5天6.92% (3.0x) → +4
    #   ⑤ 多头排列(MA5>MA10>MA20): 3.39% (1.5x) → +3
    #   每日前视: Top10 次日涨停率 13.53% (随机2.57%的5.3倍), 分月稳健 8.3%~25%
    _closes = [r["close"] for r in rows]
    _limit_cnt = 0
    for _i in range(max(0, idx - 60), idx):
        if _closes[_i] > 0 and _closes[_i - 1] > 0 and (_closes[_i] / _closes[_i - 1] - 1) * 100 >= 9.5:
            _limit_cnt += 1
    det["limit_gene_60"] = _limit_cnt
    _posd = det.get("pos_detail") or {}
    _dist_hi = _posd.get("dist_to_high60")
    # 突破前夜: 收盘距60日高点≤3% (全市场最强单因子, 9.4倍)
    if _dist_hi is not None and _dist_hi <= 0.03:
        bonus += 12
        logic.append(f"突破前夜: 距60日高点{round(_dist_hi*100,1)}%(研究: 全市场次日涨停率13.7%·9.4倍)")
    # 涨停基因加分 (近60日涨停次数)
    if _limit_cnt >= 4:
        bonus += 10
        logic.append(f"涨停基因{_limit_cnt}次(近60日): 次日涨停率6.1%(研究·4.2倍)")
    elif _limit_cnt >= 2:
        bonus += 6
        logic.append(f"涨停基因{_limit_cnt}次(近60日): 次日涨停率3.6%(研究·2.5倍)")
    # 前2周动量
    if idx >= 10:
        _w2 = (_closes[idx] / _closes[idx - 10] - 1) * 100
        det["w2_chg"] = round(_w2, 2)
        if _w2 > 20:
            bonus += 5
            logic.append(f"前2周涨{_w2:.1f}%(研究: 次日涨停率5.0%·3.4倍)")
    # 前2周放量天数 (放量=量>1.5×前5日均量)
    _vol_up = 0
    for _i in range(max(0, idx - 10), idx):
        _bv = [r["volume"] for r in rows[max(0, _i - 5):_i]]
        if _bv and sum(_bv) / len(_bv) > 0 and rows[_i]["volume"] > 1.5 * sum(_bv) / len(_bv):
            _vol_up += 1
    det["vol_up_days"] = _vol_up
    if _vol_up >= 3:
        bonus += 4
        logic.append(f"前2周放量{_vol_up}天(研究: 资金持续介入 3.5倍)")
    # 多头排列
    _ma5, _ma10, _ma20 = det.get("ma5"), det.get("ma10"), det.get("ma20")
    if _ma5 and _ma10 and _ma20 and _ma5 > _ma10 > _ma20:
        bonus += 3
        logic.append("多头排列(MA5>MA10>MA20)")
    score = base + pos_score + bonus
    level = "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 50 else "D"
    return {
        "type": typ,
        "name": cls["name"],
        "level": level,
        "score": score,
        "position": pos_name,
        "logic": "; ".join(logic),
        "detail": det,
    }


def analyze_stock(code: str, count: int = 120) -> Optional[Dict[str, Any]]:
    """单只股票打板潜力分析（对最后一根K线评分）。"""
    try:
        rows = fetch_daily_kline(code, count=count)
    except Exception:
        return None
    if len(rows) < 60:
        return None   # 次新排除：上市不足60交易日，无60日高点，位置判断无意义
    rows = attach_prev_close(rows)
    sig = score_signal(rows, len(rows) - 1)
    sig["code"] = code
    last = rows[-1]
    sig["price"] = last["close"]
    sig["day"] = last["day"]
    return sig


def run_screener(codes: List[str], top_n: int = 20, count: int = 120,
                 workers: int = 8, progress=None) -> List[Dict[str, Any]]:
    """批量打分排序（并发拉K线，新浪不封IP；结果按评分排序）。"""
    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(analyze_stock, code, count): code for code in codes}
        for fut in as_completed(futures):
            try:
                sig = fut.result()
            except Exception:
                sig = None
            if sig and sig["type"] != "无形态":
                results.append(sig)
            done += 1
            if progress and done % 200 == 0:
                progress(done, len(codes))
    results.sort(key=lambda x: -x["score"])
    return results[:top_n]


# ------------------------------------------------------------------ 统计 ----

def limitup_statistics(rows: List[Dict[str, Any]], code: str) -> Dict[str, Any]:
    """历史统计验证（文字①的可执行版）。

    两个口径：
      A. 对所有涨停日 T，统计 T-1 的量能形态分布 → 验证"涨停前一日只会归为三类"
      B. 对所有形态出现日 T-1，统计次日 T 涨停率 → 诚实呈现真实概率（会远低于90%）
    """
    rows = attach_prev_close(rows)
    stats: Dict[str, Dict[str, Any]] = {}
    base = {"count": 0, "next_limit": 0, "next_up": 0, "next_avg_chg": [], "chain2": 0}

    for idx in range(25, len(rows) - 1):
        cls = classify_prev_volume(rows, idx)
        typ = cls["type"]
        st = stats.setdefault(typ, dict(base))
        st["count"] += 1
        nxt = rows[idx + 1]
        if nxt["close"] > nxt["prev_close"]:
            st["next_up"] += 1
        st["next_avg_chg"].append((nxt["close"] - nxt["prev_close"]) / nxt["prev_close"] * 100.0)
        if is_limit_up(nxt, code, nxt["prev_close"]):
            st["next_limit"] += 1
            # 连板：T+2 也涨停
            if idx + 2 < len(rows):
                nxt2 = rows[idx + 2]
                if is_limit_up(nxt2, code, rows[idx + 1]["close"]):
                    st["chain2"] += 1

    # 口径A：涨停日的 T-1 形态分布
    limit_day_prev = {"缩量地量": 0, "温和放量": 0, "翻倍爆量": 0, "无形态": 0}
    total_limit = 0
    for idx in range(25, len(rows)):
        if is_limit_up(rows[idx], code, rows[idx].get("prev_close")):
            total_limit += 1
            cls = classify_prev_volume(rows, idx - 1)
            limit_day_prev[cls["type"]] = limit_day_prev.get(cls["type"], 0) + 1

    out = {}
    for typ, st in stats.items():
        n = st["count"]
        out[typ] = {
            "出现次数": n,
            "次日上涨率": round(st["next_up"] / n * 100, 1) if n else 0.0,
            "次日涨停率": round(st["next_limit"] / n * 100, 1) if n else 0.0,
            "次日平均涨幅": round(mean(st["next_avg_chg"]), 2) if st["next_avg_chg"] else 0.0,
            "连板次数": st["chain2"],
        }
    return {
        "code": code,
        "涨停总数": total_limit,
        "涨停日前一日形态分布": limit_day_prev,
        "三类形态占比": {k: round(v / total_limit * 100, 1) if total_limit else 0
                       for k, v in limit_day_prev.items()},
        "形态→次日涨停率": out,
    }


import time as _t
def time_sleep(sec: float) -> None:
    _t.sleep(sec)
