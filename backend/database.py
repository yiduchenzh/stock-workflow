# Database layer - SQLite
import sqlite3, json, logging
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent
DB_DIR = BASE / "backend" / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "aurora.db"
logger = logging.getLogger("aurora.db")

def conn():
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c

def init():
    db = conn()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            password TEXT,
            tier TEXT DEFAULT 'free',
            created TEXT,
            used INTEGER DEFAULT 0,
            limit_q INTEGER DEFAULT 3,
            data TEXT DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS orders (
            oid TEXT PRIMARY KEY,
            uid TEXT,
            tier TEXT,
            days INTEGER DEFAULT 30,
            amount INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created TEXT,
            paid_at TEXT
        );
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT, name TEXT, action TEXT,
            score INTEGER, strategy TEXT, price REAL,
            regime TEXT, time TEXT
        );
    """)
    db.commit()
    db.close()
    logger.info("DB ready")

def migrate():
    db = conn()
    count = 0
    af = DB_DIR / "auth_users.json"
    if af.exists():
        for email, ud in json.loads(af.read_text(encoding="utf-8")).items():
            db.execute("INSERT OR IGNORE INTO users (email,password,tier,created,used,limit_q,data) VALUES (?,?,?,?,?,?,?)",
                [email, ud.get("pwd",""), ud.get("tier","free"), ud.get("created",""), ud.get("used",0), ud.get("limit",3), json.dumps(ud)])
            count += 1
    db.commit()
    db.close()
    if count:
        logger.info("Migrated %d users", count)
    return count

def get_user(email):
    db = conn()
    r = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    db.close()
    return dict(r) if r else None

def create_user(email, pwd_hash, tier="free"):
    limit = {"free":3,"live":50,"vip":999,"annual":9999}.get(tier, 3)
    db = conn()
    db.execute("INSERT OR REPLACE INTO users (email,password,tier,created,used,limit_q) VALUES (?,?,?,?,?,?)",
        [email, pwd_hash, tier, datetime.now().isoformat(), 0, limit])
    db.commit()
    db.close()

def update_tier(email, tier):
    limit = {"free":3,"live":50,"vip":999,"annual":9999}.get(tier, 3)
    db = conn()
    db.execute("UPDATE users SET tier=?, limit_q=? WHERE email=?", (tier, limit, email))
    db.commit()
    db.close()

def inc_usage(email):
    db = conn()
    db.execute("UPDATE users SET used=used+1 WHERE email=?", (email,))
    db.commit()
    db.close()