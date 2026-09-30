"""Audit trail and integration error log helpers."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import redact
from app.models import IntegrationLog, Post, PostEvent

logger = logging.getLogger(__name__)


def record_event(
    db: Session,
    post: Post,
    event_type: str,
    message: str = "",
    *,
    from_status: str | None = None,
    to_status: str | None = None,
    actor_id: int | None = None,
    data: dict[str, Any] | None = None,
) -> PostEvent:
    ev = PostEvent(
        post_id=post.id,
        event_type=event_type,
        message=redact(message),
        from_status=from_status,
        to_status=to_status,
        actor_id=actor_id,
        data=data or {},
    )
    db.add(ev)
    return ev


def log_integration(db: Session, source: str, message: str, *, level: str = "error", details: dict[str, Any] | None = None, post_id: int | None = None) -> None:
    """Persist an integration error so admins see it on the dashboard (never silently fail)."""
    message = redact(message)
    getattr(logger, "error" if level == "error" else "warning" if level == "warning" else "info")(f"[{source}] {message}")
    db.add(IntegrationLog(source=source, level=level, message=message, details=details or {}, post_id=post_id))
