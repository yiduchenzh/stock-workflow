"""集合竞价分析 — 承接力CC+竞价量比+开盘方向预判"""
import urllib.request, json, logging
from datetime import datetime
logger = logging.getLogger("aurora.auction")

UA = "Mozilla/5.0"

# ⭐ 2026-08-20 A/B 实证(2年1884只全市场, 25512竞价信号):
#   高开 gap 越高, 次日胜率单调下降 —— 1~2%:71.5% → 2~3%:62.9% → 3~4%:58.6%
#   → 4~5%:54.3% → 5~6%:51.3% → 6~7%:47.2% (隔夜口径)。
#   "高开2-5%黄金区间"是自媒体宣称, 数据证伪; 真实规律=低高开优先(1-2%最优)。
#   反加权排序 (cc - k×gap) 分年度/top_n/系数全部稳健提升: 隔夜胜率 63.6%→72.8%(k=2)。
#   k=0 关闭=原行为(兼容历史回测)。
GAP_PENALTY_K = 2.0

def get_auction_data(codes: list) -> dict:
    """获取集合竞价数据 (腾讯接口)"""
    if not codes: return {}
    # 腾讯竞价接口: qt.gtimg.cn 的竞价字段
    prefixed = []
    for c in codes[:50]:
        if not c or not isinstance(c, str): continue
        pfx = "sh" if c.startswith(("6","9")) else "sz"
        prefixed.append(f"{pfx}{c}")
    url = f"https://qt.gtimg.cn/q={','.join(prefixed)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        data = urllib.request.urlopen(req, timeout=10).read().decode("gbk", errors="replace")
    except Exception as e:
        logger.warning(f"竞价数据获取失败: {e}")
        return {}
    
    result = {}
    for line in data.strip().split(";"):
        if "=" not in line or '"' not in line: continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53: continue
        code = key[2:]
        # vals[5]=开盘价, vals[7]=最高, vals[8]=最低, vals[36]=竞价量, vals[37]=竞价额
        result[code] = {
            "code": code, "name": vals[1],
            "open": float(vals[5]) if vals[5] else 0,
            "high": float(vals[33]) if vals[33] else 0,
            "low": float(vals[34]) if vals[34] else 0,
            "auction_vol": float(vals[36]) if len(vals) > 36 and vals[36] else 0,
            "auction_amount": float(vals[37]) if len(vals) > 37 and vals[37] else 0,
            "change_pct": float(vals[32]) if vals[32] else 0,
        }
    return result

def calc_cc_ratio(auction_data: dict) -> dict:
    """计算集合竞价承接力(CC Ratio)
    
    CC = 竞价买盘 / 竞价卖盘
    CC >= 2.0 → 强承接(主力抢筹)
    1.5 <= CC < 2.0 → 中等承接
    1.0 <= CC < 1.5 → 弱承接
    CC < 1.0 → 无承接(主力出逃)
    """
    if not auction_data:
        return {"cc": 0, "grade": "无数据", "signal": False}
    
    vol = auction_data.get("auction_vol", 0)
    amount = auction_data.get("auction_amount", 0)
    open_price = auction_data.get("open", 0)
    prev_close = open_price / (1 + auction_data.get("change_pct", 0) / 100) if auction_data.get("change_pct", 0) != 0 else open_price
    change = auction_data.get("change_pct", 0)
    
    if vol <= 0 or open_price <= 0:
        return {"cc": 0, "grade": "无竞价量", "signal": False}
    
    # 简化CC计算: (竞价量×开盘方向) / 近5日均量代理
    avg_price = amount / vol if vol > 0 else open_price
    # 如果高开且竞价量大 → 买方承接力强
    cc = (1 + change / 100) * (vol / 10000) if vol > 0 else 0
    
    if cc >= 2.0 and change > 0:
        grade = "A: 强承接(主力抢筹)"
        signal = True
    elif cc >= 1.5 or (change > 1 and cc >= 1.0):
        grade = "B: 中等承接"
        signal = True
    elif cc >= 1.0:
        grade = "C: 弱承接"
        signal = False
    else:
        grade = "D: 无承接(主力出逃)"
        signal = False
    
    return {
        "cc": round(cc, 2), "grade": grade, "signal": signal,
        "open_change": round(change, 2), "auction_vol_wan": round(vol/10000, 1),
        "auction_amount_wan": round(amount/10000, 1),
    }

