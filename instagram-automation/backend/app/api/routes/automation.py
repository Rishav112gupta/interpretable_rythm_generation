"""Automation integrations (n8n etc.): API keys and outgoing webhooks. Admin only."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import admin
from app.core.errors import ValidationFailed
from app.database.session import get_db
from app.models import ApiKey, Role, User, WebhookDelivery, WebhookEndpoint
from app.services.automation import api_keys, webhooks

router = APIRouter(tags=["automation"])


# ------------------------------------------------------------------ schemas
class ApiKeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    role: Role = Role.EDITOR


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    prefix: str
    role: str = ""
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreated(ApiKeyOut):
    key: str = Field(description="Shown only once - store it in n8n's credentials now.")


class WebhookIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=8, max_length=1024)
    events: list[str] = Field(default_factory=lambda: ["*"])
    is_active: bool = True

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        p = urlparse(v)
        if p.scheme not in ("http", "https") or not p.netloc:
            raise ValueError("must be an http(s) URL")
        return v

    @field_validator("events")
    @classmethod
    def _events(cls, v: list[str]) -> list[str]:
        unknown = [e for e in v if e != "*" and e not in webhooks.EVENTS]
        if unknown:
            raise ValueError(f"unknown events: {', '.join(unknown)}")
        return v or ["*"]


class WebhookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    url: str
    events: list[str]
    is_active: bool
    last_delivery_at: datetime | None
    last_status_code: int | None
    last_error: str
    created_at: datetime


class WebhookCreated(WebhookOut):
    secret: str = Field(description="Signing secret - shown only once.")


class DeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    endpoint_id: int
    event: str
    status: str
    attempts: int
    last_status_code: int | None
    last_error: str
    created_at: datetime
    delivered_at: datetime | None
    next_attempt_at: datetime


# ----------------------------------------------------------------- API keys
def _key_out(row: ApiKey) -> ApiKeyOut:
    out = ApiKeyOut.model_validate(row)
    out.role = row.service_user.role if row.service_user else ""
    return out


@router.get("/api-keys", response_model=list[ApiKeyOut])
def list_keys(_: User = Depends(admin), db: Session = Depends(get_db)):
    return [_key_out(k) for k in db.scalars(select(ApiKey).order_by(ApiKey.id.desc())).unique().all()]


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
def create_key(body: ApiKeyIn, user: User = Depends(admin), db: Session = Depends(get_db)):
    row, plaintext = api_keys.create_api_key(db, name=body.name, role=body.role, created_by_id=user.id)
    return ApiKeyCreated(**_key_out(row).model_dump(), key=plaintext)


@router.delete("/api-keys/{key_id}", status_code=204)
def revoke_key(key_id: int, _: User = Depends(admin), db: Session = Depends(get_db)):
    row = db.get(ApiKey, key_id)
    if row is None:
        raise HTTPException(404, "API key not found.")
    api_keys.revoke(db, row)


# ----------------------------------------------------------------- webhooks
@router.get("/webhooks/events")
def list_events(_: User = Depends(admin)):
    return [{"event": k, "description": v} for k, v in webhooks.EVENTS.items()]


@router.get("/webhooks", response_model=list[WebhookOut])
def list_webhooks(_: User = Depends(admin), db: Session = Depends(get_db)):
    return db.scalars(select(WebhookEndpoint).order_by(WebhookEndpoint.id)).all()


@router.post("/webhooks", response_model=WebhookCreated, status_code=201)
def create_webhook(body: WebhookIn, _: User = Depends(admin), db: Session = Depends(get_db)):
    ep, secret = webhooks.create_endpoint(db, name=body.name, url=body.url, events=body.events)
    if not body.is_active:
        ep.is_active = False
        db.commit()
    return WebhookCreated(**WebhookOut.model_validate(ep).model_dump(), secret=secret)


@router.put("/webhooks/{wid}", response_model=WebhookOut)
def update_webhook(wid: int, body: WebhookIn, _: User = Depends(admin), db: Session = Depends(get_db)):
    ep = db.get(WebhookEndpoint, wid)
    if ep is None:
        raise HTTPException(404, "Webhook not found.")
    ep.name, ep.url, ep.events, ep.is_active = body.name, body.url, body.events, body.is_active
    db.commit()
    return ep


@router.post("/webhooks/{wid}/rotate-secret", response_model=WebhookCreated)
def rotate_secret(wid: int, _: User = Depends(admin), db: Session = Depends(get_db)):
    from app.core.security import encrypt_secret

    ep = db.get(WebhookEndpoint, wid)
    if ep is None:
        raise HTTPException(404, "Webhook not found.")
    secret = webhooks.new_secret()
    ep.secret_encrypted = encrypt_secret(secret)
    db.commit()
    return WebhookCreated(**WebhookOut.model_validate(ep).model_dump(), secret=secret)


@router.delete("/webhooks/{wid}", status_code=204)
def delete_webhook(wid: int, _: User = Depends(admin), db: Session = Depends(get_db)):
    ep = db.get(WebhookEndpoint, wid)
    if ep is None:
        raise HTTPException(404, "Webhook not found.")
    db.delete(ep)
    db.commit()


@router.post("/webhooks/{wid}/test", response_model=DeliveryOut)
def test_webhook(wid: int, _: User = Depends(admin), db: Session = Depends(get_db)):
    """Send a `webhook.test` event right now and return the delivery result."""
    ep = db.get(WebhookEndpoint, wid)
    if ep is None:
        raise HTTPException(404, "Webhook not found.")
    if not ep.is_active:
        raise ValidationFailed("Enable the webhook before testing it.")
    delivery = webhooks.enqueue(db, "webhook.test", {"message": "Test event from Instagram Automation. If you can read this in n8n, the connection works."}, endpoint_id=ep.id)[0]
    db.commit()
    webhooks.deliver(db, delivery, retry=False)
    db.refresh(delivery)
    return delivery


@router.get("/webhooks/deliveries", response_model=list[DeliveryOut])
def list_deliveries(endpoint_id: int | None = None, limit: int = 100, _: User = Depends(admin), db: Session = Depends(get_db)):
    stmt = select(WebhookDelivery).order_by(WebhookDelivery.created_at.desc()).limit(min(limit, 500))
    if endpoint_id:
        stmt = stmt.where(WebhookDelivery.endpoint_id == endpoint_id)
    return db.scalars(stmt).all()
