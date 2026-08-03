"""
数据源架构 v2.0 — 2026-07-28 重构

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 优先级  数据源         协议       封IP风险   用途
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1      TDX (通达信)    TCP 7709   极低      K线、实时行情(偏交易层)
  2      腾讯 Tencent    HTTP       极低      PE/PB/市值/换手率/涨跌停(偏估值层)
  3      新浪 Sina       HTTP       低        实时行情备选、K线备选
  4      巨潮 CNINFO     HTTP       低        全市场股票列表(6198只)
  5      东财 EastMoney  HTTP       有风控    仅用于独有数据：行业板块/北向/龙虎榜
  6      同花顺          HTTP       极低      热点题材归因(零鉴权)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WZ歪枣网和XTick已弃用(2026-07)：接口不稳定/需token/有更好替代。
"""
import os as _os, urllib.request, json, time, logging, re as _re
from pathlib import Path
import pandas as pd

logger = logging.getLogger("aurora.data")
UA = "Mozilla/5.0"

# ── 文件锁(Windows并发保护) ──
import msvcrt as _ms

def _lock_file(name: str, timeout: float = 5.0) -> bool:
    lock_path = Path(__file__).resolve().parent.parent / "data" / f"{name}.lock"
    end = time.time() + timeout
    while time.time() < end:
        try:
            fd = _os.open(str(lock_path), _os.O_CREAT | _os.O_WRONLY | _os.O_EXCL)
            _ms.locking(fd, _ms.LK_NBLCK, 1)
            _os.close(fd)
            return True
        except (OSError, IOError, BlockingIOError):
            time.sleep(0.1)
    return False

def _unlock_file(name: str):
    lock_path = Path(__file__).resolve().parent.parent / "data" / f"{name}.lock"
    try:
        if lock_path.exists(): lock_path.unlink()
    except: pass


# ── 辅助函数 ──

def _prefix(code):
    """6位代码 → 腾讯格式前缀 (sh/sz/bj) — v14.41: 修复92开头北交所(920xxx新代码段)"""
    if code.startswith(("8", "4", "92")):
        return f"bj{code}"
    return f"sh{code}" if code.startswith(("6", "9")) else f"sz{code}"


# ═══════════════════════════════════════════════════════════
# 第1层: 实时行情 (TDX TCP → 腾讯 → 新浪)
# ═══════════════════════════════════════════════════════════

def get_tencent_quotes(codes: list) -> dict:
    """腾讯批量行情 — 不封IP, 主力估值数据源(PE/PB/市值)"""
    if not codes:
        return {}
    result = {}
    BATCH_SIZE = 300
    for i in range(0, len(codes), BATCH_SIZE):
        batch = codes[i:i + BATCH_SIZE]
        prefixed = [_prefix(c) for c in batch]
        url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            data = urllib.request.urlopen(req, timeout=15).read().decode("gbk", errors="replace")
            for line in data.strip().split(";"):
                if "=" not in line or '"' not in line:
                    continue
                key = line.split("=")[0].split("_")[-1]
                vals = line.split('"')[1].split("~")
                if len(vals) < 53:
                    continue
                code = key[2:]
                result[code] = {
                    "code": code, "name": vals[1],
                    "price": float(vals[3]) if vals[3] else 0,
                    "last_close": float(vals[4]) if vals[4] else 0,
                    "open": float(vals[5]) if vals[5] else 0,
                    "high": float(vals[33]) if vals[33] else 0,
                    "low": float(vals[34]) if vals[34] else 0,
                    "change_pct": float(vals[32]) if vals[32] else 0,
                    "pe": float(vals[39]) if vals[39] else 0,
                    "mcap": float(vals[44]) if vals[44] else 0,
                    "float_mcap": float(vals[45]) if vals[45] else 0,
                    "turnover": float(vals[38]) if vals[38] else 0,
                    "vol_ratio": float(vals[49]) if vals[49] else 0,
                    "pb": float(vals[46]) if vals[46] else 0,
                    "limit_up": float(vals[47]) if vals[47] else 0,
                    "limit_down": float(vals[48]) if vals[48] else 0,
                    "amplitude": float(vals[43]) if vals[43] else 0,
                    "amount_wan": float(vals[37]) if vals[37] else 0,
                }
        except Exception as e:
            logger.warning(f"腾讯行情批次{i // BATCH_SIZE + 1}失败: {e}")
            continue
    logger.info(f"[Tencent] {len(result)}/{len(codes)} quotes")
    return result


