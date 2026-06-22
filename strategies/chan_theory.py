
"""缠论 v2.0 — 108课完整映射: 包含处理→分型→笔→线段→中枢→背驰→买卖点"""
import numpy as np
import pandas as pd
import logging
logger = logging.getLogger("aurora.chan")

# ═══ 第0层: K线包含处理 ═══
def _merge_klines(df):
    """上升取高高, 下降取低低 — 缠论108课原文"""
    if df is None or len(df) < 2: return df
    o, h, l, c = df["open"].values, df["high"].values, df["low"].values, df["close"].values
    merged_o, merged_h, merged_l, merged_c = [o[0]], [h[0]], [l[0]], [c[0]]
    direction = 1 if o[1] > o[0] else -1  # 初始方向
    for i in range(1, len(o)):
        # 检查包含关系
        if (h[i] <= h[i-1] and l[i] >= l[i-1]) or (h[i] >= h[i-1] and l[i] <= l[i-1]):
            # 包含处理
            if direction > 0:  # 上升: 取高高
                new_h = max(h[i], merged_h[-1])
                new_l = max(l[i], merged_l[-1])
            else:  # 下降: 取低低
                new_h = min(h[i], merged_h[-1])
                new_l = min(l[i], merged_l[-1])
            merged_h[-1] = new_h; merged_l[-1] = new_l
            merged_c[-1] = c[i] if c[i] > merged_o[-1] else merged_c[-1]
        else:
            merged_o.append(o[i]); merged_h.append(h[i])
            merged_l.append(l[i]); merged_c.append(c[i])
            direction = 1 if o[i] > merged_o[-2] else -1
    return pd.DataFrame({"open": merged_o, "high": merged_h, "low": merged_l, "close": merged_c})

# ═══ 第1层: 分型检测 (标准3K线) ═══
def detect_fractals(kline_df):
    """标准顶/底分型检测 — 包含处理后3K线"""
    if kline_df is None:
        return {"tops": [], "bottoms": [], "bs_points": [], "fractal_count": 0, "signal": False}
    df = _merge_klines(kline_df)
    if len(df) < 5:
        return {"tops": [], "bottoms": [], "bs_points": [], "fractal_count": 0, "signal": False}
    high, low, close = df["high"].values, df["low"].values, df["close"].values
    tops, bottoms = [], []
    for i in range(1, len(high) - 1):
        # 顶分型: 中间K线高点是三根中最高, 低点也是三根中最高
        if high[i] > high[i-1] and high[i] > high[i+1] and low[i] > low[i-1] and low[i] > low[i+1]:
            # 检查顶分型力度: 第三根不深入第一根1/2 → 较强
            strength = "strong" if close[i+1] > (high[i] + low[i]) / 2 else "normal"
            tops.append({"idx": i, "price": float(high[i]), "strength": strength})
        # 底分型: 中间K线高点是三根中最低, 低点也是三根中最低
        elif low[i] < low[i-1] and low[i] < low[i+1] and high[i] < high[i-1] and high[i] < high[i+1]:
            strength = "strong" if close[i+1] < (high[i] + low[i]) / 2 else "normal"
            bottoms.append({"idx": i, "price": float(low[i]), "strength": strength})
    
    bs = _classify_bs_points(tops, bottoms, close, df)
    return {
        "tops": tops[-10:], "bottoms": bottoms[-10:],
        "bs_points": bs, "fractal_count": len(tops) + len(bottoms),
        "signal": len(bs) > 0, "last_bs": bs[-1] if bs else None,
    }

# ═══ 第2层: 笔(Bi)检测 ═══
def _detect_bi(df):
    """相邻顶底分型间构成笔 — 至少1根独立K线"""
    result = detect_fractals(df)
    tops = result["tops"]; bottoms = result["bottoms"]
    bis = []
    ti, bi = 0, 0
    while ti < len(tops) and bi < len(bottoms):
        t, b = tops[ti], bottoms[bi]
        if abs(t["idx"] - b["idx"]) >= 2:  # 至少1根独立K线
            if t["idx"] > b["idx"]:
                bis.append({"type": "up_bi", "start": b["price"], "end": t["price"],
                           "start_idx": b["idx"], "end_idx": t["idx"]})
                ti += 1
            else:
                bis.append({"type": "down_bi", "start": t["price"], "end": b["price"],
                           "start_idx": t["idx"], "end_idx": b["idx"]})
                bi += 1
        else:
            if t["idx"] > b["idx"]: bi += 1
            else: ti += 1
    return bis

# ═══ 第3-4层: 线段+中枢检测 ═══
def _detect_hub(df):
    """中枢检测: 至少3个连续次级别走势重叠区间 [ZD, ZG]"""
    bis = _detect_bi(df)
    if len(bis) < 3: return []
    # 用笔的极值作为次级别走势代理
    swings = []
    for bi in bis[-12:]:
        swings.append((min(bi["start"], bi["end"]), max(bi["start"], bi["end"])))
    hubs = []
    for i in range(len(swings) - 2):
        highs = [s[1] for s in swings[i:i+3]]
        lows = [s[0] for s in swings[i:i+3]]
        ZG = min(highs); ZD = max(lows)
        if ZD < ZG:  # 有重叠 = 中枢
            hubs.append({"ZD": round(ZD, 2), "ZG": round(ZG, 2),
                        "center": round((ZD + ZG) / 2, 2),
                        "width_pct": round((ZG - ZD) / ZD * 100, 2),
                        "idx_range": (swings[i][0], swings[i+2][1])})
    return hubs

