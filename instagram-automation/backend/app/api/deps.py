from __future__ import annotations

from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.rate_limit import rate_limiter
from app.core.security import decode_token
from app.database.session import get_db
from app.models import Role, User

bearer = HTTPBearer(auto_error=False)

ROLE_RANK = {Role.VIEWER: 0, Role.EDITOR: 1, Role.APPROVER: 2, Role.ADMIN: 3}


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = decode_token(creds.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired or invalid. Please log in again.", headers={"WWW-Authenticate": "Bearer"}) from None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account disabled or not found.")
    return user


def require_role(minimum: Role) -> Callable[[User], User]:
    def checker(user: User = Depends(get_current_user)) -> User:
        if ROLE_RANK.get(Role(user.role), -1) < ROLE_RANK[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"This action requires the '{minimum.value}' role or higher.")
        return user

    return checker


viewer = require_role(Role.VIEWER)
editor = require_role(Role.EDITOR)
approver = require_role(Role.APPROVER)
admin = require_role(Role.ADMIN)


def rate_limit(key: str, limit_attr: str):
    from app.core.config import settings

    def dep(request: Request, user: User = Depends(get_current_user)) -> None:
        rate_limiter.hit(f"{key}:{user.id}", getattr(settings, limit_attr))

    return dep


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
