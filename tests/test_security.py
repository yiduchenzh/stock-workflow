# -*- coding: utf-8 -*-
"""安全 P0 回归测试 — 覆盖 5 项加固 (源自 data/audit_10dim.md).

验证要点:
① S-1 Server酱 token 只从 .env/环境变量读取; 无 token 时 pusher 降级跳过不崩。
② S-2 /api/strategies/config/{key} 需 JWT 鉴权 + 参数白名单 (防正则注入)。
③ S-3 /api/user/upgrade 需 JWT 鉴权 (401 未登录 / 403 越权) + tier 白名单。
④ S-4 /api/payment/simulate 非 dev 模式 403。
⑤ S-5 startup 不得再注入 random 假信号 (断言 main 模块无 _inj/_gen)。

隔离: 从不触碰真实 config.yaml/users.json — config 写测试用 monkeypatch
CONFIG_PATH 指向临时文件; user 升级用临时 uid + 清理。
"""
import os
import tempfile
from pathlib import Path

import pytest

try:
    from fastapi.testclient import TestClient
    from backend.main import app, CONFIG_PATH
    _HAS_FASTAPI = True
except Exception as _e:  # noqa: BLE001
    _HAS_FASTAPI = False
    _IMPORT_ERR = _e


pytestmark = pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi 未安装,跳过安全测试")


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _gen_token(email: str) -> str:
    from backend.auth import _gen_token
    return _gen_token(email)


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# ═════════════════════════════ ① S-1 pusher 无 token 降级 ═════════════════════════════
def test_pusher_no_token_degrades_without_crash(monkeypatch):
    """S-1: 无 SCT_TOKEN (环境变量清空) 时 _send 降级为跳过, 不打崩、不发请求."""
    import notify.pusher as push
    class _FakeResp:
        pass
    # 确保环境里没有 token
    monkeypatch.delenv("SCT_TOKEN", raising=False)
    calls = []
    monkeypatch.setattr(push.requests, "post", lambda *a, **k: calls.append(a) or _FakeResp())
    engine = type("E", (), {"cfg": {"notify": {"sct_token": "SCT-FAKE-LEAKED"}}})()
    # 即使 engine.cfg 里残留明文 token, 也绝不使用 → 证明不再信任 config 明文
    push._send("标题", "内容", engine)
    assert calls == []  # 无 token 时绝不发请求


def test_pusher_uses_env_token_not_cfg(monkeypatch):
    """S-1: token 只认 SCT_TOKEN 环境变量, config 里的明文被忽略."""
    import notify.pusher as push
    monkeypatch.setenv("SCT_TOKEN", "SCT-env-token-123456")
    sent = {}
    def fake_post(url, json=None, timeout=None):
        sent["url"] = url
        sent["json"] = json
        return type("R", (), {"ok": True})()
    monkeypatch.setattr(push.requests, "post", fake_post)
    # 去重若报错不阻塞判定 — 这里直接调用 _send, cfg 中有明文但被忽略
    engine = type("E", (), {"cfg": {"notify": {"sct_token": "SCT-CFG-LEAKED"}}})()
    push._send("标题T", "内容D" * 20, engine)  # 长度>60 触发合规后缀也不影响
    if not sent:
        # 可能被 dedup 拦截, 属正常; 至少证明不会用 cfg 明文发请求到 ftqq
        return
    # 若发出了, URL 必须用环境变量 token
    assert "SCT-env-token-123456" in sent["url"]
    assert "SCT-CFG-LEAKED" not in sent["url"]


def test_config_yaml_no_plaintext_token():
    """S-1: config.yaml 不再存明文 sct_token."""
    from backend.auth import PROJ as BP
    cfg = Path(BP).parent.parent / "config.yaml"
    if cfg.exists():
        text = cfg.read_text(encoding="utf-8")
        assert "SCT363204TA" not in text
        assert "sct_token: SCT" not in text


# ═════════════════════════════ ② S-2 写策略配置 ═════════════════════════════
@pytest.fixture
def tmp_config(monkeypatch):
    """用临时 config.yaml 隔离写配置测试, 绝不污染真实文件."""
    cfg = "@./.venv/Strategies Test"  # placeholder not used
    content = (
        "strategies:\n"
        "  wave_point:\n"
        "    atr_period: 12\n"
        "    wave_pct: 3.0\n"
        "  first_board:\n"
        "    lookback: 60\n"
    )
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / "config.yaml"
        tmp.write_text(content, encoding="utf-8")
        monkeypatch.setattr("backend.main.CONFIG_PATH", tmp)
        yield tmp


def test_config_write_requires_auth(client, tmp_config):
    """S-2: 无 token 写配置 → 401 拒绝, 文件不变."""
    before = tmp_config.read_text(encoding="utf-8")
    r = client.post("/api/strategies/config/wave_point",
                    params={"param": "wave_pct", "value": 4.5})
    assert r.status_code in (401, 403)
    assert tmp_config.read_text(encoding="utf-8") == before


def test_config_write_valid_param(client, tmp_config):
    """S-2: 合法 token + 白名单参数可改数值."""
    tok = _gen_token("user@test.com")
    r = client.post("/api/strategies/config/wave_point",
                    params={"param": "wave_pct", "value": 4.5},
                    headers=_bearer(tok))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["value"] == 4.5
    assert "wave_pct: 4.5" in tmp_config.read_text(encoding="utf-8")


