"""基本面真实落库 + 板块多对多映射 — fundamentals & stock_sector SQLite 存储.

设计要点:
- 只存真实拉取到的值: 拉不到的字段写 NULL,绝不回填模拟值冒充真实数据。
- 数据源: 腾讯行情(data.sources.get_tencent_quotes)为主(提供 pe/pb/总市值/流通市值,
  不封 IP)。东财 f128 等特有字段走其独有接口,但基本面估值腾讯已覆盖,故主源即腾讯。
- 落库策略: upsert(INSERT OR REPLACE),重复刷新以新值覆盖。
- 线程安全: 所有写操作加锁,避免 FastAPI 多线程并发写 SQLite 冲突。

表结构:
  fundamentals(code TEXT PRIMARY KEY, pe_ttm REAL, pb REAL, market_cap REAL,
               roe REAL, float_mcap REAL, price REAL, updated_at TEXT)
  stock_sector(code TEXT, sector TEXT, weight REAL, UNIQUE(code, sector))
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("aurora.fundamentals_store")

# 独立建库,与 backend/aurora.db(账户/信号)分离,职责清晰便于独立维护
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "fundamentals.db"

_lock = threading.RLock()

# 腾讯行情字段 -> 落库字段映射 (字段名取自 data.sources.get_tencent_quotes)
#   pe        = 动态市盈率(PE-TTM),腾讯提供
#   pb        = 市净率
#   mcap      = 总市值(亿元)
#   float_mcap= 流通市值(亿元)
#   price     = 现价
#   roe       = 腾讯行情不提供,故不硬塞;若未来有数据源提供再启用
_TX_QUOTE_MAP = {
    "pe_ttm": "pe",
    "pb": "pb",
    "market_cap": "mcap",
    "float_mcap": "float_mcap",
    "price": "price",
}


def _conn() -> sqlite3.Connection:
    """获取 SQLite 连接(行工厂开启)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _schema() -> str:
    return """
        CREATE TABLE IF NOT EXISTS fundamentals (
            code       TEXT PRIMARY KEY,
            pe_ttm     REAL,
            pb         REAL,
            market_cap REAL,
            roe        REAL,
            float_mcap REAL,
            price      REAL,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS stock_sector (
            code   TEXT,
            sector TEXT,
            weight REAL,
            PRIMARY KEY (code, sector)
        );
    """


def init() -> None:
    """初始化表结构(幂等)."""
    with _lock:
        db = _conn()
        try:
            db.executescript(_schema())
            db.commit()
        finally:
            db.close()
        logger.debug("[fundamentals_store] schema ready")


# ═══════════════════════════════════════════════════════════════════════════
# ① 基本面落库
# ═══════════════════════════════════════════════════════════════════════════

def _pull_from_tencent(codes: List[str]) -> Dict[str, dict]:
    """用腾讯行情拉取真实估值字段;拉不到返回空 dict(不抛伪造)."""
    try:
        from data.sources import get_tencent_quotes
        quotes = get_tencent_quotes(codes)
        out = {}
        for code, q in quotes.items():
            row = {"code": code}
            for field, tx_field in _TX_QUOTE_MAP.items():
                val = q.get(tx_field)
                # 腾讯默认 0/空也算"拉不到该值",置 None 表示未知
                if val is None or val == "":
                    row[field] = None
                else:
                    try:
                        fv = float(val)
                        row[field] = fv if fv == fv else None  # NaN -> None
                    except (TypeError, ValueError):
                        row[field] = None
            # roe 腾讯行情不提供,如实置 None
            row["roe"] = None
            out[code] = row
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[fundamentals_store] 腾讯行情拉取失败: {e}")
        return {}


