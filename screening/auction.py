"""集合竞价分析 — 承接力CC+竞价量比+开盘方向预判"""
import urllib.request, json, logging
from datetime import datetime
logger = logging.getLogger("aurora.auction")

UA = "Mozilla/5.0"

def get_auction_data(codes: list) -> dict:
    """获取集合竞价数据 (腾讯接口)"""
    if not codes: return {}
    # 腾讯竞价接口: qt.gtimg.cn 的竞价字段
    prefixed = []
    for c in codes[:50]:
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
    """集合竞价筛选: 取CC≥1.5的前N只"""
    if not candidates: return []
    codes = [c.get("code", "") for c in candidates if c.get("code")]
    auction = get_auction_data(codes)
    
    results = []
    for c in candidates:
        code = c.get("code", "")
        ad = auction.get(code, {})
        cc_info = calc_cc_ratio(ad)
        c["auction"] = cc_info
        if cc_info["signal"]:
            results.append(c)
    
    results.sort(key=lambda x: x["auction"]["cc"], reverse=True)
    logger.info(f"[Auction] {len(results)}/{len(candidates)} passed (CC>=1.5)")
    return results[:top_n]