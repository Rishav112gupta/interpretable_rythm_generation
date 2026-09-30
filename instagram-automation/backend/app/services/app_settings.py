"""Runtime settings editable from the dashboard (stored in the app_settings table)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AppSetting

DEFAULTS: dict[str, Any] = {
    "timezone": settings.default_timezone,
    "publishing_enabled": settings.publishing_enabled,
    "sheets_auto_sync": False,
}


def get_setting(db: Session, key: str) -> Any:
    row = db.get(AppSetting, key)
    return row.value if row is not None else DEFAULTS.get(key)


def set_setting(db: Session, key: str, value: Any) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value


def all_settings(db: Session) -> dict[str, Any]:
    return {k: get_setting(db, k) for k in DEFAULTS}


def get_timezone(db: Session) -> str:
    return get_setting(db, "timezone") or "Asia/Kolkata"
