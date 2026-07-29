"""Sina API数据源 — Ashare兼容层，A股实时行情备用数据源
Sina API (http://hq.sinajs.cn) 与腾讯API互为备选
"""
import os, json, logging, time
from datetime import datetime, timedelta
import urllib.request

logger = logging.getLogger("aurora.sina")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://finance.sina.com.cn",
}

def _fetch(url, timeout=5, retries=2):
    """带重试的HTTP GET"""
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            r = urllib.request.urlopen(req, timeout=timeout)
            return r.read()
        except Exception as e:
            if i < retries - 1:
                time.sleep(1)
                continue
            raise
    return b""

def get_realtime_quotes(codes, prefix=True):
    """获取实时行情 — 对标Ashare.get_realtime_quotes()
    
    Args:
        codes: 股票代码列表 ["600519","000001"] 或单个代码
        prefix: 是否自动加前缀(sh/sz)
    Returns:
        dict: {code: {name, open, price, high, low, volume, amount, change, change_pct}}
    """
    if isinstance(codes, str):
        codes = [codes]
    
    # 加前缀
    if prefix:
        prefixed = []
        for c in codes:
            c = c.strip()
            if c.startswith("sh") or c.startswith("sz") or c.startswith("bj"):
                prefixed.append(c)
            elif c.startswith("6") or c.startswith("9"):
                prefixed.append("sh" + c)
            elif c.startswith("8") or c.startswith("4"):
                prefixed.append("bj" + c)
            else:
                prefixed.append("sz" + c)
    else:
        prefixed = codes
    
    url = "http://hq.sinajs.cn/list=" + ",".join(prefixed)
    try:
        data = _fetch(url, timeout=5)
        raw = data.decode("gbk", errors="replace")
    except Exception as e:
        logger.warning(f"Sina quotes failed: {e}")
        return {}
    
    result = {}
    for line in raw.strip().split(";"):
        if not line or "=" not in line:
            continue
        try:
            key, val = line.split("=", 1)
            val = val.strip().strip('"').strip(";")
            parts = val.split(",")
            if len(parts) < 30:
                continue
            name = parts[0]
            code = key.split("_")[-1] if "_" in key else key
            open_p = float(parts[1]) if parts[1] else 0
            close_y = float(parts[2]) if parts[2] else 0  # 昨日收盘
            price = float(parts[3]) if parts[3] else 0
            high = float(parts[4]) if parts[4] else 0
            low = float(parts[5]) if parts[5] else 0
            volume = int(parts[8]) if parts[8] else 0  # 手
            amount = float(parts[9]) if parts[9] else 0  # 万
            
            change = round(price - close_y, 2) if close_y else 0
            change_pct = round(change / close_y * 100, 2) if close_y else 0
            
            result[code] = {
                "name": name,
                "code": code,
                "open": open_p,
                "close_y": close_y,
                "price": price,
                "high": high,
                "low": low,
                "volume": volume,
                "amount": amount,
                "change": change,
                "change_pct": change_pct,
            }
        except (IndexError, ValueError) as e:
            continue
    return result

def get_indices():
    """获取主要指数行情"""
    codes = ["sh000001", "sz399001", "sz399006", "sh000688", "sh000300", "sh000016"]
    return get_realtime_quotes(codes, prefix=False)

def get_market_breadth():
    """获取市场涨跌家数 — 通过腾讯API"""
    try:
        import urllib.request as _ur
        r = _ur.urlopen("http://qt.gtimg.cn/q=sh000001", timeout=5)
        raw = r.read().decode("gbk", errors="replace")
        parts = raw.split("~")
        if len(parts) > 35:
            up = int(float(parts[28])) if parts[28] else 0
            down = int(float(parts[29])) if parts[29] else 0
            if up > 0 or down > 0:
                return {"up_count": up, "down_count": down, "total": up + down}
    except:
        pass
    return None


def get_klines(code, ktype="D", days=60):
    """获取K线数据 — 对标Ashare.get_kline()
    
    ktype: D=日线 W=周线 M=月线 60=60分 30=30分 15=15分
    """
    # Sina K-line API
    symbol = code
    if not code.startswith(("sh", "sz", "bj")):
        if code.startswith(("6", "9")):
            symbol = "sh" + code
        elif code.startswith(("8", "4")):
            symbol = "bj" + code
        else:
            symbol = "sz" + code
    
    url = f"http://quotes.money.163.com/service/chddata.html?code={symbol}&start=20200101&end=20991231&fields=TCLOSE"
    try:
        data = _fetch(url, timeout=10)
        # 163 returns CSV
        lines = data.decode("gbk", errors="replace").strip().split("\n")
        if len(lines) < 2:
            return None
        result = []
        for line in lines[1:1+days]:  # Skip header
            parts = line.split(",")
            if len(parts) >= 6:
                result.append({
                    "date": parts[0],
                    "open": float(parts[1]) if parts[1] else 0,
                    "high": float(parts[2]) if parts[2] else 0,
                    "low": float(parts[3]) if parts[3] else 0,
                    "close": float(parts[4]) if parts[4] else 0,
                    "volume": int(parts[5]) if parts[5] else 0,
                })
        return result
    except Exception as e:
        logger.warning(f"Sina K-line failed for {code}: {e}")
        return None

# 测试
if __name__ == "__main__":
    print("=== Ashare兼容层测试 ===")
    quotes = get_realtime_quotes(["600519", "000001", "300750"])
    for code, q in quotes.items():
        print(f"  {q['name']}({code}): {q['price']} {q['change_pct']}%")
    
    print(f"\n  指数:")
    for code, q in get_indices().items():
        print(f"  {q['name']}({code}): {q['price']} {q['change_pct']}%")
    
    breadth = get_market_breadth()
    if breadth:
        print(f"\n  涨跌: {breadth['up_count']}/{breadth['down_count']}")
