"""API keys for automation tools (n8n, Zapier, scripts).

A key is sent as the `X-API-Key` header. Each key is backed by its own
service user with a normal role, so the existing permission checks and audit
trail apply unchanged. Admin keys are not allowed: automation should never
be able to manage users, settings or the Instagram connection.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailed
from app.core.security import hash_password
from app.models import ApiKey, Role, User

KEY_PREFIX = "ia_"
ALLOWED_ROLES = {Role.VIEWER, Role.EDITOR, Role.APPROVER}


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def create_api_key(db: Session, *, name: str, role: Role, created_by_id: int | None) -> tuple[ApiKey, str]:
    """Create a key and return (row, plaintext key). The plaintext is never stored."""
    if role not in ALLOWED_ROLES:
        raise ValidationFailed("API keys can have the viewer, editor or approver role (admin is not allowed).")
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "key"
    service_user = User(
        email=f"apikey-{slug}-{secrets.token_hex(3)}@service.local",
        full_name=f"API key: {name}",
        hashed_password=hash_password(secrets.token_urlsafe(32)),  # unusable for login
        role=role,
        is_service=True,
    )
    db.add(service_user)
    db.flush()
    plaintext = KEY_PREFIX + secrets.token_urlsafe(32)
    row = ApiKey(name=name, prefix=plaintext[:10], key_hash=_hash(plaintext), service_user_id=service_user.id, created_by_id=created_by_id)
    db.add(row)
    db.commit()
    return row, plaintext


def authenticate(db: Session, key: str) -> User | None:
    if not key or not key.startswith(KEY_PREFIX):
        return None
    row = db.scalars(select(ApiKey).where(ApiKey.key_hash == _hash(key))).first()
    if row is None or row.revoked_at is not None:
        return None
    user = row.service_user
    if user is None or not user.is_active:
        return None
    now = datetime.now(UTC)
    if row.last_used_at is None or now - row.last_used_at > timedelta(minutes=1):
        row.last_used_at = now
        db.commit()
    return user


def revoke(db: Session, row: ApiKey) -> None:
    row.revoked_at = datetime.now(UTC)
    if row.service_user:
        row.service_user.is_active = False
    db.commit()