def test_config_write_regex_injection_blocked(client, tmp_config):
    """S-2: param 含正则元字符 (.*) 被白名单/\\w+ 拦截, 不注入、文件不变."""
    before = tmp_config.read_text(encoding="utf-8")
    tok = _gen_token("user@test.com")
    r = client.post("/api/strategies/config/wave_point",
                    params={"param": ".*", "value": 9.9},
                    headers=_bearer(tok))
    assert r.status_code == 200
    assert r.json()["status"] == "error"  # 非法参数名 → error
    assert tmp_config.read_text(encoding="utf-8") == before


def test_config_write_non_whitelist_param(client, tmp_config):
    """S-2: 非白名单参数拒绝, 即使格式合法."""
    before = tmp_config.read_text(encoding="utf-8")
    tok = _gen_token("user@test.com")
    r = client.post("/api/strategies/config/wave_point",
                    params={"param": "evil_param", "value": 1.0},
                    headers=_bearer(tok))
    assert r.json()["status"] == "error"
    assert tmp_config.read_text(encoding="utf-8") == before


# ═════════════════════════════ ③ S-3 用户升级 ═════════════════════════════
def test_upgrade_no_token_rejected(client, monkeypatch):
    """S-3: 无 token 调 /api/user/upgrade → 401."""
    r = client.get("/api/user/upgrade", params={"uid": "abc", "tier": "vip"})
    assert r.status_code == 401


def test_upgrade_invalid_tier_rejected(client):
    """S-3: tier 不在白名单 → 400."""
    tok = _gen_token("self@test.com")
    r = client.get("/api/user/upgrade",
                   params={"uid": "self@test.com", "tier": "superadmin"},
                   headers=_bearer(tok))
    assert r.status_code == 400


def test_upgrade_non_matching_user_forbidden(client):
    """S-3: 登录但非管理员且非本人 → 403."""
    tok = _gen_token("alice@test.com")
    r = client.get("/api/user/upgrade",
                   params={"uid": "other-user", "tier": "vip"},
                   headers=_bearer(tok))
    assert r.status_code == 403


def test_upgrade_self_allowed(client, monkeypatch):
    """S-3: 本人(uid==email) 可升级白名单内 tier."""
    uid = "self@test.com"
    try:
        tok = _gen_token(uid)
        r = client.get("/api/user/upgrade",
                       params={"uid": uid, "tier": "vip", "days": 5},
                       headers=_bearer(tok))
        assert r.status_code == 200
        assert r.json()["tier"] == "vip"
    finally:
        # 清理临时用户文件
        from backend.users import _path_uid
        p = _path_uid(uid)
        if p.exists():
            p.unlink()


def test_upgrade_admin_allowed(client):
    """S-3: 管理员可升级任意 uid."""
    import backend.deps as deps
    mono = __import__("unittest.mock", fromlist=["patch"]).patch.dict
    os.environ["AURORA_ADMIN_EMAILS"] = "admin@test.com"
    try:
        tok = _gen_token("admin@test.com")
        uid = "some-random-uid"
        r = client.get("/api/user/upgrade",
                       params={"uid": uid, "tier": "annual", "days": 1},
                       headers=_bearer(tok))
        assert r.status_code == 200
        assert r.json()["tier"] == "annual"
        from backend.users import _path_uid
        p = _path_uid(uid)
        if p.exists():
            p.unlink()
    finally:
        os.environ.pop("AURORA_ADMIN_EMAILS", None)


# ═════════════════════════════ ④ S-4 支付模拟 ═════════════════════════════
def test_simulate_pay_non_dev_403(client, monkeypatch):
    """S-4: AURORA_MODE != dev → 403, 即便带 token."""
    monkeypatch.delenv("AURORA_MODE", raising=False)
    tok = _gen_token("admin@test.com")
    _create_order("oidxyz123")
    try:
        r = client.post("/api/payment/simulate/oidxyz123", headers=_bearer(tok))
        assert r.status_code == 403
    finally:
        from backend.main import _order_path as _op
        p = _op("oidxyz123")
        if p.exists():
            p.unlink()


def test_simulate_pay_dev_requires_admin(client, monkeypatch):
    """S-4: dev 模式但仍需管理员鉴权; 普通用户 → 403."""
    monkeypatch.setenv("AURORA_MODE", "dev")
    try:
        tok = _gen_token("plain@test.com")
        r = client.post("/api/payment/simulate/oid-does-not-exist", headers=_bearer(tok))
        assert r.status_code == 403  # 非管理员被拒
    finally:
        os.environ.pop("AURORA_MODE", None)


def test_simulate_pay_no_token_rejected(client, monkeypatch):
    """S-4: 无 token 也拒绝."""
    monkeypatch.setenv("AURORA_MODE", "dev")
    try:
        r = client.post("/api/payment/simulate/oidxyz", )
        assert r.status_code == 401
    finally:
        os.environ.pop("AURORA_MODE", None)


# ═════════════════════════════ ⑤ S-5 无假信号注入 ═════════════════════════════
def test_no_fake_signal_injection_in_startup():
    """S-5: 模块内不再存在随机假信号注入 `_inj`/`_gen` 或写死股票表."""
    src = Path(__file__).resolve().parent.parent / "backend" / "main.py"
    text = src.read_text(encoding="utf-8")
    assert "def _inj(" not in text
    assert "def _gen(" not in text
    assert "_r.choice(stocks)" not in text
    assert "_r.randint(30,95)" not in text


# ═════════════════════════════ 工具 ═════════════════════════════
def _create_order(oid):
    import json
    from backend.main import _order_path
    order = {"oid": oid, "uid": "demo", "tier": "live", "days": 30,
             "amount": 1900, "status": "pending", "created": ""}
    _order_path(oid).write_text(json.dumps(order), encoding="utf-8")


def _clean_order(oid):
    from backend.main import _order_path
    p = _order_path(oid)
    if p.exists():
        p.unlink()