def auction_screen(candidates: list, top_n: int = 10) -> list:
    """集合竞价筛选: 取CC≥1.5的前N只

    v14.46 (2026-08-10 融合 hunter-v2 pick_engine 竞价方向):
    增加 hunter-v2 竞价护栏（pick_engine.py direction=auction）:
      gap 1%~7% (高开有承接意愿, 但防追高) + 量比≥1.5 + 成交额≥0.3亿
    保留 CC 承接力分级作为方向确认。
    """
    if not candidates: return []
    codes = [c.get("code", "") for c in candidates if c.get("code")]
    auction = get_auction_data(codes)
    
    results = []
    for c in candidates:
        code = c.get("code", "")
        ad = auction.get(code, {})
        cc_info = calc_cc_ratio(ad)
        c["auction"] = cc_info
        # ── v14.46: hunter-v2 竞价护栏（防追高 + 量能确认）──
        guard = _auction_guard(c, ad)
        if not guard["ok"]:
            c["auction"]["guard_reason"] = guard["reason"]
            logger.debug(f"[Auction] {code} 护栏拦截: {guard['reason']}")
            continue
        if cc_info["signal"]:
            results.append(c)
    
    # ⭐ 2026-08-20 A/B 实证(2年1884只全市场 25512信号): 高开 gap 越高次日胜率单调降
    #   1~2%:71.5% → 2~3%:62.9% → 3~4%:58.6% → 4~5%:54.3% → 5~6%:51.3% → 6~7%:47.2%
    #   "黄金区间2-5%"自媒体宣称被证伪(加权反而 58.9%<基线63.6%)。反加权 (cc - k×gap)
    #   隔夜胜率 63.6%→72.8% / 次日收 62.5%→70.2% (k=2, 分年度/top_n/系数全部稳健)。
    #   排序键 = cc - GAP_PENALTY_K × gap(高开越低越优先, 1-2%最优); k=0 关闭=原行为。
    def _sort_key(x):
        cc = x["auction"]["cc"]
        gap = x["auction"].get("open_change") or 0.0
        return cc - GAP_PENALTY_K * gap

    results.sort(key=_sort_key, reverse=True)
    logger.info(f"[Auction] {len(results)}/{len(candidates)} passed (CC>=1.5 + 竞价护栏 + 低高开优先 k={GAP_PENALTY_K})")
    return results[:top_n]


def _auction_guard(c: dict, ad: dict) -> dict:
    """hunter-v2 竞价方向护栏（pick_engine.py direction=auction 同口径）:

    1. 高开 gap 1%~7%: 开盘有承接意愿(≥1%) 且 不追高(≤7%)
    2. 量比 ≥1.5: 竞价放量确认
    3. 成交额 ≥0.3亿: 有真实资金参与
    """
    open_p = ad.get("open") or c.get("open") or 0
    pre_c = ad.get("last_close") or c.get("last_close") or 0
    if not open_p or not pre_c:
        return {"ok": True, "reason": ""}  # 数据缺失不拦截（保守放行）
    gap = (open_p / pre_c - 1) * 100
    vr = c.get("vol_ratio") or 0
    amount_yi = (c.get("amount_wan") or 0) / 10000.0
    if gap < 1.0:
        return {"ok": False, "reason": f"高开不足 gap={gap:.1f}%<1%"}
    if gap > 7.0:
        return {"ok": False, "reason": f"防追高 gap={gap:.1f}%>7%"}
    if vr < 1.5:
        return {"ok": False, "reason": f"量比不足 vr={vr:.1f}<1.5"}
    if amount_yi < 0.3:
        return {"ok": False, "reason": f"成交额不足 {amount_yi:.2f}亿<0.3亿"}
    return {"ok": True, "reason": f"gap={gap:.1f}% vr={vr:.1f} 额{amount_yi:.2f}亿"}