"""Password hashing, JWT session tokens and encryption of third-party tokens."""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=4 if settings.app_env == "test" else 12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(subject: str, extra: dict[str, Any] | None = None, minutes: int | None = None) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=minutes or settings.access_token_expire_minutes),
        "typ": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    payload = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])
    if payload.get("typ") != expected_type:
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def create_state_token(data: dict[str, Any], minutes: int = 15) -> str:
    """Signed, short-lived OAuth `state` value (CSRF protection for the Instagram connect flow)."""
    return create_access_token(subject=str(data.get("user_id", "")), extra={**data, "typ": "oauth_state"}, minutes=minutes)


def _fernet() -> Fernet:
    key = settings.token_encryption_key
    if not key:
        # Development fallback: derive a key from SECRET_KEY. Production refuses to
        # start without TOKEN_ENCRYPTION_KEY (see Settings.validate_for_production).
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest()).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:  # key rotated or data corrupted
        raise ValueError("Stored secret could not be decrypted - reconnect the account.") from exc
