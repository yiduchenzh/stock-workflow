"""
龙虎榜数据接入 — P0-3 备源切换
=========================
数据源: 同花顺(10jqka) → 腾讯(QQ) 双备源
原东财push2端点已切换为备用源

使用方式:
    from data.longhubang import get_lhb_top, is_limit_up_stock
    lhb = get_lhb_top(days=3, min_amount=0.1)  # 近3日≥0.1亿
    # → [{"code","name","reason","amount","type","rank"}]
"""
import logging, urllib.request, re
from datetime import datetime, timedelta

logger = logging.getLogger("aurora.lhb")

# ========================
# 备源1: 同花顺(10jqka) 龙虎榜
# ========================
LHB_URL_10JQKA = "http://data.10jqka.com.cn/finance/lhb/"

# ========================
# 备源2: 腾讯 龙虎榜
# ========================
LHB_URL_QQ = "https://stockhtm.finance.qq.com/sstock/lhb/"

# 龙虎榜类型
LHB_REASONS = {
    "0": "日涨幅偏离值达7%",
    "1": "日振幅值达15%",
    "2": "日换手率达20%",
    "3": "连续三日涨幅偏离值累计达20%",
    "4": "ST、*ST证券",
    "5": "无价格涨跌幅限制",
}

# 函数是否已知不可用（全局标记避免重复重试）
_LHB_UNAVAILABLE = False


def _fetch_10jqka_lhb() -> list:
    """从同花顺(10jqka)获取龙虎榜数据"""
    results = []
    try:
        req = urllib.request.Request(LHB_URL_10JQKA, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
        })
        resp = urllib.request.urlopen(req, timeout=10)
        html = resp.read().decode("utf-8", errors="replace")

        today = datetime.now()
        # 解析同花顺龙虎榜HTML表格
        # 查找表格行: <tr>...</tr>
        rows = re.findall(
            r'<tr[^>]*>.*?<td[^>]*>.*?<a[^>]*href="[^"]*/(\d+)/[^"]*"[^>]*>([^<]+)</a>.*?</td>'
            r'.*?<td[^>]*>([^<]+)</td>'
            r'.*?<td[^>]*>([^<]+)</td>'
            r'.*?<td[^>]*>([^<]+)</td>',
            html, re.DOTALL
        )

        if rows:
            for row in rows:
                code = row[0].strip()
                name = row[1].strip()
                reason = row[2].strip()
                amount_str = row[3].strip().replace(",", "").replace("亿", "")
                try:
                    amount = float(amount_str) if amount_str else 0
                except ValueError:
                    amount = 0

                results.append({
                    "code": code,
                    "name": name,
                    "reason": reason,
                    "amount": amount,
                    "type": "多空均衡",
                    "change_pct": 0,
                    "date": today.strftime("%Y-%m-%d"),
                    "source": "10jqka",
                })

        if results:
            results.sort(key=lambda x: -x["amount"])
            logger.info(f"[LHB] 同花顺备源: {len(results)}只")
            return results[:20]

        # 尝试第二种解析方式（桌面版表格结构不同）
        rows2 = re.findall(
            r'<tr[^>]*>\s*<td[^>]*>\s*(\d{6})\s*</td>\s*<td[^>]*>\s*([^<]+)\s*</td>',
            html, re.DOTALL
        )
        if rows2:
            for code, name in rows2[:50]:
                results.append({
                    "code": code.strip(),
                    "name": name.strip(),
                    "reason": "龙虎榜",
                    "amount": 0,
                    "type": "多空均衡",
                    "change_pct": 0,
                    "date": today.strftime("%Y-%m-%d"),
                    "source": "10jqka",
                })
            logger.info(f"[LHB] 同花顺备源(降级): {len(results)}只")
            return results

        logger.warning("[LHB] 同花顺备源无数据")
        return []
    except Exception as e:
        logger.debug(f"[LHB] 同花顺备源异常: {e}")
        return []


def _fetch_qq_lhb() -> list:
    """从腾讯股票获取龙虎榜数据"""
    results = []
    try:
        req = urllib.request.Request(LHB_URL_QQ, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        resp = urllib.request.urlopen(req, timeout=10)
        html = resp.read().decode("utf-8", errors="replace")

        today = datetime.now()
        # 解析腾讯龙虎榜HTML
        # 腾讯龙虎榜表格结构通常是: <td><a href="...">股票名</a></td>
        rows = re.findall(
            r'<td[^>]*>\s*<a[^>]*href="[^"]*stock/(\d{6})[^"]*"[^>]*>([^<]+)</a>\s*</td>'
            r'\s*<td[^>]*>([^<]+)</td>',
            html, re.DOTALL
        )

        if rows:
            for code, name, change_pct in rows:
                results.append({
                    "code": code.strip(),
                    "name": name.strip(),
                    "reason": "龙虎榜",
                    "amount": 0,
                    "type": "多空均衡",
                    "change_pct": float(change_pct.strip().replace("%", "")) if change_pct.strip() else 0,
                    "date": today.strftime("%Y-%m-%d"),
                    "source": "qq",
                })

        # 尝试更通用的解析
        if not results:
            rows2 = re.findall(
                r'<td[^>]*>\s*(\d{6})\s*</td>\s*<td[^>]*>\s*([^<]+?)\s*</td>',
                html, re.DOTALL
            )
            for code, name in rows2[:50]:
                results.append({
                    "code": code.strip(),
                    "name": name.strip(),
                    "reason": "龙虎榜",
                    "amount": 0,
                    "type": "多空均衡",
                    "change_pct": 0,
                    "date": today.strftime("%Y-%m-%d"),
                    "source": "qq",
                })

        if results:
            logger.info(f"[LHB] 腾讯备源: {len(results)}只")
            return results[:20]

        logger.debug("[LHB] 腾讯备源无数据")
        return []
    except Exception as e:
        logger.debug(f"[LHB] 腾讯备源异常: {e}")
        return []


def get_lhb_top(days: int = 3, min_amount: float = 0.1) -> list:
    """
    获取近N日龙虎榜TOP列表

    Args:
        days: 近几天 (1-5)
        min_amount: 最小成交额(亿元)

    Returns:
        list: [{code, name, reason, amount, type, rank, date}]
    """
    global _LHB_UNAVAILABLE

    # 如果已标记为不可用，直接返回空列表
    if _LHB_UNAVAILABLE:
        logger.warning("[LHB] 所有备源已知不可用，跳过请求")
        return []

    # 备源1: 同花顺
    results = _fetch_10jqka_lhb()
    if results:
        # 过滤最低成交额
        if min_amount > 0:
            results = [r for r in results if r["amount"] >= min_amount]
        return results[:20]

    # 备源2: 腾讯
    results = _fetch_qq_lhb()
    if results:
        return results[:20]

    # 所有备源均不可用 → 标记为已知不可用
    _LHB_UNAVAILABLE = True
    logger.warning("[LHB] 同花顺+腾讯备源均不可用，标记为已知不可用")
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
