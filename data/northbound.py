"""北向资金监控 — 陆股通净流入/累计净买入"""
import requests, logging
from datetime import datetime
logger = logging.getLogger("aurora.northbound")

def get_northbound_flow() -> dict:
    """获取北向资金当日净流入 (东财接口)"""
    try:
        # 东财北向资金实时接口
        url = "https://push2.eastmoney.com/api/qt/kamt.kline/get"
        params = {
            "fields1": "f1,f2,f3,f4",
            "fields2": "f51,f52,f53,f54",
            "klt": "1", "lmt": "1",
            "secid": "1.000300",  # 沪股通
        }
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}
        r = requests.get(url, params=params, headers=headers, timeout=10)
        data = r.json().get("data", {})
        klines = data.get("klines", [])
        
        # 当日净流入
        today_net = 0
        if klines:
            last = klines[-1].split(",")
            if len(last) >= 2:
                today_net = float(last[1]) / 10000  # 转换为亿
        
        # 累计净买入 (从历史汇总接口)
        total_url = "https://push2.eastmoney.com/api/qt/kamt.kline/get"
        total_params = {
            "fields1": "f1,f2,f3,f4",
            "fields2": "f51,f52",
            "klt": "101", "lmt": "1",
            "secid": "1.000300",
        }
        r2 = requests.get(total_url, params=total_params, headers=headers, timeout=10)
        total_data = r2.json().get("data", {})
        total_klines = total_data.get("klines", [])
        cumulative = 0
        if total_klines:
            last_total = total_klines[-1].split(",")
            if len(last_total) >= 2:
                cumulative = float(last_total[1]) / 100000000  # 转换为亿
        
        # 方向判断
        if today_net > 30:
            direction = "strong_inflow"
            signal = f"大幅流入({today_net:.0f}亿)"
        elif today_net > 0:
            direction = "inflow"
            signal = f"净流入({today_net:.0f}亿)"
        elif today_net > -20:
            direction = "outflow"
            signal = f"净流出({abs(today_net):.0f}亿)"
        else:
            direction = "strong_outflow"
            signal = f"大幅流出({abs(today_net):.0f}亿)"
        
        return {
            "today_net_yi": round(today_net, 1),
            "cumulative_yi": round(cumulative, 1),
            "direction": direction,
            "signal": signal,
            "score": _flow_to_score(today_net),
        }
    except Exception as e:
        logger.warning(f"北向资金获取失败: {e}")
        return {
            "today_net_yi": 0, "cumulative_yi": 0,
            "direction": "unknown", "signal": "数据获取失败",
            "score": 50,
        }

def _flow_to_score(net_yi: float) -> float:
    """北向净流入→评分"""
    if net_yi > 100: return 100
    elif net_yi > 50: return 80
    elif net_yi > 20: return 65
    elif net_yi > 0: return 55
    elif net_yi > -20: return 40
    elif net_yi > -50: return 25
    else: return 10