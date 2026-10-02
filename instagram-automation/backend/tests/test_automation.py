"""API keys and outgoing webhooks (n8n integration). No real network calls."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.models import ApiKey, Role, WebhookDelivery
from app.services.automation import webhooks
from app.services.content import workflow
from app.services.instagram import publisher
from tests.helpers import make_generated_post, make_scheduled_post


class Receiver:
    """Fake n8n: records requests and answers with a configurable status code."""

    def __init__(self, status: int = 200):
        self.status = status
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, json={"ok": True})

    def events(self) -> list[str]:
        return [r.headers["X-IA-Event"] for r in self.requests]


@pytest.fixture
def receiver():
    r = Receiver()
    webhooks.set_transport(httpx.MockTransport(r))
    yield r
    webhooks.set_transport(None)


def _endpoint(db, events=("*",)):
    ep, secret = webhooks.create_endpoint(db, name="n8n", url="http://n8n:5678/webhook/insta", events=list(events))
    return ep, secret


# ---------------------------------------------------------------- API keys
def test_api_key_lifecycle(client, admin_headers):
    r = client.post("/api/api-keys", json={"name": "n8n", "role": "editor"}, headers=admin_headers)
    assert r.status_code == 201
    key = r.json()["key"]
    assert key.startswith("ia_") and r.json()["prefix"] == key[:10]

    h = {"X-API-Key": key}
    assert client.get("/api/posts", headers=h).status_code == 200
    created = client.post("/api/posts", json={"topic": "From n8n", "generate": True}, headers=h)
    assert created.status_code == 201 and created.json()["status"] == "NEEDS_REVIEW"
    assert created.json()["created_by_name"] == "API key: n8n"

    # editor key cannot approve or publish (human stays in the loop) nor manage settings
    pid = created.json()["id"]
    assert client.post(f"/api/posts/{pid}/approve", json={"acknowledge_flags": True}, headers=h).status_code == 403
    assert client.post(f"/api/posts/{pid}/publish", headers=h).status_code == 403
    assert client.get("/api/api-keys", headers=h).status_code == 403

    listed = client.get("/api/api-keys", headers=admin_headers).json()
    assert "key" not in listed[0] and listed[0]["last_used_at"] is not None

    assert client.delete(f"/api/api-keys/{listed[0]['id']}", headers=admin_headers).status_code == 204
    assert client.get("/api/posts", headers=h).status_code == 401


def test_api_key_is_hashed_and_service_user_cannot_log_in(client, admin_headers, db):
    key = client.post("/api/api-keys", json={"name": "bot", "role": "viewer"}, headers=admin_headers).json()["key"]
    row = db.scalars(select(ApiKey)).one()
    assert key not in row.key_hash and len(row.key_hash) == 64
    r = client.post("/api/auth/login", json={"email": row.service_user.email, "password": "anything"})
    assert r.status_code == 401
    users = client.get("/api/users", headers=admin_headers).json()
    assert all("service.local" not in u["email"] for u in users)


def test_admin_api_keys_not_allowed(client, admin_headers):
    assert client.post("/api/api-keys", json={"name": "x", "role": "admin"}, headers=admin_headers).status_code == 422


def test_invalid_api_key(client):
    assert client.get("/api/posts", headers={"X-API-Key": "ia_nope"}).status_code == 401
    assert client.get("/api/posts", headers={"X-API-Key": "garbage"}).status_code == 401


def test_only_admin_manages_automation(client, headers_for):
    h = headers_for(Role.APPROVER)
    assert client.get("/api/webhooks", headers=h).status_code == 403
    assert client.post("/api/api-keys", json={"name": "x"}, headers=h).status_code == 403


# ---------------------------------------------------------------- webhooks
def test_workflow_events_are_queued_and_delivered_signed(db, receiver, ig_mock):
    ep, secret = _endpoint(db)
    post = make_scheduled_post(db)
    publisher.publish_post(db, post.id)
    webhooks.deliver_pending(db)

    events = receiver.events()
    for e in ("post.needs_review", "post.approved", "post.scheduled", "post.published"):
        assert e in events, (e, events)
    req = receiver.requests[events.index("post.published")]
    body = req.content
    assert webhooks.verify(secret, req.headers["X-IA-Timestamp"], body, req.headers["X-IA-Signature"])
    assert not webhooks.verify("wrong-secret", req.headers["X-IA-Timestamp"], body, req.headers["X-IA-Signature"])
    payload = json.loads(body)
    assert payload["event"] == "post.published" and payload["id"] == req.headers["X-IA-Delivery"]
    assert payload["data"]["post"]["id"] == post.id
    assert payload["data"]["post"]["published_via_mock"] is True
    assert payload["data"]["post"]["dashboard_url"].endswith(f"/posts/{post.id}")
    assert all(d.status == "success" for d in db.scalars(select(WebhookDelivery)))


def test_event_filtering(db, receiver):
    _endpoint(db, events=["post.needs_review"])
    make_generated_post(db)
    webhooks.deliver_pending(db)
    assert receiver.events() == ["post.needs_review"]


def test_failed_publish_and_retry_events(db, receiver, ig_mock):
    from app.services.instagram.errors import InstagramAPIError

    _endpoint(db, events=["post.publish_retry", "post.failed", "instagram.token_expired"])
    post = make_scheduled_post(db)
    ig_mock.fail_next["create_image_container"] = [InstagramAPIError("Temporary", transient=True)]
    publisher.publish_post(db, post.id)
    post2 = make_scheduled_post(db)
    ig_mock.fail_next["create_image_container"] = [InstagramAPIError("Bad token", graph_code=190, token_problem=True)]
    publisher.publish_post(db, post2.id)
    webhooks.deliver_pending(db)
    assert sorted(receiver.events()) == ["instagram.token_expired", "post.failed", "post.publish_retry"]


def test_receiver_down_retries_with_backoff_then_fails(db, receiver):
    receiver.status = 503
    _endpoint(db)
    webhooks.enqueue(db, "webhook.test", {"x": 1})
    db.commit()
    now = datetime.now(UTC)
    for i, delay in enumerate(webhooks.RETRY_DELAYS):
        assert webhooks.deliver_pending(db, now=now)["retrying"] == 1
        d = db.scalars(select(WebhookDelivery)).one()
        assert d.status == "pending" and d.attempts == i + 1
        assert abs((d.next_attempt_at - now).total_seconds() - delay) < 2
        assert webhooks.deliver_pending(db, now=now)["retrying"] == 0  # not due yet
        now = d.next_attempt_at
    assert webhooks.deliver_pending(db, now=now)["failed"] == 1
    d = db.scalars(select(WebhookDelivery)).one()
    assert d.status == "failed" and "503" in d.last_error


def test_receiver_recovers(db, receiver):
    receiver.status = 500
    _endpoint(db)
    webhooks.enqueue(db, "webhook.test", {})
    db.commit()
    webhooks.deliver_pending(db)
    receiver.status = 200
    webhooks.deliver_pending(db, now=datetime.now(UTC) + timedelta(minutes=5))
    assert db.scalars(select(WebhookDelivery)).one().status == "success"


def test_no_webhook_for_rolled_back_change(db, receiver):
    _endpoint(db)
    post = make_generated_post(db)
    webhooks.deliver_pending(db)
    receiver.requests.clear()
    workflow.approve(db, post, actor_id=1, acknowledge_flags=True)
    db.rollback()  # the approval never happened
    webhooks.deliver_pending(db)
    assert receiver.requests == []


def test_webhook_api_create_test_and_log(client, admin_headers, receiver):
    r = client.post("/api/webhooks", json={"name": "n8n", "url": "http://n8n:5678/webhook/x", "events": ["post.published"]}, headers=admin_headers)
    assert r.status_code == 201 and r.json()["secret"].startswith("whsec_")
    wid = r.json()["id"]
    t = client.post(f"/api/webhooks/{wid}/test", headers=admin_headers).json()
    assert t["status"] == "success" and t["event"] == "webhook.test"
    assert receiver.events() == ["webhook.test"]
    assert len(client.get("/api/webhooks/deliveries", headers=admin_headers).json()) == 1
    assert "secret" not in client.get("/api/webhooks", headers=admin_headers).json()[0]
    assert len(client.get("/api/webhooks/events", headers=admin_headers).json()) >= 10
    bad = client.post("/api/webhooks", json={"name": "x", "url": "ftp://x", "events": ["nope"]}, headers=admin_headers)
    assert bad.status_code == 422
    rotated = client.post(f"/api/webhooks/{wid}/rotate-secret", headers=admin_headers).json()["secret"]
    assert rotated != r.json()["secret"]


def test_test_failure_is_not_retried(client, admin_headers, receiver):
    receiver.status = 404
    wid = client.post("/api/webhooks", json={"name": "n8n", "url": "http://n8n:5678/webhook/x"}, headers=admin_headers).json()["id"]
    t = client.post(f"/api/webhooks/{wid}/test", headers=admin_headers).json()
    assert t["status"] == "failed" and t["last_status_code"] == 404


def test_webhook_errors_never_break_workflow(db, monkeypatch):
    _endpoint(db)
    monkeypatch.setattr(webhooks, "enqueue", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    post = make_generated_post(db)  # must not raise
    assert post.status == "NEEDS_REVIEW"


def test_post_created_via_api_emits_event(client, admin_headers, receiver, db):
    _endpoint(db, events=["post.created"])
    client.post("/api/posts", json={"topic": "Hello"}, headers=admin_headers)
    webhooks.deliver_pending(db)
    assert receiver.events() == ["post.created"]
