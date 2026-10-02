"""Outgoing webhooks (e.g. to n8n).

Reliability: events are written to the `webhook_deliveries` table in the SAME
database transaction as the change that caused them (transactional outbox).
The Celery worker sends pending deliveries every few seconds and retries
failures with back-off. So an event is never lost if n8n is down, and never
sent for a change that was rolled back.

Security: every request is signed.
  X-IA-Event:      post.published
  X-IA-Delivery:   <uuid>            (use it to ignore duplicates)
  X-IA-Timestamp:  <unix seconds>
  X-IA-Signature:  sha256=<hex HMAC-SHA256(secret, "<timestamp>.<raw body>")>
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import redact
from app.core.security import decrypt_secret, encrypt_secret
from app.models import Post, WebhookDelivery, WebhookEndpoint

logger = logging.getLogger(__name__)

EVENTS: dict[str, str] = {
    "post.created": "A post was created (dashboard, API, Google Sheets or recurring schedule).",
    "post.needs_review": "A post is waiting for human review/approval.",
    "post.approved": "A post was approved.",
    "post.rejected": "A post was rejected.",
    "post.scheduled": "An approved post was scheduled.",
    "post.published": "A post was published (check data.published_via_mock for simulated publishes).",
    "post.publish_retry": "Publishing hit a temporary error; an automatic retry is scheduled.",
    "post.failed": "Publishing failed permanently.",
    "post.generation_failed": "AI text generation failed.",
    "schedule.missed_slot": "A recurring-schedule slot passed without an approved post.",
    "instagram.token_expired": "The Instagram connection needs to be reconnected.",
    "webhook.test": "Test event sent from the dashboard.",
}

# Back-off between delivery attempts (seconds). After the last one the delivery is marked failed.
RETRY_DELAYS = [30, 120, 600, 1800, 3600]
TIMEOUT_SECONDS = 10.0

# post_event.event_type / to_status  ->  webhook event
_EVENT_TYPE_MAP = {
    "created": "post.created",
    "rescheduled": "post.scheduled",
    "publish_retry_scheduled": "post.publish_retry",
    "publish_failed": "post.failed",
    "published": "post.published",
    "generation_failed": "post.generation_failed",
    "missed_slot": "schedule.missed_slot",
}
_STATUS_MAP = {
    "NEEDS_REVIEW": "post.needs_review",
    "APPROVED": "post.approved",
    "REJECTED": "post.rejected",
    "SCHEDULED": "post.scheduled",
}

_transport: httpx.BaseTransport | None = None  # tests inject a fake transport


def set_transport(transport: httpx.BaseTransport | None) -> None:
    global _transport
    _transport = transport


def new_secret() -> str:
    return "whsec_" + secrets.token_urlsafe(32)


def create_endpoint(db: Session, *, name: str, url: str, events: list[str], secret: str | None = None) -> tuple[WebhookEndpoint, str]:
    secret = secret or new_secret()
    ep = WebhookEndpoint(name=name, url=url, events=events or ["*"], secret_encrypted=encrypt_secret(secret))
    db.add(ep)
    db.commit()
    return ep, secret


def sign(secret: str, timestamp: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), timestamp.encode("utf-8") + b"." + body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def verify(secret: str, timestamp: str, body: bytes, signature: str, *, tolerance_seconds: int = 300) -> bool:
    """Reference verification (the same logic is used in the n8n example workflow)."""
    if abs(time.time() - int(timestamp)) > tolerance_seconds:
        return False
    return hmac.compare_digest(sign(secret, timestamp, body), signature)


def post_payload(post: Post, message: str = "") -> dict[str, Any]:
    def iso(dt):
        return dt.isoformat() if dt else None

    return {
        "post": {
            "id": post.id,
            "status": post.status,
            "category": post.category.key if post.category else None,
            "topic": post.topic,
            "headline": post.headline,
            "caption": post.caption,
            "hashtags": post.hashtags or [],
            "image_url": post.image_url,
            "desired_publish_at": iso(post.desired_publish_at),
            "scheduled_at": iso(post.scheduled_at),
            "published_at": iso(post.published_at),
            "instagram_media_id": post.instagram_media_id,
            "instagram_permalink": post.instagram_permalink,
            "published_via_mock": post.published_via_mock,
            "review_flags": len(post.review_flags or []) + len(post.missing_information or []),
            "last_error": post.last_error,
            "dashboard_url": f"{settings.frontend_url.rstrip('/')}/posts/{post.id}",
        },
        "message": message,
    }


def event_for(event_type: str, to_status: str | None) -> str | None:
    return _EVENT_TYPE_MAP.get(event_type) or (_STATUS_MAP.get(to_status) if to_status else None)


def enqueue(db: Session, event: str, data: dict[str, Any], *, endpoint_id: int | None = None) -> list[WebhookDelivery]:
    """Add an outbox row for every active endpoint subscribed to `event`. Caller commits."""
    stmt = select(WebhookEndpoint).where(WebhookEndpoint.is_active.is_(True))
    if endpoint_id is not None:
        stmt = stmt.where(WebhookEndpoint.id == endpoint_id)
    created: list[WebhookDelivery] = []
    now = datetime.now(UTC)
    for ep in db.scalars(stmt).all():
        subscribed = ep.events or ["*"]
        if endpoint_id is None and "*" not in subscribed and event not in subscribed:
            continue
        delivery_id = str(uuid.uuid4())
        payload = {"id": delivery_id, "event": event, "created_at": now.isoformat(), "data": data}
        d = WebhookDelivery(id=delivery_id, endpoint_id=ep.id, event=event, payload=payload, next_attempt_at=now)
        db.add(d)
        created.append(d)
    return created


def _send(ep: WebhookEndpoint, delivery: WebhookDelivery) -> tuple[bool, int | None, str]:
    body = json.dumps(delivery.payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ts = str(int(time.time()))
    try:
        secret = decrypt_secret(ep.secret_encrypted)
    except ValueError as exc:
        return False, None, str(exc)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "instagram-automation-webhooks/1.0",
        "X-IA-Event": delivery.event,
        "X-IA-Delivery": delivery.id,
        "X-IA-Timestamp": ts,
        "X-IA-Signature": sign(secret, ts, body),
    }
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS, transport=_transport, follow_redirects=False) as client:
            resp = client.post(ep.url, content=body, headers=headers)
    except httpx.HTTPError as exc:
        return False, None, f"Network error: {type(exc).__name__}"
    if 200 <= resp.status_code < 300:
        return True, resp.status_code, ""
    return False, resp.status_code, redact(f"HTTP {resp.status_code}: {resp.text[:300]}")


def deliver(db: Session, d: WebhookDelivery, *, retry: bool = True, now: datetime | None = None) -> str:
    """Attempt one delivery. Returns "sent", "retrying" or "failed"."""
    now = now or datetime.now(UTC)
    ep = db.get(WebhookEndpoint, d.endpoint_id)
    if ep is None or not ep.is_active:
        d.status = "failed"
        d.last_error = "Endpoint disabled or deleted."
        db.commit()
        return "failed"
    ok, code, error = _send(ep, d)
    d.attempts += 1
    d.last_status_code = code
    ep.last_delivery_at = datetime.now(UTC)
    ep.last_status_code = code
    if ok:
        d.status = "success"
        d.delivered_at = datetime.now(UTC)
        d.last_error = ep.last_error = ""
        result = "sent"
    else:
        d.last_error = ep.last_error = error
        if retry and d.attempts <= len(RETRY_DELAYS):
            d.next_attempt_at = now + timedelta(seconds=RETRY_DELAYS[d.attempts - 1])
            result = "retrying"
        else:
            d.status = "failed"
            result = "failed"
            logger.warning("Webhook delivery %s to %s failed: %s", d.id, ep.name, error)
    db.commit()
    return result


def deliver_pending(db: Session, *, now: datetime | None = None, limit: int = 50) -> dict[str, int]:
    now = now or datetime.now(UTC)
    rows = db.scalars(
        select(WebhookDelivery).where(WebhookDelivery.status == "pending", WebhookDelivery.next_attempt_at <= now).order_by(WebhookDelivery.created_at).limit(limit)
    ).all()
    counts = {"sent": 0, "retrying": 0, "failed": 0}
    for d in rows:
        counts[deliver(db, d, now=now)] += 1
    return counts


def cleanup_old(db: Session, days: int = 30) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    old = db.scalars(select(WebhookDelivery).where(WebhookDelivery.created_at < cutoff, WebhookDelivery.status != "pending")).all()
    for d in old:
        db.delete(d)
    db.commit()
    return len(old)