def get_sina_quotes(codes: list) -> dict:
    """新浪行情 — 腾讯备选"""
    if not codes:
        return {}
    prefixed = []
    for c in codes:
        c = c.strip()
        if c.startswith(("sh", "sz", "bj")):
            prefixed.append(c)
        elif c.startswith(("6", "9")):
            prefixed.append("sh" + c)
        elif c.startswith(("8", "4")):
            prefixed.append("bj" + c)
        else:
            prefixed.append("sz" + c)
    url = "http://hq.sinajs.cn/list=" + ",".join(prefixed)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                     "Referer": "https://finance.sina.com.cn"})
        data = urllib.request.urlopen(req, timeout=5).read().decode("gbk", errors="replace")
    except Exception as e:
        logger.warning(f"Sina quotes failed: {e}")
        return {}
    result = {}
    for line in data.strip().split(";"):
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
            result[code] = {
                "code": code, "name": name,
                "price": float(parts[3]) if parts[3] else 0,
                "close_y": float(parts[2]) if parts[2] else 0,
                "change": round(float(parts[3]) - float(parts[2]), 2) if parts[2] and parts[3] else 0,
                "change_pct": round((float(parts[3]) - float(parts[2])) / float(parts[2]) * 100, 2) if parts[2] and parts[3] else 0,
                "open": float(parts[1]) if parts[1] else 0,
                "high": float(parts[4]) if parts[4] else 0,
                "low": float(parts[5]) if parts[5] else 0,
                "volume": int(parts[8]) if parts[8] else 0,
                "amount": float(parts[9]) if parts[9] else 0,
            }
        except (IndexError, ValueError):
            continue
    if result:
        logger.info(f"[Sina] {len(result)}/{len(codes)} quotes")
    return result


# ═══════════════════════════════════════════════════════════
# 第2层: K线数据 (TDX TCP → 腾讯 → 新浪)
# ═══════════════════════════════════════════════════════════

def _get_kline_from_tencent(code: str, days: int = 250) -> pd.DataFrame:
    """腾讯日K — 主力K线源"""
    import requests
    pfx = _prefix(code)
    url = f"https://ifzq.gtimg.cn/appstock/app/fqkline/get?param={pfx},day,,,{days},qfq"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=10)
        data = r.json().get("data", {}).get(pfx, {})
        raw = data.get("qfqday", []) or data.get("day", [])
        if not raw:
            return pd.DataFrame()
        rows = [{"date": d[0], "open": float(d[1]), "close": float(d[2]),
                 "high": float(d[3]), "low": float(d[4]), "volume": float(d[5])} for d in raw]
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception as e:
        logger.debug(f"腾讯K线 {code}: {e}")
        return pd.DataFrame()


# ── 全局TDX可用状态(防止每次K线请求都尝试连接) ──
_TDX_AVAILABLE = True

def _get_kline_from_tdx(code: str, days: int = 500) -> pd.DataFrame:
    """TDX TCP K线 — 首选K线源(零外部依赖)"""
    global _TDX_AVAILABLE
    if not _TDX_AVAILABLE:
        return pd.DataFrame()
    try:
        from data.tdx_sources import get_tdx_kline
        df = get_tdx_kline(code, days=days)
        if df is not None and not df.empty:
            return df
    except Exception as e:
        logger.debug(f"TDX K线 {code}: {e}")
    _TDX_AVAILABLE = False
    logger.info("[TDX] K-line unavailable, falling back to Tencent HTTP")
    return pd.DataFrame()


def get_kline(code: str, days: int = 500) -> pd.DataFrame:
    """
    获取K线(含缓存 + 三级降级):
      1. SharedDataCache
      2. TDX TCP (首选)
      3. 腾讯 HTTP (备选)
      4. 新浪 (最后备选)
    """
    # Cache check
    try:
        from data.shared_cache import cache as _ck
        cached = _ck.get(f"kline_{code}_{days}")
        if cached is not None:
            return cached
    except:
        pass

    df = _get_kline_from_tdx(code, days)
    if df is not None and not df.empty:
        try:
            from data.shared_cache import cache as _ck
            _ck.set(f"kline_{code}_{days}", df, 60)
        except:
            pass
        return df

    df = _get_kline_from_tencent(code, days)
    if df is not None and not df.empty:
        try:
            from data.shared_cache import cache as _ck
            _ck.set(f"kline_{code}_{days}", df, 60)
        except:
            pass
        return df

    logger.warning(f"K线 {code}: 所有数据源失败")
    return pd.DataFrame()