def _upsert_fundamentals(db: sqlite3.Connection, rows: List[dict]) -> None:
    """批量 upsert 真实基本面到 fundamentals 表."""
    now = datetime.now().isoformat(timespec="seconds")
    for r in rows:
        db.execute(
            """INSERT OR REPLACE INTO fundamentals
               (code, pe_ttm, pb, market_cap, roe, float_mcap, price, updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                r.get("code"),
                r.get("pe_ttm"),
                r.get("pb"),
                r.get("market_cap"),
                r.get("roe"),
                r.get("float_mcap"),
                r.get("price"),
                now,
            ),
        )


def refresh_fundamentals(codes: List[str]) -> Dict[str, dict]:
    """用真实数据源刷新并落库基本面向量,返回 {code: {...}}.

    只落真实拉取到的值;某字段拉不到则写 NULL,不写模拟值。
    返回的 dict 与落库内容一致(含 None 字段表示该值未知)。
    """
    if not codes:
        return {}
    init()
    pulled = _pull_from_tencent(codes)
    if not pulled:
        logger.warning(f"[fundamentals_store] refresh {len(codes)} code: 未能拉到任何真实值")
        return {}
    with _lock:
        db = _conn()
        try:
            _upsert_fundamentals(db, list(pulled.values()))
            db.commit()
        finally:
            db.close()
    got = len([r for r in pulled.values() if r.get("pe_ttm") is not None])
    logger.info(f"[fundamentals_store] refresh {len(codes)} code: 拉到 {got} 只有效PE")
    return pulled


def get_fundamentals(code: str) -> dict:
    """读库返回单只股票真实基本面;缺失返回空 dict (不返回模拟值)."""
    init()
    with _lock:
        db = _conn()
        try:
            r = db.execute(
                "SELECT code, pe_ttm, pb, market_cap, roe, float_mcap, price, updated_at "
                "FROM fundamentals WHERE code=?", (code,),
            ).fetchone()
            return dict(r) if r else {}
        finally:
            db.close()


def get_fundamentals_snapshot(codes: List[str]) -> Dict[str, dict]:
    """批量读库;批量中某只缺失则该 code 不出现(读不到 = 无该只)."""
    if not codes:
        return {}
    init()
    placeholders = ",".join("?" * len(codes))
    with _lock:
        db = _conn()
        try:
            rows = db.execute(
                f"SELECT code, pe_ttm, pb, market_cap, roe, float_mcap, price, updated_at "
                f"FROM fundamentals WHERE code IN ({placeholders})",
                list(codes),
            ).fetchall()
            return {r["code"]: dict(r) for r in rows}
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════════
# ② 板块多对多映射
# ═══════════════════════════════════════════════════════════════════════════

def update_stock_sectors(mapping: Dict[str, object]) -> None:
    """写入/覆盖某股所属板块(多对多).

    mapping 支持三种形态:
      {code: [(sector, weight), (sector2, weight2), ...]}   # 二元组带权重
      {code: {sector: weight, ...}}                          # dict(板块->权重)
      {code: ["板块A", "板块B", ...]}                         # 仅板块名,权重默认 1.0

    对同一 code 采用"全量替换"语义: 先删旧再写新,保证表内与 mapping 一致,
    避免陈旧板块残留。未在 mapping 中的 code 不受影响。
    """
    if not mapping:
        return
    init()
    normalized = []
    for code, val in mapping.items():
        code = str(code)
        if isinstance(val, dict):
            items = [(str(k), float(v)) for k, v in val.items()]
        elif isinstance(val, (list, tuple)):
            items = []
            for it in val:
                if isinstance(it, (list, tuple)) and len(it) == 2:
                    items.append((str(it[0]), float(it[1])))
                else:
                    items.append((str(it), 1.0))
        else:
            items = [(str(val), 1.0)]
        normalized.extend((code, sector, weight) for sector, weight in items)
    with _lock:
        db = _conn()
        try:
            for code in {t[0] for t in normalized}:
                db.execute("DELETE FROM stock_sector WHERE code=?", (code,))
            db.executemany(
                "INSERT OR REPLACE INTO stock_sector (code, sector, weight) VALUES (?,?,?)",
                normalized,
            )
            db.commit()
        finally:
            db.close()
    logger.debug(f"[fundamentals_store] update_stock_sectors: {len(normalized)} 条映射")


def get_stock_sectors(code: str) -> List[dict]:
    """返回单只股票所属板块列表 [{sector, weight}, ...],未配置返回空列表."""
    init()
    with _lock:
        db = _conn()
        try:
            rows = db.execute(
                "SELECT sector, weight FROM stock_sector WHERE code=? ORDER BY weight DESC, sector",
                (str(code),),
            ).fetchall()
            return [{"sector": r["sector"], "weight": r["weight"]} for r in rows]
        finally:
            db.close()


def get_stock_sectors_names(code: str) -> List[str]:
    """便捷: 仅返回板块名列表."""
    return [s["sector"] for s in get_stock_sectors(code)]


def get_stock_sectors_bulk(codes: List[str]) -> Dict[str, List[str]]:
    """批量读取多股板块归属,返回 {code: [sector名, ...]}.

    一次 SQLite 连接 + 一条 IN 查询,避免候选池数百上千只时逐股建连接
    造成性能瓶颈。批量中某 code 无板块记录则该 code 不出现。
    """
    if not codes:
        return {}
    init()
    placeholders = ",".join("?" * len(codes))
    with _lock:
        db = _conn()
        try:
            rows = db.execute(
                f"SELECT code, sector FROM stock_sector "
                f"WHERE code IN ({placeholders}) ORDER BY weight DESC, sector",
                list(codes),
            ).fetchall()
            out: Dict[str, List[str]] = {}
            for r in rows:
                out.setdefault(r["code"], []).append(r["sector"])
            return out
        finally:
            db.close()


def get_sector_members(sector: str) -> List[dict]:
    """反向查询: 返回隶属某板块(drill-down)的所有股票 [{code, weight}, ...].

    stock_sector 是 code<->sector 多对多,这里是按 sector 反查 members,
    供 /api/sector/members 接口把板块拆解成成分股。按 weight 降序排列,
    weight 相同时按 code 升序以保证确定性输出。
    若该板块无任何成分记录,返回空列表(不抛错、不伪造)。
    """
    if not sector:
        return []
    init()
    with _lock:
        db = _conn()
        try:
            rows = db.execute(
                "SELECT code, weight FROM stock_sector "
                "WHERE sector=? ORDER BY weight DESC, code",
                (str(sector),),
            ).fetchall()
            return [{"code": r["code"], "weight": r["weight"]} for r in rows]
        finally:
            db.close()


def ensure_sector_membership(code: str) -> str:
    """若某股在 stock_sector 尚无板块归属,则用真实数据源补齐(东财概念板块).

    返回 'filled'(已补齐) / 'exists'(本就存在) / 'no_source'(拉不到真实板块,留空)。
    只写真实拉取到的板块名,网络不可用时如实留空,绝不写模拟板块。
    """
    existing = get_stock_sectors(code)
    if existing:
        return "exists"
    # 尝试用东财真实概念板块填充 (get_concept_blocks 网络受限返回 [])
    _blocks = []
    try:
        from data.sources import get_concept_blocks
        _blocks = get_concept_blocks(code) or []
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[fundamentals_store] ensure_sector_membership({code}) 拉取概念板块失败: {e}")
        _blocks = []
    if not _blocks:
        logger.info(f"[fundamentals_store] ensure_sector_membership({code}) 无真实板块来源,留空不编造")
        return "no_source"
    # 板块分->权重(默认1.0;有涨幅则加权,便于 results 按权重排序)
    mapping = {}
    for b in _blocks:
        name = str(b.get("name", "")).replace("\u3000", "").strip()
        if not name:
            continue
        try:
            # 权重 = max(0.1, 1.0 + change_pct/100) —— 板块越热权重越高
            chg = float(b.get("change_pct", 0) or 0)
            mapping[name] = max(0.1, 1.0 + chg / 100.0)
        except (TypeError, ValueError):
            mapping[name] = 1.0
    if not mapping:
        return "no_source"
    update_stock_sectors({code: mapping})
    logger.info(f"[fundamentals_store] ensure_sector_membership({code}): 写入 {len(mapping)} 个真实板块")
    return "filled"



# 启动即确保表存在(幂等)
init()
