"""FastAPI 安全依赖 — JWT Bearer token 鉴权.

供受保护端点复用: /api/strategies/config、/api/user/upgrade、/api/payment/simulate。
复用 backend/auth.py 的 SECRET 与签名机制, 未破坏 /api/auth/* 自身。
"""
from __future__ import annotations
import os
from fastapi import Depends, HTTPException, Header

# 避免引入循环导入: 仅在依赖函数内延迟 import backend.auth
def _verify_token(token: str):
    from backend.auth import verify as _ver
    res = _ver(token)
    if res.get("status") != "ok":
        raise HTTPException(status_code=401, detail=res.get("message", "未授权"))
    return res["email"]


def require_user(authorization: str = Header(default="")):
    """要求合法 JWT (Bearer token)。返回登录用户邮箱。"""
    if not authorization:
        raise HTTPException(status_code=401, detail="缺少 Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Bearer token 缺失或格式错误")
    return _verify_token(token.strip())


def require_admin(authorization: str = Header(default="")):
    """在 require_user 基础上要求管理员。管理员邮箱由环境变量 AURORA_ADMIN_EMAILS 指定(逗号分隔)。"""
    email = require_user(authorization=authorization)
    admins = _admin_emails()
    # 未配置管理员清单时, 拒绝一切 admin 端点 (fail-closed, 而非默认放行)
    if not admins or email.lower() not in admins:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return email


def _admin_emails() -> set:
    return {e.strip().lower() for e in os.environ.get("AURORA_ADMIN_EMAILS", "").split(",") if e.strip()}


def is_admin_email(email: str) -> bool:
    """供端点内复用: 判断某邮箱是否管理员 (不抛异常, 便于结合 uid 匹配逻辑)."""
    return bool(email) and email.lower() in _admin_emails()


def require_optional_user(authorization: str = Header(default="")):
    """可选鉴权: 带合法 token 返回邮箱, 否则返回 "" (不抛异常)。

    用于需要在「未登录拒绝」与「登录但非管理员」之间分别处理的端点,
    由端点自身基于返回值决定放行/拒绝。
    """
    if not authorization:
        return ""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return ""
    try:
        return _verify_token(token.strip())
    except HTTPException:
        return ""