def get_kline_period(code: str, period: str = "day", days: int = 250) -> pd.DataFrame:
    """多周期K线: day/week/month + 5min/30min/60min — 腾讯/新浪"""
    if period == "day":
        return get_kline(code, days)

    import requests
    pfx = _prefix(code)
    minute_map = {"5min": "m5", "15min": "m15", "30min": "m30", "60min": "m60"}
    if period in minute_map:
        mp = minute_map[period]
        url = f"https://ifzq.gtimg.cn/appstock/app/kline/mkline?param={pfx},{mp},,{days}"
        try:
            r = requests.get(url, headers={"User-Agent": UA, "Referer": "https://finance.qq.com"}, timeout=10)
            data = r.json().get("data", {}).get(pfx, {}).get(mp, [])
            if not data:
                data = r.json().get("data", {}).get(pfx, {}).get("qt", {}).get(pfx, [])
            rows = []
            for d in data:
                if isinstance(d, list) and len(d) >= 6:
                    try:
                        rows.append({"date": str(d[0]), "open": float(d[1]), "close": float(d[2]),
                                     "high": float(d[3]), "low": float(d[4]), "volume": float(d[5])})
                    except (ValueError, IndexError):
                        continue
            if rows:
                df = pd.DataFrame(rows)
                df["date"] = pd.to_datetime(df["date"])
                return df
        except Exception as e:
            logger.warning(f"分钟K线 {code} {period}: {e}")
        return pd.DataFrame()

    # 日/周/月
    period_map = {"day": "day", "week": "week", "month": "month"}
    p = period_map.get(period, "day")
    url = f"https://ifzq.gtimg.cn/appstock/app/fqkline/get?param={pfx},{p},,,{days},qfq"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=10)
        data = r.json().get("data", {}).get(pfx, {})
        keys = {"day": "qfqday", "week": "qfqweek", "month": "qfqmonth"}
        raw = data.get(keys.get(p, "qfqday"), []) or data.get(p, [])
        if not raw:
            return pd.DataFrame()
        rows = [{"date": str(d[0]), "open": float(d[1]), "close": float(d[2]),
                 "high": float(d[3]), "low": float(d[4]), "volume": float(d[5]) if len(d) > 5 else 0}
                for d in raw]
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception as e:
        logger.warning(f"K线 {code} {period}: {e}")
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════
# 第3层: 指数 + 市场广度
# ═══════════════════════════════════════════════════════════

def get_index_snapshot(codes):
    """指数快照 — 腾讯"""
    idx_map = {"000001": "sh000001", "399001": "sz399001", "399006": "sz399006",
               "000688": "sh000688", "000300": "sh000300"}
    mapped = [idx_map.get(c, _prefix(c) + c) for c in codes]
    if not mapped:
        return {}
    url = "https://qt.gtimg.cn/q=" + ",".join(mapped)
    try:
        data = urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": UA}), timeout=10
        ).read().decode("gbk", "replace")
    except Exception as e:
        logger.warning(f"Index fail: {e}")
        return {}
    result = {}
    for line in data.strip().split(";"):
        if "=" not in line:
            continue
        parts = line.split("=")
        key = parts[0].split("_")[-1]
        if '"' not in parts[1]:
            continue
        vals = parts[1].split('"')[1].split("~")
        if len(vals) < 3:
            continue
        c2 = key[2:] if key[:2] in ("sh", "sz") else key
        result[c2] = {
            "code": c2, "name": vals[1],
            "price": float(vals[3]) if vals[3] else 0,
            "change_pct": float(vals[32]) if len(vals) > 32 and vals[32] else 0,
        }
    return result


