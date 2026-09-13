# -*- coding: utf-8 -*-
"""
datafeed.py — 数据层（limitup-system）

数据源（按技能库实测优先级）：
  1. 新浪 K线 HTTP  API   — 日K/分钟K（字段全为字符串，必须 float()）
  2. 新浪 Market_Center   — 全市场列表（选股/昨收 settlement）
  3. 腾讯 qt.gtimg.cn     — 批量实时行情（昨收 parts[4]，GBK 编码，不封 IP）

关键坑（技能库实测沉淀）：
  - 新浪 K 线字段名是 'day'（不是 'date'），所有数值是字符串
  - 新浪 K 线 URL 是 quotes_service/api/json_v2.php/CN_MarketData.getKLineData
  - 腾讯行情 GBK 编码，字段以 ~ 分隔，parts[4]=昨收
  - 指数 000001 = 平安银行，指数代码必须带 sh/sz 前缀直连
  - push2delay 全量串行防限流；本系统选股用新浪分页（稳定）
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import requests

UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}
SINA_KLINE = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
              "CN_MarketData.getKLineData")
SINA_MARKET = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
               "Market_Center.getHQNodeData")
TENCENT_QUOTE = "https://qt.gtimg.cn/q="


# ---------------------------------------------------------------- 工具 ----

def _sf(v: Any, default: float = 0.0) -> float:
    """安全转 float：技能库 _sf 模式，处理 '-' 字符串/None/str。"""
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _market_prefix(code: str) -> str:
    """市场前缀：6/5 开头→sh，0/3 开头→sz；带前缀原样返回。"""
    code = code.strip().lower()
    if code.startswith(("sh", "sz", "bj")):
        return code[:2]
    if code[0] in ("5", "6", "9"):
        return "sh"
    if code[0] in ("0", "2", "3"):
        return "sz"
    if code[0] == "4" or code.startswith("8"):  # 北交所
        return "bj"
    return "sz"


def _full_symbol(code: str) -> str:
    code = code.strip()
    if code.lower().startswith(("sh", "sz", "bj")):
        return code.lower()
    return _market_prefix(code) + code


# ---------------------------------------------------------------- 缓存 ----

class TTLCache:
    """线程安全 TTL 缓存。"""

    def __init__(self, ttl: float = 60.0):
        self._ttl = ttl
        self._data: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            ts, val = item
            if time.time() - ts > self._ttl:
                self._data.pop(key, None)
                return None
            return val

    def set(self, key: str, val: Any) -> None:
        with self._lock:
            self._data[key] = (time.time(), val)


_kline_cache = TTLCache(ttl=300)   # K线 5 分钟
_market_cache = TTLCache(ttl=60)   # 全市场列表 60 秒
_quote_cache = TTLCache(ttl=10)    # 批量实时 10 秒


# ------------------------------------------------------------ K线获取 ----

def fetch_daily_kline(code: str, count: int = 250) -> List[Dict[str, Any]]:
    """日K线（三级缓存：内存 → SQLite持久 → 网络[新浪→腾讯]）。

    返回 [{day, open, high, low, close, volume}...] 升序。
    盘后 SQLite 全天有效（日K定型），盘中 10 分钟 TTL。
    新浪 456 时自动切腾讯 qfq（qfqday 字段，volume 单位股）。
    """
    cache_key = f"daily:{code}:{count}"
    hit = _kline_cache.get(cache_key)
    if hit is not None:
        return hit
    rows, fresh = _get_kdb().get(code, count, _kline_max_age())
    if fresh and rows and len(rows) >= count:
        # ⭐ 2026-08-10: 盘中直接命中共享库（昨收定型数据选股足够, 不重拉）
        # 盘后若库内缺今日K → 增量补拉当日（一次 mootdx）, 不全量重拉（strong_pool 首tick 93s 根因）
        _last_day = rows[-1]["day"]
        _today = time.strftime("%Y-%m-%d")
        if _last_day >= _today or _is_trading_time():
            _kline_cache.set(cache_key, rows)
            return rows
        _add = _fetch_daily_tdx(code, 5)
        if _add:
            try:
                _get_kdb().put(code, _add)
            except Exception:
                pass
            rows2 = _get_kdb().get(code, count, _kline_max_age())[0]
            if rows2:
                rows = rows2
        _kline_cache.set(cache_key, rows)
        return rows
    # 主源：通达信 mootdx（TCP 不封IP，可高并发）→ 备胎：腾讯 fqkline
    time.sleep(_src_backoff("tdx"))
    try:
        rows = _fetch_daily_tdx(code, count)
        if rows:
            _src_ok("tdx")
        else:
            _src_fail_inc("tdx")
    except Exception:
        rows = []
        _src_fail_inc("tdx")
    if not rows:
        # 腾讯 fqkline 备胎（失败重试1次，快速失败不烧退避）
        for attempt in range(1):
            time.sleep(_src_backoff("tencent"))
            try:
                rows = _fetch_daily_tencent(code, count)
                if rows:
                    _src_ok("tencent")
                    break
                _src_fail_inc("tencent")
            except Exception:
                rows = []
                _src_fail_inc("tencent")
    if rows:
        _get_kdb().put(code, rows)
        _kline_cache.set(cache_key, rows)
    return rows


_tdx_tls = threading.local()


def _tdx_client():
    """mootdx 客户端 — 每线程单例（Quotes.factory 有连接状态，线程池并发不能共享）。"""
    c = getattr(_tdx_tls, "client", None)
    if c is None:
        from mootdx.quotes import Quotes
        c = Quotes.factory(market="std")
        _tdx_tls.client = c
    return c


def tdx_available() -> bool:
    try:
        import importlib.util as u
        return u.find_spec("mootdx") is not None
    except Exception:
        return False


def _fetch_daily_tdx(code: str, count: int = 250) -> List[Dict[str, Any]]:
    """通达信 mootdx 原始日K（主源，不封IP可高并发，frequency=9 日K）。

    单次最多 800 根，超过翻页(start 偏移)；按 day 去重合并后升序。
    ⚠️ vol 单位待实测（通达信协议为手，若与腾讯股不一致需 ×100）。
    """
    if not tdx_available():
        return []
    client = _tdx_client()
    merged: Dict[str, Dict[str, Any]] = {}
    start = 0
    while len(merged) < count:
        try:
            bars = client.bars(symbol=code, frequency=9, start=start, offset=800)
        except Exception:
            break
        if bars is None or len(bars) == 0:
            break
        for _, row in bars.iterrows():
            day = str(row.get("datetime"))[:10]
            if len(day) != 10:
                continue
            merged[day] = {
                "day": day,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("vol") or 0) * 100.0,   # 手 -> 股（实测对照新浪）
            }
        if len(bars) < 800:
            break
        start += 800
        if start > 20000:
            break
    rows = sorted(merged.values(), key=lambda r: r["day"])
    return rows[-count:] if rows else []


def _fetch_daily_sina(code: str, count: int) -> List[Dict[str, Any]]:
    """新浪日K（主源）。"""
    sym = _full_symbol(code)
    params = {"symbol": sym, "scale": 240, "datalen": count}
    r = requests.get(SINA_KLINE, params=params, timeout=10, headers=UA)
    raw = r.json()
    rows = []
    for it in raw or []:
        rows.append({
            "day": str(it.get("day", "")),
            "open": _sf(it.get("open")),
            "high": _sf(it.get("high")),
            "low": _sf(it.get("low")),
            "close": _sf(it.get("close")),
            "volume": _sf(it.get("volume")),
        })
    return rows


def _fetch_daily_tencent(code: str, count: int) -> List[Dict[str, Any]]:
    """腾讯 fqkline 日K备胎（新浪456时自动启用）。

    ⚠️ 实测：fqkline/get 返回 data[sym].day（不是 qfqday）；
    volume 单位是【股】（13.87M股 × 14.86 ≈ 2.06亿成交额，与东财匹配），不×100。
    数组格式 [date, open, close, high, low, volume]。
    """
    sym = _full_symbol(code)
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {"param": f"{sym},day,,,{count},qfq"}
    r = requests.get(url, params=params, timeout=10,
                     headers={"User-Agent": "Mozilla/5.0"})
    d = r.json()
    data = (d.get("data") or {}).get(sym) or {}
    raw = data.get("qfqday") or data.get("day") or []
    rows = []
    for it in raw:
        if len(it) < 6:
            continue
        rows.append({
            "day": str(it[0]),
            "open": _sf(it[1]),
            "close": _sf(it[2]),
            "high": _sf(it[3]),
            "low": _sf(it[4]),
            "volume": _sf(it[5]),   # 股（实测）
        })
    return rows


def fetch_minute_kline(code: str, scale: int = 5, count: int = 240) -> List[Dict[str, Any]]:
    """新浪分钟K线 scale=5/15/30/60。返回 [{day, open, high, low, close, volume}]。

    注意：新浪分钟K的 day 形如 '2026-08-07 10:35:00'（K线结束时间）。
    """
    cache_key = f"min:{code}:{scale}:{count}"
    hit = _kline_cache.get(cache_key)
    if hit is not None:
        return hit
    sym = _full_symbol(code)
    params = {"symbol": sym, "scale": scale, "datalen": count}
    r = requests.get(SINA_KLINE, params=params, timeout=10, headers=UA)
    raw = r.json()
    rows = []
    for it in raw or []:
        rows.append({
            "day": str(it.get("day", "")),
            "open": _sf(it.get("open")),
            "high": _sf(it.get("high")),
            "low": _sf(it.get("low")),
            "close": _sf(it.get("close")),
            "volume": _sf(it.get("volume")),
        })
    _kline_cache.set(cache_key, rows)
    return rows


# -------------------------------------------------------- 全市场列表 ----

def fetch_market_list(max_pages: int = 8, direction: str = "all") -> List[Dict[str, Any]]:
    """全市场列表（选股用）。备胎链：新浪 Market_Center → 东财 push2delay。

    direction:
      all  — 涨幅榜 + 跌幅榜各 max_pages 页（快，只覆盖两端，适合调试）
      up   - 仅涨幅榜; down - 仅跌幅榜
      full — 单方向翻页直到空，全量约 5300 只（打板选股默认）

    字段：code/name/trade(最新价)/changepercent(涨跌幅%)/settlement(昨收)/turnoverratio/amount(元)
    新浪被封(456)时自动切东财 push2delay（昨收 = price/(1+pct/100) 反推）。
    """
    cache_key = f"market:{max_pages}:{direction}"
    hit = _market_cache.get(cache_key)
    if hit is not None:
        return hit
    # 文件缓存：全量列表盘后全天有效，盘中 5 分钟 TTL
    if direction == "full":
        fc = load_json_cache(_market_cache_file())
        if fc and isinstance(fc.get("items"), list):
            age = time.time() - float(fc.get("ts", 0))
            if age < _market_file_ttl():
                _market_cache.set(cache_key, fc["items"])
                return fc["items"]
    out = _fetch_market_sina(max_pages, direction)
    if not out:
        out = _fetch_market_em()
    if out and direction == "full":
        save_json_cache(_market_cache_file(), {"ts": time.time(), "items": out})
    _market_cache.set(cache_key, out)
    return out


def _fetch_market_sina(max_pages: int, direction: str) -> List[Dict[str, Any]]:
    """新浪 Market_Center hs_a 分页列表。被封/空时返回空列表。"""
    out: List[Dict[str, Any]] = []
    seen = set()
    if direction == "full":
        asc_list = [0]
        page_limit = 200
    elif direction == "all":
        asc_list = [0, 1]
        page_limit = max_pages
    else:
        asc_list = [0 if direction == "up" else 1]
        page_limit = max_pages
    for asc in asc_list:
        for page in range(1, page_limit + 1):
            params = {
                "page": page, "num": 100, "sort": "changepercent",
                "asc": asc, "node": "hs_a", "_s_r_a": "page",
            }
            try:
                r = requests.get(SINA_MARKET, params=params, timeout=10, headers=UA)
                items = r.json()
            except Exception:
                break
            if not items:
                break
            for it in items:
                code = str(it.get("code", ""))
                if not code or code in seen:
                    continue
                seen.add(code)
                out.append({
                    "code": code,
                    "name": str(it.get("name", "")),
                    "trade": _sf(it.get("trade")),
                    "changepercent": _sf(it.get("changepercent")),
                    "settlement": _sf(it.get("settlement")),
                    "turnoverratio": _sf(it.get("turnoverratio")),
                    "amount": _sf(it.get("amount")),
                })
            time.sleep(0.12)
    return out


def _fetch_market_em() -> List[Dict[str, Any]]:
    """东财 push2delay 全量行情备胎（新浪 456 时自动启用）。

    ⚠️ 不带北交所 fs 段 + 不传 ut，否则 rc:102 返回空。
    昨收由 price/(1+pct/100) 反推（fltt=2 时 f3 已是 %）。
    """
    out: List[Dict[str, Any]] = []
    seen = set()
    url = "https://push2delay.eastmoney.com/api/qt/clist/get"
    fs = "m:0+t:6+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2"
    for page in range(1, 200):
        params = {"pn": page, "pz": 100, "po": 1, "np": "1",
                  "fltt": "2", "invt": "2", "fid": "f3", "fs": fs,
                  "fields": "f2,f3,f12,f14,f20"}
        try:
            r = requests.get(url, params=params, timeout=15,
                             headers={"User-Agent": "Mozilla/5.0"})
            d = r.json().get("data") or {}
            items = d.get("diff") or []
        except Exception:
            break
        if not items:
            break
        for it in items:
            code = str(it.get("f12") or "")
            if not code or code in seen:
                continue
            seen.add(code)
            price = _sf(it.get("f2"))
            pct = _sf(it.get("f3"))
            prev = price / (1 + pct / 100.0) if price > 0 and abs(pct) < 30 else 0.0
            out.append({
                "code": code,
                "name": str(it.get("f14") or ""),
                "trade": price,
                "changepercent": pct,
                "settlement": prev,
                "turnoverratio": 0.0,
                "amount": _sf(it.get("f20")),
            })
        time.sleep(0.05)
    return out


# -------------------------------------------------------- 批量实时 ----

def fetch_quote_batch(codes: List[str]) -> Dict[str, Dict[str, float]]:
    """腾讯 qt.gtimg.cn 批量实时行情。返回 {code: {price, prev_close, open, high, low, ...}}。

    格式：字段以 ~ 分隔，GBK 编码。
      parts[3]=现价 parts[4]=昨收 parts[5]=今开 parts[33]=最高 parts[34]=最低
      parts[32]=涨跌% parts[36]=成交量(手) parts[37]=成交额(万)
    """
    if not codes:
        return {}
    cache_key = "|".join(sorted(set(codes)))
    hit = _quote_cache.get(cache_key)
    if hit is not None:
        return hit
    syms = [_full_symbol(c) for c in codes]
    # 单次 ≤ 100 只防限流（技能库实测）
    result: Dict[str, Dict[str, float]] = {}
    for i in range(0, len(syms), 80):
        batch = syms[i:i + 80]
        url = TENCENT_QUOTE + ",".join(batch)
        try:
            r = requests.get(url, timeout=8, headers={"User-Agent": UA["User-Agent"]})
            r.encoding = "gbk"
        except Exception:
            continue
        for line in r.text.splitlines():
            m = re.search(r'="(.*)"', line)
            if not m:
                continue
            parts = m.group(1).split("~")
            if len(parts) < 35:
                continue
            # 腾讯行情内嵌代码在 parts[2]（如 600519），行头解析不可靠 → 直接用
            code = parts[2].strip()
            if not code or not code.isdigit():
                continue
            result[code] = {
                "name": parts[1] if len(parts) > 1 else "",
                "price": _sf(parts[3]),
                "prev_close": _sf(parts[4]),
                "open": _sf(parts[5]),
                "high": _sf(parts[33]),
                "low": _sf(parts[34]),
                "change_pct": _sf(parts[32]),
                "volume": _sf(parts[36]),      # 手
                "amount": _sf(parts[37]),      # 万
            }
    _quote_cache.set(cache_key, result)
    return result


# ------------------------------------------------------------ 涨跌停 ----

def limit_pct(code: str) -> float:
    """涨停幅度阈值(%)。主板 10%，创业板(300/301)/科创板(688) 20%，北交所 30%，ST 5%。"""
    c = code.strip()
    if c.startswith(("300", "301", "688")):
        return 20.0
    if c.startswith(("4", "8")):
        return 30.0
    return 10.0


def is_limit_up(row: Dict[str, Any], code: str, prev_close: Optional[float] = None) -> bool:
    """是否涨停：涨幅 ≥ 涨停阈值 - 0.2% 容差（主板 9.8% / 20cm 19.8%）。

    用 prev_close（昨收）算涨幅，不是用 open。
    """
    pc = prev_close if prev_close is not None else row.get("prev_close")
    if not pc:
        return False
    if row.get("close", 0) <= 0:
        return False
    pct = (row["close"] - pc) / pc * 100.0
    return pct >= limit_pct(code) - 0.2


def attach_prev_close(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """为升序日K列表附加每根K线的 prev_close（上一根收盘）。"""
    out = []
    prev = None
    for row in rows:
        r = dict(row)
        r["prev_close"] = prev if prev is not None else r.get("open", r.get("close", 0))
        out.append(r)
        prev = r["close"]
    return out


def limit_price_of(prev_close: float, code: str) -> float:
    """涨停价（保留2位，A股规则四舍五入）。"""
    return round(prev_close * (1 + limit_pct(code) / 100.0), 2)


def load_json_cache(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_json_cache(path: str, obj: Any) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


# -------------------------------------------------------- 持久缓存层 ----

def _cache_dir() -> str:
    """缓存目录（2026-08-10: 两项目数据完全独立 — 工作流用自己的缓存, 不共享 web 的库）。

    ⭐ 用户定调: web 工程(hunter-v2)与股票工作流(stock-workflow)是两个独立项目,
    K线/市场列表缓存各自独立维护, 不交叉读写。web 侧缓存 = limitup-system/cache（web 体系内部）。
    """
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
    os.makedirs(d, exist_ok=True)
    return d


def _market_cache_file() -> str:
    return os.path.join(_cache_dir(), "market_full.json")


def _is_trading_time() -> bool:
    now = time.localtime()
    if now.tm_wday >= 5:
        return False
    hm = now.tm_hour * 100 + now.tm_min
    return 915 <= hm <= 1505


def _market_file_ttl() -> float:
    """盘后列表全天有效（日K定型、排序不变）；盘中 5 分钟。"""
    return 300.0 if _is_trading_time() else 86400.0


def _kline_max_age() -> float:
    """K线新鲜度：共享库持久日K昨收定型数据 48h 有效（选股足够, 盘中不重拉）。

    ⭐ 2026-08-10: 盘中不再 10 分钟 TTL——共享库昨晚写入的日K对选股/形态判定完全够用，
    盘中重拉只会拖慢 strong_pool（首tick 93s 根因）。当日新K线由调用方（实时行情/分钟K）保证。
    """
    return 48 * 3600.0


class KlineDB:
    """SQLite 日K持久缓存（跨进程复用，全量扫描二次运行秒级）。"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.path.join(_cache_dir(), "kline.db")
        self._path = db_path
        # timeout=30: 共享库被 web(limitup-system screen) 写入时等待而非报 database is locked
        self._wconn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
        self._lock = threading.Lock()
        self._local = threading.local()   # 每线程只读连接（并发读无锁竞争）
        # ⭐ WAL 模式：共享库被 web(limitup-system screen) 并行写入时，本进程读取不被锁阻塞
        try:
            self._wconn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass
        self._wconn.execute(
            "CREATE TABLE IF NOT EXISTS kline_daily (code TEXT, day TEXT, "
            "open REAL, high REAL, low REAL, close REAL, volume REAL, "
            "updated_ts REAL, PRIMARY KEY(code, day))")
        self._wconn.execute("CREATE INDEX IF NOT EXISTS idx_kd_code ON kline_daily(code)")
        self._wconn.commit()

    def _rconn(self):
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self._path, check_same_thread=False, timeout=30)
            self._local.conn = c
        return c

    def get(self, code: str, count: int, max_age: float) -> Tuple[Optional[List[Dict]], bool]:
        """返回 (rows, fresh)。fresh=False 表示缓存过期需重拉。读用线程本地连接（无锁）。"""
        conn = self._rconn()
        cur = conn.execute(
            "SELECT day, open, high, low, close, volume, updated_ts "
            "FROM kline_daily WHERE code=? ORDER BY day DESC LIMIT ?",
            (code, count))
        raw = cur.fetchall()
        if not raw:
            return None, False
        rows = [{"day": r[0], "open": r[1], "high": r[2], "low": r[3],
                 "close": r[4], "volume": r[5]} for r in reversed(raw)]
        fresh = (time.time() - float(raw[-1][6])) < max_age
        return rows, fresh

    def put(self, code: str, rows: List[Dict[str, Any]]) -> None:
        now = time.time()
        data = [(code, r["day"], r["open"], r["high"], r["low"], r["close"],
                 r["volume"], now) for r in rows]
        with self._lock:
            self._wconn.executemany(
                "INSERT OR REPLACE INTO kline_daily "
                "(code, day, open, high, low, close, volume, updated_ts) "
                "VALUES (?,?,?,?,?,?,?,?)", data)
            self._wconn.commit()


_kdb: Optional[KlineDB] = None
# 数据源健康状态：连续失败计数，触发指数退避（防止限流时疯狂重试加剧封禁）
_src_fail = {"tdx": 0, "tencent": 0, "sina": 0}
_src_fail_lock = threading.Lock()


def _src_backoff(src: str) -> float:
    """返回当前应等待的秒数（连续失败次数越多等待越久）。"""
    with _src_fail_lock:
        n = _src_fail[src]
    return min(0.2 * (2 ** n), 1.5) if n > 0 else 0.0


def _src_ok(src: str) -> None:
    with _src_fail_lock:
        _src_fail[src] = 0


def _src_fail_inc(src: str) -> None:
    with _src_fail_lock:
        _src_fail[src] = min(_src_fail[src] + 1, 8)


def _get_kdb() -> KlineDB:
    global _kdb
    if _kdb is None:
        _kdb = KlineDB()
    return _kdb
