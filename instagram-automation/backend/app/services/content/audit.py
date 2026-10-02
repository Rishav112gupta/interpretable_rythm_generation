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
    _emit_webhook(db, post, event_type, to_status, message)
    return ev


def _emit_webhook(db: Session, post: Post, event_type: str, to_status: str | None, message: str) -> None:
    """Queue a webhook (e.g. for n8n) in the same transaction as the audit event."""
    from app.services.automation import webhooks

    event = webhooks.event_for(event_type, to_status)
    if event is None:
        return
    # A retry goes back to SCHEDULED, but it is reported as post.publish_retry only.
    if event == "post.scheduled" and event_type not in ("status_change", "rescheduled"):
        return
    try:
        webhooks.enqueue(db, event, webhooks.post_payload(post, redact(message)))
    except Exception:  # webhooks must never break the main workflow
        logger.exception("Could not queue webhook %s for post %s", event, post.id)


def log_integration(db: Session, source: str, message: str, *, level: str = "error", details: dict[str, Any] | None = None, post_id: int | None = None) -> None:
    """Persist an integration error so admins see it on the dashboard (never silently fail)."""
    message = redact(message)
    getattr(logger, "error" if level == "error" else "warning" if level == "warning" else "info")(f"[{source}] {message}")
    db.add(IntegrationLog(source=source, level=level, message=message, details=details or {}, post_id=post_id))