def get_market_breadth() -> dict:
    """市场广度: 涨跌比 — 腾讯分层采样 (v14.41: 修复advance_ratio键+扩大采样至1000只)"""
    try:
        codes = get_real_stock_list()
        # 分层采样: 前200大市值 + 中间300 + 后500小市值 (覆盖大/中/小市值, 避免权重股偏差)
        n = len(codes)
        if n > 1000:
            sample = codes[:200] + codes[n // 2 - 150:n // 2 + 150] + codes[-500:]
        else:
            sample = codes[:200]
        quotes = get_tencent_quotes(sample)
        if not quotes:
            return {"ad_score": 0, "up_count": 0, "down_count": 0, "advance_ratio": 0.5,
                    "total_sampled": 0}
        changes = [q.get("change_pct", 0) for q in quotes.values()]
        up = sum(1 for c in changes if c > 0)
        down = sum(1 for c in changes if c < 0)
        total = up + down or 1
        ratio = up / total
        return {"ad_score": int(min(max((ratio - 0.3) / 0.4 * 60, 0), 60)),
                "up_count": up, "down_count": down,
                "advance_ratio": round(ratio, 3), "total_sampled": len(quotes)}
    except Exception as e:
        logger.warning(f"Breadth fail: {e}")
        return {"ad_score": 0, "up_count": 0, "down_count": 0, "advance_ratio": 0.5,
                "total_sampled": 0}


# ═══════════════════════════════════════════════════════════
# 第4层: 股票列表 (巨潮6222 → TDX → Sina → 硬编码备用)
# ═══════════════════════════════════════════════════════════

STOCK_CACHE = Path(__file__).resolve().parent.parent / "data" / "stock_cache.json"
STOCK_CACHE_TTL = 1800  # 30分钟(全市场列表一天不变)

def _fallback_stock_list() -> list:
    """硬编码200只重点股票 — 终极降级"""
    return [
        "000001", "000002", "000333", "000568", "000625", "000651", "000725",
        "000733", "000768", "000792", "000858", "000938", "000983", "001979",
        "002007", "002049", "002129", "002230", "002236", "002241",
        "002304", "002352", "002371", "002415", "002459", "002460", "002466",
        "002475", "002493", "002594", "002601", "002709", "002714", "002812",
        "002920", "002938", "300014", "300015", "300059", "300124",
        "300274", "300308", "300413", "300433", "300450", "300502", "300661",
        "300750", "300751", "300760", "300782", "300999",
        "600000", "600010", "600011", "600016", "600019", "600025", "600028",
        "600030", "600031", "600036", "600048", "600050", "600085", "600089",
        "600104", "600111", "600115", "600150", "600188", "600196",
        "600276", "600309", "600340", "600346", "600362", "600406", "600436",
        "600438", "600482", "600487", "600519", "600522", "600536", "600570",
        "600585", "600588", "600690", "600703", "600732", "600745", "600809",
        "600886", "600887", "600893", "600900", "600919", "600926",
        "600941", "600958", "600989", "600999",
        "601012", "601066", "601088", "601111", "601127", "601138",
        "601166", "601169", "601186", "601211", "601216", "601225", "601229",
        "601236", "601288", "601318", "601328", "601336", "601360", "601377",
        "601390", "601398", "601600", "601601", "601607", "601615",
        "601618", "601628", "601633", "601658", "601669", "601688", "601689",
        "601728", "601766", "601788", "601800", "601818", "601857", "601872",
        "601877", "601878", "601881", "601888", "601899", "601901",
        "601919", "601939", "601958", "601966", "601985", "601988", "601989",
        "601990", "601992", "601995",
        "603019", "603195", "603259", "603288", "603369", "603392", "603501",
        "603659", "603799", "603986", "605117",
        "688008", "688009", "688012", "688036", "688065", "688111", "688126",
        "688169", "688180", "688187", "688200", "688256", "688303", "688347",
        "688363", "688396", "688469", "688488", "688516",
        "688520", "688533", "688536", "688599", "688660", "688728", "688766",
        "688777", "688819", "688981",
    ]


def _sina_stock_list() -> list:
    """新浪股票列表(~1200只)"""
    import requests as req
    codes = []
    nodes = {"sh_a": "6", "sz_a": "0", "cyb": "3"}
    for node in nodes:
        for pn in range(1, 5):
            try:
                url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
                r = req.get(url, params={"page": pn, "num": 100, "sort": "code", "asc": "1", "node": node}, timeout=10)
                items = r.json() if isinstance(r.json(), list) else []
                chunk = [it["code"] for it in items if isinstance(it, dict) and len(it.get("code", "")) == 6]
                codes.extend(chunk)
                if len(items) < 100:
                    break
            except Exception:
                break
    logger.info(f"[Sina] {len(codes)} codes fallback")
    return codes if codes else _fallback_stock_list()


def _cninfo_stock_list() -> list:
    """巨潮证券列表(6222只, 全市场最全)"""
    import requests as req
    try:
        r = req.get("http://www.cninfo.com.cn/new/data/szse_stock.json",
                    headers={"User-Agent": UA}, timeout=15)
        stock_data = r.json().get("stockList", [])
        codes = list(dict.fromkeys(
            s["code"] for s in stock_data if len(str(s.get("code", ""))) == 6
        ))
        if codes and len(codes) > 1000:
            logger.info(f"[CNINFO] {len(codes)} stocks")
            return codes
    except Exception as e:
        logger.debug(f"CNINFO fail: {e}")
    return []


def get_real_stock_list() -> list:
    """
    获取全市场股票列表(含缓存, 优先巨潮6222):
      1. 缓存 (5min TTL)
      2. 巨潮 CNINFO (6222只, 全市场最全)
      3. TDX TCP (～5000只)
      4. Sina (～1200只)
      5. 硬编码200只 (终极降级)
    """
    import json as _j
    # Cache
    try:
        if STOCK_CACHE.exists():
            data = _j.loads(STOCK_CACHE.read_text())
            if time.time() - data.get("time", 0) < STOCK_CACHE_TTL:
                cached = data["codes"]
                # v14.41: 缓存路径同样过滤B股
                if any(c.startswith(("20", "90")) for c in cached[:50]):
                    cached = [c for c in cached if not c.startswith(("20", "90"))]
                logger.info(f"[Cache] {len(cached)} stocks")
                return cached
    except Exception:
        pass

    codes = []

    # 1. 巨潮 (全市场最全)
    codes = _cninfo_stock_list()
    if len(codes) >= 4000:
        # v14.41: 过滤B股(20深B/90沪B非A股), 保留92北交所
        codes = [c for c in codes if not c.startswith(("20", "90"))]
        try:
            STOCK_CACHE.write_text(_j.dumps({"time": time.time(), "codes": codes}))
        except Exception:
            pass
        return codes

    # 2. TDX TCP
    try:
        from data.tdx_sources import get_tdx_stock_list
        codes = get_tdx_stock_list()
        if codes and len(codes) >= 4000:
            logger.info(f"[TDX] {len(codes)} stocks")
            try:
                STOCK_CACHE.write_text(_j.dumps({"time": time.time(), "codes": codes}))
            except Exception:
                pass
            return codes
    except Exception as e:
        logger.warning(f"TDX stock list fail: {e}")

    # 3. Sina
    codes = _sina_stock_list()
    if codes and len(codes) >= 1000:
        try:
            STOCK_CACHE.write_text(_j.dumps({"time": time.time(), "codes": codes}))
        except Exception:
            pass
        return codes

    # 4. 硬编码
    logger.warning("[StockList] 所有数据源失败,使用硬编码200只")
    return _fallback_stock_list()


# ═══════════════════════════════════════════════════════════
# 第5层: 行业板块 (东财 → 缓存 → 静态默认)
# ═══════════════════════════════════════════════════════════

SECTOR_CACHE = Path(__file__).resolve().parent.parent / "data" / "sector_cache.json"
SECTOR_CACHE_TTL = 1800  # 30分钟(盘中板块轮动变化快)
FLOW_CACHE_FILE = Path(__file__).resolve().parent.parent / "data" / "flow_cache.json"
FLOW_CACHE_TTL = 3600  # 1小时

DEFAULT_SECTORS = [
    {"name": "银行", "code": "BK0475", "change_pct": 0, "up": 0, "down": 0, "leader": ""},
    {"name": "证券", "code": "BK0473", "change_pct": 0, "up": 0, "down": 0, "leader": ""},
    {"name": "保险", "code": "BK0474", "change_pct": 0, "up": 0, "down": 0, "leader": ""},
    {"name": "半导体", "code": "BK1036", "change_pct": 0, "up": 0, "down": 0, "leader": ""},
    {"name": "酿酒行业", "code": "BK0477", "change_pct": 0, "up": 0, "down": 0, "leader": ""},
    {"name": "医药制造", "code": "BK0465", "change_pct": 0, "up": 0, "down": 0, "leader": ""},
    {"name": "汽车零部件", "code": "BK0481", "change_pct": 0, "up": 0, "down": 0, "leader": ""},
    {"name": "电力行业", "code": "BK0428", "change_pct": 0, "up": 0, "down": 0, "leader": ""},
    {"name": "航空机场", "code": "BK0430", "change_pct": 0, "up": 0, "down": 0, "leader": ""},
    {"name": "电池", "code": "BK1033", "change_pct": 0, "up": 0, "down": 0, "leader": ""},
    {"name": "光伏设备", "code": "BK1011", "change_pct": 0, "up": 0, "down": 0, "leader": ""},
    {"name": "软件开发", "code": "", "change_pct": 0, "up": 0, "down": 0, "leader": ""},
    {"name": "通信设备", "code": "BK0448", "change_pct": 0, "up": 0, "down": 0, "leader": ""},
    {"name": "化学制药", "code": "BK0468", "change_pct": 0, "up": 0, "down": 0, "leader": ""},
    {"name": "军工", "code": "BK0480", "change_pct": 0, "up": 0, "down": 0, "leader": ""},
    {"name": "有色金属", "code": "BK0478", "change_pct": 0, "up": 0, "down": 0, "leader": ""},
    {"name": "煤炭", "code": "BK0437", "change_pct": 0, "up": 0, "down": 0, "leader": ""},
    {"name": "物流", "code": "BK0454", "change_pct": 0, "up": 0, "down": 0, "leader": ""},
    {"name": "工程建设", "code": "BK0423", "change_pct": 0, "up": 0, "down": 0, "leader": ""},
    {"name": "文化传媒", "code": "BK0457", "change_pct": 0, "up": 0, "down": 0, "leader": ""},
    {"name": "互联网服务", "code": "BK0449", "change_pct": 0, "up": 0, "down": 0, "leader": ""},
    {"name": "钢铁", "code": "BK0478", "change_pct": 0, "up": 0, "down": 0, "leader": ""},
]


def _save_sector_cache(sectors):
    try:
        SECTOR_CACHE.parent.mkdir(parents=True, exist_ok=True)
        import json as _j
        _j.dump({"sectors": sectors[:30]}, open(SECTOR_CACHE, "w", encoding="utf-8"))
    except:
        pass


def _load_sector_cache() -> list:
    try:
        if SECTOR_CACHE.exists():
            import json as _j
            mtime = SECTOR_CACHE.stat().st_mtime
            if time.time() - mtime > SECTOR_CACHE_TTL:
                logger.debug(f"[Sector] Cache expired")
                return []
            return _j.load(open(SECTOR_CACHE, encoding="utf-8")).get("sectors", [])
    except:
        pass
    return []


def _save_flow_cache(data):
    try:
        FLOW_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        import json as _j
        _j.dump(data, open(FLOW_CACHE_FILE, "w", encoding="utf-8"))
    except:
        pass


def _load_flow_cache():
    try:
        if FLOW_CACHE_FILE.exists():
            import json as _j
            return _j.load(open(FLOW_CACHE_FILE, encoding="utf-8"))
    except:
        pass
    return {}


def get_sector_ranking(top_n: int = 50) -> list:
    """
    行业板块排名 — 东财(唯一有) → 同花顺热点(MCP) → 缓存 → 静态默认
    """
    import requests
    for attempt in range(2):
        try:
            url = "https://push2.eastmoney.com/api/qt/clist/get"
            params = {"pn": "1", "pz": str(top_n), "po": "1", "np": "1",
                      "fltt": "2", "invt": "2", "fs": "m:90+t:2",
                      "fields": "f2,f3,f4,f12,f14,f104,f105,f128"}
            if attempt == 0:
                time.sleep(1.2)
            r = requests.get(url, params=params,
                             headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}, timeout=15)
            items = r.json().get("data", {}).get("diff", []) or []
            result = [{"name": it.get("f14", ""), "code": it.get("f12", ""),
                       "change_pct": it.get("f3", 0), "up": it.get("f104", 0),
                       "down": it.get("f105", 0), "leader": it.get("f128", "")}
                      for it in items]
            if result:
                _save_sector_cache(result)
                return result
        except Exception as e:
            if attempt == 0:
                logger.warning(f"板块数据失败(重试): {e}")
                time.sleep(2)
            else:
                logger.warning(f"板块数据失败: {e}")

    # 降级2: MCP/同花顺热点
    try:
        from data.mcp_sources import get_sectors_via_mcp
        mcp_sectors = get_sectors_via_mcp(top_n)
        if mcp_sectors and len(mcp_sectors) > 0 and mcp_sectors[0].get("name"):
            logger.info(f"[Sector] Using 同花顺热点 ({len(mcp_sectors)} sectors)")
            return mcp_sectors
    except Exception as e:
        logger.debug(f"[Sector] MCP fallback failed: {e}")

    # 降级3: 缓存(有效期内)
    cached = _load_sector_cache()
    if cached:
        logger.info(f"[Sector] Using cached ({len(cached)} sectors)")
        return cached

    # 降级4: 静态默认
    logger.warning("[Sector] 所有数据源失败,使用静态默认板块")
    return DEFAULT_SECTORS