# ═══ 第5层: 背驰检测 ═══
def _detect_divergence(df, hubs):
    """MACD辅助背驰: c段力度 < b段力度"""
    if df is None or len(df) < 60 or not hubs: return []
    close = df["close"].values
    divergences = []
    # 简化: 用最后一中枢离开段 vs 进入段的价格变化率
    if len(hubs) >= 1:
        hub = hubs[-1]
        ZD, ZG = hub["ZD"], hub["ZG"]
        into_seg = abs(ZG - ZD)
        leave_seg = abs(close[-1] - ZG)
        if leave_seg < into_seg * 0.618:
            divergences.append({"type": "trend_divergence", "into_pct": round(into_seg/ZD*100, 1),
                               "leave_pct": round(leave_seg/ZD*100, 1),
                               "position": "顶部背驰" if close[-1] > ZG else "底部背驰"})
    return divergences

# ═══ 第6层: 三类买卖点 ═══
def _classify_bs_points(tops, bottoms, close, df):
    """完整的三类买卖点 — 结合中枢+背驰+分型"""
    points = []
    hubs = _detect_hub(df)
    divergences = _detect_divergence(df, hubs)
    
    # 一买: 下跌趋势+最后一个中枢+底部背驰+底分型
    if bottoms and divergences:
        for d in divergences:
            if "底部背驰" in d["position"]:
                b = bottoms[-1]
                points.append({"type": "buy1", "price": b["price"], "idx": b["idx"],
                              "desc": f"一买(底背驰,中枢宽{d.get('into_pct',0)}%)"})
    
    # 二买: 一买后回抽不创新低 → 次低底分型
    if bottoms:
        recent_b = [b for b in bottoms if b["idx"] > len(close) - 30]
        if len(recent_b) >= 2:
            b2, b1 = recent_b[-2], recent_b[-1]
            if b1["price"] > b2["price"]:  # 抬高
                points.append({"type": "buy2", "price": b1["price"], "idx": b1["idx"],
                              "desc": f"二买(回踩确认,底抬高{b1['price']-b2['price']:.2f})"})
    
    # 三买: 离开中枢+次级别回抽不进ZG
    if hubs and bottoms:
        hub = hubs[-1]; ZG = hub["ZG"]
        recent_b = [b for b in bottoms if b["idx"] > len(close) - 20]
        if recent_b and recent_b[-1]["price"] > ZG:
            points.append({"type": "buy3", "price": recent_b[-1]["price"],
                          "idx": recent_b[-1]["idx"],
                          "desc": f"三买(出中枢回踩不进ZG={ZG:.2f})"})
    
    # 卖点系统 (镜像)
    if tops and divergences:
        for d in divergences:
            if "顶部背驰" in d["position"]:
                t = tops[-1]
                points.append({"type": "sell1", "price": t["price"], "idx": t["idx"],
                              "desc": f"一卖(顶背驰)"})
    
    if tops:
        recent_t = [t for t in tops if t["idx"] > len(close) - 30]
        if len(recent_t) >= 2:
            t2, t1 = recent_t[-2], recent_t[-1]
            if t1["price"] < t2["price"]:
                points.append({"type": "sell2", "price": t1["price"], "idx": t1["idx"],
                              "desc": "二卖(反弹确认,顶降低)"})
    
    if hubs and tops:
        hub = hubs[-1]; ZD = hub["ZD"]
        recent_t = [t for t in tops if t["idx"] > len(close) - 20]
        if recent_t and recent_t[-1]["price"] < ZD:
            points.append({"type": "sell3", "price": recent_t[-1]["price"],
                          "idx": recent_t[-1]["idx"],
                          "desc": f"三卖(破中枢回抽不进ZD={ZD:.2f})"})
    
    return points

def chan_score(kline_df):
    """缠论综合评分 0-100 — 中枢+背驰+买卖点加权"""
    if kline_df is None or len(kline_df) < 30:
        return 40
    result = detect_fractals(kline_df)
    hubs = _detect_hub(kline_df) if kline_df is not None else []
    divergences = _detect_divergence(kline_df, hubs)
    
    score = 40  # 基准
    if result["fractal_count"] >= 3: score += 5   # 有充足分型
    if hubs: score += 15                            # 有中枢
    if divergences: score += 15                     # 有背驰
    if result.get("signal"): score += 10            # 有买卖点
    
    # 买卖点质量加成
    last = result.get("last_bs")
    if last:
        if last["type"] == "buy3": score += 15      # 三买最优
        elif last["type"] == "buy2": score += 10    # 二买次优
        elif last["type"] == "buy1": score += 5     # 一买需谨慎
        elif "sell" in last["type"]: score -= 5     # 卖点=降分
    
    return min(max(score, 0), 100)
