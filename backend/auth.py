"""User authentication: register, login, JWT middleware"""
import os, json, hashlib, secrets, logging
from datetime import datetime, timedelta
from pathlib import Path
import bcrypt

PROJ = Path(__file__).resolve().parent.parent
AUTH_FILE = PROJ / "backend" / "data" / "auth_users.json"
logger = logging.getLogger("aurora.auth")

def _load_secret() -> str:
    """JWT 兜底密钥: 优先环境变量 AURORA_SECRET, 其次 .env, 最后进程随机会话密钥。

    安全加固 P1-f: 不再使用固定公开默认值 "aurora-dev-2026" (否则环境变量未设时
    令牌可被伪造)。兜底改为每次进程启动随机生成, 重启后旧 token 失效——对个人/
    单机 SaaS 可接受, 且杜绝固定可伪造默认值。
    """
    value = os.environ.get("AURORA_SECRET", "").strip()
    if value:
        return hashlib.sha256(value.encode()).hexdigest()
    # 兜底: 尝试从 .env 读取 (与 daily_run.py 解析风格一致, 手动解析避免额外依赖)
    env_path = PROJ / ".env"
    if env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").strip().split("\n"):
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k == "AURORA_SECRET" and v:
                        return hashlib.sha256(v.encode()).hexdigest()
        except Exception:
            logger.warning("[auth] 读取 .env 失败, 改用进程随机会话密钥", exc_info=True)
    # 兜底: 进程随机密钥, 重启后旧 token 失效
    logger.warning(
        "[auth] 未配置 AURORA_SECRET (环境变量/.env 均无), 使用进程随机会话密钥, 重启后旧 token 失效"
    )
    return hashlib.sha256(secrets.token_bytes(32)).hexdigest()

SECRET = _load_secret()
TOKEN_TTL = 7 * 24 * 3600

from backend.database import get_user, create_user

def register(email, password):
    if not email or "@" not in email:
        return {"status": "error", "message": "邮箱格式不正确"}
    if len(password) < 6:
        return {"status": "error", "message": "密码至少6位"}
    existing = get_user(email)
    if existing:
        return {"status": "error", "message": "该邮箱已注册"}
    salt = bcrypt.gensalt()
    pwd = bcrypt.hashpw(password.encode(), salt).decode()
    create_user(email, pwd)
    token = _gen_token(email)
    return {"status": "ok", "token": token, "email": email, "tier": "free"}

def login(email, password):
    u = get_user(email)
    if not u:
        return {"status": "error", "message": "邮箱或密码错误"}
    if not bcrypt.checkpw(password.encode(), u["password"].encode()):
        return {"status": "error", "message": "邮箱或密码错误"}
    token = _gen_token(email)
    return {"status": "ok", "token": token, "email": email, "tier": u.get("tier", "free")}

def _gen_token(email):
    import jwt
    payload = {"email": email, "exp": datetime.utcnow() + timedelta(seconds=TOKEN_TTL), "iat": datetime.utcnow()}
    return jwt.encode(payload, SECRET, algorithm="HS256")

def verify(token):
    import jwt
    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        return {"status": "ok", "email": payload["email"]}
    except jwt.ExpiredSignatureError:
        return {"status": "error", "message": "Token已过期，请重新登录"}
    except Exception as e:
        return {"status": "error", "message": str(e)}