def get_top_flow_stocks(top_n=200):
    """资金流向排名(东财) — 东财 → 缓存 → Sina量比近似"""
    import requests as req
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {"pn": 1, "pz": top_n, "po": 1, "np": 1, "fltt": 2, "invt": 2,
                  "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23", "fields": "f12,f62", "fid": "f62"}
        r = req.get(url, params=params, headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}, timeout=15)
        items = r.json().get("data", {}).get("diff", []) or []
        result = {}
        for it in items:
            c_code = str(it.get("f12", ""))
            if len(c_code) == 6:
                result[c_code] = it.get("f62", 0)
        if result:
            _save_flow_cache(result)
            logger.info(f"[Flow] {len(result)} stocks with inflow data")
            return result
        cached = _load_flow_cache()
        if cached:
            logger.info(f"[Flow] Cache hit: {len(cached)} stocks")
            return cached
    except Exception as e:
        logger.warning(f"Flow Eastmoney fail: {e}")
        cached = _load_flow_cache()
        if cached:
            logger.info(f"[Flow] Cache hit: {len(cached)} stocks")
            return cached

    # 降级: Sina量比近似(vol_ratio > 2.0)
    try:
        logger.info("[Flow] Trying Sina vol_ratio fallback")
        stock_list = get_real_stock_list()
        if not stock_list:
            stock_list = _fallback_stock_list()
        quotes = get_tencent_quotes(stock_list[:200])
        if quotes:
            result = {}
            for code, q in quotes.items():
                vol_ratio = q.get("vol_ratio", 0)
                if vol_ratio > 2.0:
                    result[code] = vol_ratio * 1000000
            if result:
                result = dict(sorted(result.items(), key=lambda x: x[1], reverse=True)[:top_n])
                logger.info(f"[Flow] Sina fallback: {len(result)} stocks with vol_ratio>2.0")
                return result
    except Exception as e2:
        logger.warning(f"Flow Sina fallback also failed: {e2}")
    return {}


