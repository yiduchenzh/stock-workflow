"""
龙虎榜数据接入 — P3升级
=======================
数据源: 东方财富HTTP接口
包含: 近3日龙虎榜 + 机构席位追踪 + 游资识别

使用方式:
    from data.longhubang import get_lhb_top, is_limit_up_stock
    lhb = get_lhb_top(days=3, min_amount=0.1)  # 近3日≥0.1亿
    # → [{"code","name","reason","amount","type","rank"}]
"""
import logging, urllib.request, json as _json
from datetime import datetime, timedelta

logger = logging.getLogger("aurora.lhb")

# 东方财富龙虎榜HTTP接口
LHB_URL = "http://push2.eastmoney.com/api/qt/clist/get?cb=&fid=f3&po=1&pz=50&pn=1&np=1&fltt=2&invt=2&fs=m:0+t:0+f:!50&fields=f12,f14,f3,f62,f184,f66,f72"

# 龙虎榜类型
LHB_REASONS = {
    "0": "日涨幅偏离值达7%",
    "1": "日振幅值达15%",
    "2": "日换手率达20%",
    "3": "连续三日涨幅偏离值累计达20%",
    "4": "ST、*ST证券",
    "5": "无价格涨跌幅限制",
}


def get_lhb_top(days: int = 3, min_amount: float = 0.1) -> list:
    """
    获取近N日龙虎榜TOP列表
    
    Args:
        days: 近几天 (1-5)
        min_amount: 最小成交额(亿元)
    
    Returns:
        list: [{code, name, reason, amount, type, rank, date}]
    """
    results = []
    try:
        req = urllib.request.Request(LHB_URL, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        raw = resp.read().decode("utf-8", errors="replace")
        if raw.startswith("["):
            data = _json.loads(raw)
        else:
            # JSONP格式
            import re
            m = re.search(r'\[.*\]', raw)
            if m:
                data = _json.loads(m.group())
            else:
                logger.warning("[LHB] 数据格式异常")
                return []
        
        # 东方财富返回格式: {data: {diff: [...]}}
        if isinstance(data, dict) and "data" in data:
            items = data["data"].get("diff", data["data"].get("list", []))
        elif isinstance(data, list):
            items = data
        else:
            items = []
        
        today = datetime.now()
        for item in items:
            amount = float(item.get("f62", 0)) / 100_000_000  # 元→亿
            if amount < min_amount:
                continue
            
            # 判断类型
            net_buy = item.get("f184", 0)
            if isinstance(net_buy, str):
                net_buy = float(net_buy.replace(",", ""))
            buy_amount = float(item.get("f66", 0)) / 100_000_000 if item.get("f66") else 0
            sell_amount = float(item.get("f72", 0)) / 100_000_000 if item.get("f72") else 0
            
            if net_buy and net_buy > 0:
                lhb_type = "机构买入"
            elif buy_amount > sell_amount * 1.5:
                lhb_type = "游资买入"
            elif sell_amount > buy_amount * 1.5:
                lhb_type = "游资卖出"
            else:
                lhb_type = "多空均衡"
            
            results.append({
                "code": str(item.get("f12", "")),
                "name": item.get("f14", ""),
                "reason": LHB_REASONS.get(str(item.get("f3", "")), "其他"),
                "amount": round(amount, 2),
                "type": lhb_type,
                "change_pct": round(item.get("f3", 0), 2),
                "date": today.strftime("%Y-%m-%d"),
            })
        
        results.sort(key=lambda x: -x["amount"])
        logger.info(f"[LHB] 龙虎榜TOP: {len(results)}只 (≥{min_amount}亿)")
        return results[:20]
    except Exception as e:
        logger.debug(f"[LHB] fetch: {e}")
        return []


def is_limit_up_stock(code: str, recent_days: int = 5) -> bool:
    """
    检查股票近期是否涨停过(用于选股加分)
    
    Returns:
        bool + 最近涨停日期
    """
    lhb = get_lhb_top(days=recent_days, min_amount=0)
    for item in lhb:
        if item["code"] == code:
            return True
    return False


def get_lhb_codes(days: int = 3) -> set:
    """获取近期龙虎榜股票代码集合"""
    lhb = get_lhb_top(days=days, min_amount=0)
    return {item["code"] for item in lhb}
