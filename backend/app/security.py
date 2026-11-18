from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User

hasher = PasswordHasher()
bearer = HTTPBearer(auto_error=False)


def verify_password(raw, encoded):
    try:
        return hasher.verify(encoded, raw)
    except (VerificationError, InvalidHashError):
        return False


def token_for(user):
    cfg = get_settings()
    return jwt.encode(
        {
            "sub": str(user.id),
            "ver": user.auth_version,
            "exp": datetime.now(timezone.utc) + timedelta(hours=cfg.token_hours),
        },
        cfg.jwt_secret,
        algorithm="HS256",
    )


def current_user(
    auth: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
):
    if not auth:
        raise HTTPException(401, "请先登录")
    try:
        payload = jwt.decode(
            auth.credentials, get_settings().jwt_secret, algorithms=["HS256"]
        )
        user = db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, "登录已过期，请重新登录")
    if not user or not user.active:
        raise HTTPException(401, "账号不可用")
    if payload.get("ver", 0) != user.auth_version:
        raise HTTPException(401, "密码已更新，请重新登录")
    return user


def require_roles(*roles):
    def dependency(user: User = Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(403, "当前角色没有此操作权限")
        return user

    return dependency