def get_top_sectors(top_n=5):
    """获取涨幅前N行业板块"""
    sectors = get_sector_ranking(100)
    if not sectors:
        fb = ["化学制药", "半导体", "软件服务", "汽车整车", "银行",
              "证券", "食品饮料", "白酒", "国防军工", "电力设备"]
        logger.info(f"[Sector] Hardcoded fallback: {fb[:top_n]}")
        return fb[:top_n]
    sectors.sort(key=lambda s: s.get("change_pct", 0), reverse=True)
    top = [s["name"] for s in sectors[:top_n] if s.get("name")]
    logger.info(f"[Sector] Top {top_n}: {top}")
    return top


def get_limit_up_count():
    """获取涨停股票数量(近似) — v14.41: 东财push2被WAF屏蔽, 改用腾讯全市场采样统计
    涨停判定: 主板涨幅>=9.8%, 创业板/科创板>=19.5% (近似, 采样2000只)
    """
    try:
        # 腾讯批量查询全市场股票, 统计涨幅达涨停阈值的数量
        codes = get_real_stock_list()
        if not codes:
            return 0
        # 采样: 前500 + 中500 + 后1000, 覆盖大中小市值
        n = len(codes)
        sample = codes[:500] + codes[n // 2 - 250:n // 2 + 250] + codes[-1000:]
        quotes = get_tencent_quotes(sample)
        if not quotes:
            return 0
        cnt = 0
        for c, q in quotes.items():
            chg = q.get("change_pct", 0) or 0
            # 创业板(30x)/科创板(68x)涨停20%, 主板10%, 北交所(8/4开头)30%
            if c.startswith(("30", "68")):
                if chg >= 19.5:
                    cnt += 1
            elif c.startswith(("8", "4")):
                if chg >= 29.5:
                    cnt += 1
            else:
                if chg >= 9.8:
                    cnt += 1
        # 采样2000只覆盖约1/3市场, 按比例外推
        ratio = len(sample) / max(n, 1)
        return int(cnt / ratio) if ratio > 0 else cnt
    except Exception:
        return 0


# ═══════════════════════════════════════════════════════════
# 第6层: 数据质量检查
# ═══════════════════════════════════════════════════════════

_CACHE_TTL = 3600
_cache_timestamps = {}

def _check_cache_ttl(cache_key: str, ttl: int = _CACHE_TTL) -> bool:
    now = time.time()
    return (now - _cache_timestamps.get(cache_key, 0)) < ttl

def _update_cache_ts(cache_key: str):
    _cache_timestamps[cache_key] = time.time()

def validate_kline_data(df, code: str = "") -> dict:
    """K线数据质量检查"""
    import numpy as np
    issues = []
    if df is None:
        return {"valid": False, "issues": ["DataFrame is None"], "code": code}
    if df.empty:
        return {"valid": False, "issues": ["Empty DataFrame"], "code": code}

    close = df["close"].values if "close" in df.columns else None
    vol = df["volume"].values if "volume" in df.columns else None
    high = df["high"].values if "high" in df.columns else None
    low = df["low"].values if "low" in df.columns else None

    if close is not None and np.any(np.isnan(close)):
        issues.append("close列含NaN")
    if vol is not None and np.any(np.isnan(vol)):
        issues.append("volume列含NaN")
    if close is not None and np.any(close <= 0):
        issues.append("存在<=0的收盘价")
    if close is not None and np.any(np.abs(np.diff(close) / close[:-1]) > 0.20):
        issues.append("存在单日涨跌幅>20%的异常数据")
    if high is not None and low is not None:
        if np.any(high < low):
            issues.append("high<low的数据行")
    if vol is not None and len(vol) >= 5 and np.any(vol < 0):
        issues.append("存在负成交量")

    return {"valid": len(issues) == 0, "issues": issues, "code": code, "rows": len(df)}


# ═══════════════════════════════════════════════════════════
# 第7层: 概念板块 / 龙虎榜 / EPS一致预期
# ═══════════════════════════════════════════════════════════


def _em_secid(code: str) -> str:
    """6位代码 → 东财secid格式 (market.code)"""
    market = "1" if code.startswith(("6", "9")) else "0"
    return f"{market}.{code}"


def get_concept_blocks(code: str) -> list:
    """
    个股所属概念板块 (东财slist API, 零鉴权)

    URL: https://push2.eastmoney.com/api/qt/slist/get
    params: secid=market.code, spt=3

    Returns:
        [{name, code(BK码), change_pct, lead_stock}, ...]
    """
    import requests as _req
    try:
        secid = _em_secid(code)
        time.sleep(2.0)  # 东财限流
        url = "https://push2.eastmoney.com/api/qt/slist/get"
        params = {
            "fltt": "2", "invt": "2",
            "secid": secid, "spt": "3",
            "pi": "0", "pz": "200", "po": "1",
            "fields": "f12,f14,f3,f128",
        }
        r = _req.get(url, params=params,
                     headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"},
                     timeout=15)
        data = r.json()
        if data.get("rc", 0) != 0:
            logger.debug(f"[ConceptBlocks] {code}: rc={data.get('rc')}, err={str(data.get('data',''))[:100]}")
            return []

        raw = data.get("data", {}) or {}
        diff = raw.get("diff", []) or []
        if isinstance(diff, dict):
            diff = list(diff.values())
        result = []
        for item in diff:
            result.append({
                "name": item.get("f14", ""),
                "code": item.get("f12", ""),
                "change_pct": item.get("f3", 0),
                "lead_stock": item.get("f128", ""),
            })
        logger.info(f"[ConceptBlocks] {code}: {len(result)} blocks")
        return result
    except Exception as e:
        logger.warning(f"[ConceptBlocks] {code}: {e}")
        return []


def get_dragon_tiger_board(trade_date: str = None) -> list:
    """
    全市场龙虎榜 (东财 datacenter API)

    URL: https://datacenter-web.eastmoney.com/api/data/v1/get
    params: reportName=RPT_DAILYBILLBOARD_DETAILSNEW

    Args:
        trade_date: 交易日 YYYY-MM-DD, 不传则查最新

    Returns:
        [{code, name, reason(上榜原因), net_buy_wan(净买额万),
          change_pct, turnover_pct}, ...]
    """
    import requests as _req
    try:
        time.sleep(1.2)
        url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
        params = {
            "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
            "columns": "SECURITY_CODE,SECURITY_NAME_ABBR,TRADE_DATE,CHANGE_RATE,"
                       "TURNOVERRATE,EXPLAIN,CLOSE_PRICE,BILLBOARD_NET_AMT",
            "pageSize": 100,
            "pageNumber": 1,
            "sortTypes": -1,
            "sortColumns": "BILLBOARD_NET_AMT",
            "source": "WEB",
            "client": "WEB",
        }
        if trade_date:
            params["filter"] = f'(TRADE_DATE=\'{trade_date}\')'
        r = _req.get(url, params=params,
                     headers={"User-Agent": UA, "Referer": "https://data.eastmoney.com/"},
                     timeout=15)
        data = r.json()
        if not data.get("success"):
            logger.warning(f"[DragonTiger] API返回失败: {data.get('message', data)}")
            return []

        items = data.get("result", {}).get("data", []) or []
        result = []
        for item in items:
            # 净买额从 BILLBOARD_NET_AMT 字段获取
            net_amt = item.get("BILLBOARD_NET_AMT") or 0
            try:
                net_buy = round(float(net_amt) / 10000, 1) if float(net_amt) != 0 else 0
            except (ValueError, TypeError):
                net_buy = 0
            result.append({
                "code": item.get("SECURITY_CODE", ""),
                "name": item.get("SECURITY_NAME_ABBR", ""),
                "reason": item.get("EXPLAIN", ""),
                "net_buy_wan": net_buy,
                "change_pct": item.get("CHANGE_RATE", 0) or 0,
                "turnover_pct": item.get("TURNOVERRATE", 0) or 0,
            })
        logger.info(f"[DragonTiger] {len(result)} records")
        return result
    except Exception as e:
        logger.warning(f"[DragonTiger] Failed: {e}")
        return []


def get_eps_forecast(code: str) -> dict:
    """
    同花顺机构一致预期EPS (直连 basic.10jqka.com.cn)
    解析HTML表格, 提取今年EPS, 明年EPS, 后年EPS, 覆盖机构数

    Returns:
        {eps_cur, eps_next, eps_next2, analyst_count}
    """
    import requests as _req
    try:
        # 63->SH主板/科创板, 52->SZ主板/创业板
        prefix = "63" if code.startswith(("6", "9")) else "52"

        # 尝试两个页面: operate.html(财务分析) 和 主页
        pages = [
            f"http://basic.10jqka.com.cn/{prefix}/{code}/operate.html",
            f"http://basic.10jqka.com.cn/{prefix}/{code}/",
        ]
        result = {"eps_cur": 0, "eps_next": 0, "eps_next2": 0, "analyst_count": 0}

        for page_url in pages:
            try:
                r = _req.get(page_url,
                             headers={"User-Agent": UA, "Referer": "https://www.10jqka.com.cn/"},
                             timeout=15)
                r.encoding = "utf-8"
                html = r.text
            except Exception:
                continue

            # ── Pattern 1: 每股收益(元) 表格行 ──
            # <td>每股收益(元)</td><td>1.23</td><td>1.45</td><td>1.67</td>
            m = _re.search(
                r'每股收益\s*[（(]\s*元\s*[）)]?\s*</td>\s*<td[^>]*>\s*(\d+(?:\.\d+)?)\s*</td>\s*<td[^>]*>\s*(\d+(?:\.\d+)?)\s*</td>\s*<td[^>]*>\s*(\d+(?:\.\d+)?)\s*</td>',
                html, _re.IGNORECASE
            )
            if m:
                eps_vals = [float(m.group(1)), float(m.group(2)), float(m.group(3))]
                result["eps_cur"] = eps_vals[0]
                result["eps_next"] = eps_vals[1]
                result["eps_next2"] = eps_vals[2]

                # ── 找预测机构数 ──
                m2 = _re.search(
                    r'预测机构数\s*</td>\s*<td[^>]*>\s*(\d+)\s*</td>',
                    html, _re.IGNORECASE
                )
                if m2:
                    result["analyst_count"] = int(m2.group(1))

                logger.info(f"[EPS Forecast] {code}: cur={result['eps_cur']}, "
                            f"next={result['eps_next']}, next2={result['eps_next2']}, "
                            f"analysts={result['analyst_count']}")
                return result

            # ── Pattern 2: "预测" + 数字(元) 行 ──
            m = _re.search(
                r'预测每股收益[^\d]*?(\d+(?:\.\d+)?)\s*[^\d]*?(\d+(?:\.\d+)?)\s*[^\d]*?(\d+(?:\.\d+)?)',
                html, _re.IGNORECASE
            )
            if m:
                result["eps_cur"] = float(m.group(1))
                result["eps_next"] = float(m.group(2))
                result["eps_next2"] = float(m.group(3))
                logger.info(f"[EPS Forecast] {code}: cur={result['eps_cur']}, "
                            f"next={result['eps_next']}, next2={result['eps_next2']}")
                return result

        # 两个页面都没找到
        logger.debug(f"[EPS Forecast] {code}: 未找到EPS预测数据")
        return result

    except Exception as e:
        logger.warning(f"[EPS Forecast] {code}: {e}")
        return {"eps_cur": 0, "eps_next": 0, "eps_next2": 0, "analyst_count": 0}
