"""
测试 JWT 兜底密钥安全加固 (P1-f)。

验证 backend.auth 的 SECRET 不再推导自固定公开默认值 "aurora-dev-2026":
  (a) 设置环境变量 AURORA_SECRET 时, SECRET 必须由该变量派生;
  (b) 未设置任何 AURORA_SECRET 时, SECRET 必须是随机进程密钥, 绝不能等于
      sha256("aurora-dev-2026") 这个固定可伪造值。

由于 SECRET 在模块导入时求值, 用独立子进程控制环境变量, 避免污染其它测试。
"""
import hashlib
import os
import subprocess
import sys

from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
AUTH_PY = PROJ / "backend" / "auth.py"

_FIXED_DEFAULT = "aurora-dev-2026"
_FIXED_SHA = hashlib.sha256(_FIXED_DEFAULT.encode()).hexdigest()

_IMPORT_SNIPPET = (
    "import sys; sys.path.insert(0, r'{proj}'); "
    "from backend.auth import SECRET; "
    "print(SECRET)"
)


def _run_import(**env_overrides):
    """在独立子进程里 import backend.auth, 返回其 SECRET。"""
    env = dict(os.environ)
    for k, v in env_overrides.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    code = _IMPORT_SNIPPET.format(proj=str(PROJ))
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd=str(PROJ), env=env, timeout=120,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"import backend.auth 失败:\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )
    secret = proc.stdout.strip().splitlines()[-1]
    assert secret, "SECRET 输出为空"
    return secret


def test_secret_derives_from_env_var():
    """(a) 设置 AURORA_SECRET 时, SECRET 由该变量派生, 用不到默认/随机密钥。"""
    env_secret = "my-very-secret-production-key-42"
    expected = hashlib.sha256(env_secret.encode()).hexdigest()
    secret = _run_import(AURORA_SECRET=env_secret)
    assert secret == expected, (
        f"SECRET 应由环境变量 AURORA_SECRET 派生, 期望 {expected}, 实际 {secret}"
    )
    # 且绝不能是固定默认值
    assert secret != _FIXED_SHA, "SECRET 仍是固定默认值哈希"


def test_secret_not_fixed_default_without_env():
    """(b) 未设置 AURORA_SECRET 时, SECRET 不是固定默认值, 而是随机会话密钥。"""
    secret = _run_import(AURORA_SECRET=None)
    assert secret != _FIXED_SHA, (
        f"未配置 AURORA_SECRET 时 SECRET 绝不能等于 sha256({_FIXED_DEFAULT!r}), "
        "否则 JWT 令牌可被伪造"
    )
    # 64 位 sha256 hexdigest
    assert len(secret) == 64, f"SECRET 应为 sha256 hexdigest (64 字符), 实际 {len(secret)}"


def test_secret_differs_across_process_restarts():
    """进程重启后 SECRET 变化 (随机会话密钥语义): 独立子进程两次导入应不同。"""
    s1 = _run_import(AURORA_SECRET=None)
    s2 = _run_import(AURORA_SECRET=None)
    assert s1 != s2, "未配置 AURORA_SECRET 时, 每次进程 SECRET 应随机不同 (重启后旧 token 失效)"
