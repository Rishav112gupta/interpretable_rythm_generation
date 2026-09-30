"""HTTP API tests: auth, authorization, validation, post workflow."""

from datetime import UTC, datetime, timedelta

from app.models import Role


def _create(client, headers, **kw):
    cats = client.get("/api/categories", headers=headers).json()
    exam = next(c for c in cats if c["key"] == "EXAM")
    body = {
        "category_id": exam["id"],
        "topic": "Last-minute exam preparation",
        "target_audience": "Students",
        "tone": "Helpful and motivating",
        "cta": "Join our preparation program",
        "generate": True,
        **kw,
    }
    r = client.post("/api/posts", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_requires_authentication(client):
    assert client.get("/api/posts").status_code == 401
    assert client.get("/api/posts", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_login_wrong_password(client):
    r = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "nope"})
    assert r.status_code == 401


def test_login_rate_limited(client):
    codes = [client.post("/api/auth/login", json={"email": "x@example.com", "password": "bad"}).status_code for _ in range(12)]
    assert 429 in codes


def test_role_based_authorization(client, headers_for):
    viewer = headers_for(Role.VIEWER)
    assert client.get("/api/posts", headers=viewer).status_code == 200
    assert client.post("/api/posts", json={"topic": "x"}, headers=viewer).status_code == 403
    editor = headers_for(Role.EDITOR)
    post = _create(client, editor)
    # editors cannot approve or change settings
    assert client.post(f"/api/posts/{post['id']}/approve", json={"acknowledge_flags": True}, headers=editor).status_code == 403
    assert client.patch("/api/settings", json={"publishing_enabled": False}, headers=editor).status_code == 403
    assert client.get("/api/users", headers=editor).status_code == 403


def test_input_validation(client, admin_headers):
    r = client.post("/api/posts", json={"topic": ""}, headers=admin_headers)
    assert r.status_code == 422 and "topic" in r.json()["detail"]
    r = client.post("/api/posts", json={"topic": "x", "desired_publish_at": "2026-10-01T10:00:00"}, headers=admin_headers)
    assert r.status_code == 422  # naive datetime rejected
    r = client.post("/api/categories", json={"key": "bad key", "name": "x"}, headers=admin_headers)
    assert r.status_code == 422


def test_full_workflow_generate_edit_approve_schedule_publish(client, admin_headers, ig_mock):
    post = _create(client, admin_headers)
    assert post["status"] == "NEEDS_REVIEW"
    assert post["image_url"] and post["hashtags"]
    pid = post["id"]

    r = client.patch(f"/api/posts/{pid}", json={"caption": "Edited caption for students.", "hashtags": ["#exam prep", "study"]}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["hashtags"] == ["examprep", "study"]

    # Missing information -> approval requires explicit acknowledgement
    r = client.post(f"/api/posts/{pid}/approve", json={}, headers=admin_headers)
    assert r.status_code == 422
    r = client.post(f"/api/posts/{pid}/approve", json={"acknowledge_flags": True}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["status"] == "APPROVED"

    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    assert client.post(f"/api/posts/{pid}/schedule", json={"scheduled_at": past}, headers=admin_headers).status_code == 422
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    r = client.post(f"/api/posts/{pid}/schedule", json={"scheduled_at": future}, headers=admin_headers)
    assert r.json()["status"] == "SCHEDULED"

    r = client.post(f"/api/posts/{pid}/publish", headers=admin_headers)
    body = r.json()
    assert body["status"] == "PUBLISHED" and body["published_via_mock"] is True
    assert any("MOCK MODE" in w for w in body["warnings"])

    r = client.post(f"/api/posts/{pid}/publish", headers=admin_headers)
    assert r.status_code == 409 and r.json()["error"] == "duplicate_publish"
    assert client.patch(f"/api/posts/{pid}", json={"caption": "x"}, headers=admin_headers).status_code == 409


def test_approve_with_desired_time_auto_schedules(client, admin_headers):
    when = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    post = _create(client, admin_headers, desired_publish_at=when.isoformat(), important_info="Mock test on Sunday for Batch A")
    r = client.post(f"/api/posts/{post['id']}/approve", json={"acknowledge_flags": True}, headers=admin_headers)
    assert r.json()["status"] == "SCHEDULED"
    assert datetime.fromisoformat(r.json()["scheduled_at"]) == when


def test_reject_and_regenerate(client, admin_headers):
    post = _create(client, admin_headers)
    r = client.post(f"/api/posts/{post['id']}/reject", json={"reason": "Too generic"}, headers=admin_headers)
    assert r.json()["status"] == "REJECTED" and r.json()["rejected_reason"] == "Too generic"
    r = client.post(f"/api/posts/{post['id']}/regenerate-text", json={"feedback": "More specific"}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "NEEDS_REVIEW"
    assert r.json()["regeneration_count"] == 1
    r = client.post(f"/api/posts/{post['id']}/regenerate-image", headers=admin_headers)
    assert r.json()["image_regeneration_count"] == 1


def test_upload_image_validation(client, admin_headers):
    post = _create(client, admin_headers)
    r = client.post(f"/api/posts/{post['id']}/image", files={"file": ("x.jpg", b"not an image", "image/jpeg")}, headers=admin_headers)
    assert r.status_code == 422
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (800, 2000), "red").save(buf, format="PNG")  # too tall -> will be cropped to 4:5
    r = client.post(f"/api/posts/{post['id']}/image", files={"file": ("x.png", buf.getvalue(), "image/png")}, data={"apply_template": "false"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["image_provider"] == "upload"


def test_instagram_status_never_exposes_tokens(client, admin_headers):
    r = client.get("/api/instagram/status", headers=admin_headers)
    assert r.status_code == 200
    body = r.text.lower()
    assert "access_token" not in body and "mock-token" not in body
    assert r.json()["is_mock"] is True


def test_dashboard_and_calendar(client, admin_headers):
    _create(client, admin_headers)
    d = client.get("/api/dashboard", headers=admin_headers).json()
    assert d["counts"]["pending_approval"] == 1
    start = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    end = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    r = client.get("/api/posts/calendar", params={"start": start, "end": end}, headers=admin_headers)
    assert r.status_code == 200


def test_categories_admin_can_add_and_deactivate(client, admin_headers):
    r = client.post("/api/categories", json={"key": "WEBINAR", "name": "Webinar"}, headers=admin_headers)
    assert r.status_code == 201
    cid = r.json()["id"]
    client.patch(f"/api/categories/{cid}", json={"is_active": False}, headers=admin_headers)
    keys = [c["key"] for c in client.get("/api/categories", headers=admin_headers).json()]
    assert "WEBINAR" not in keys
    keys = [c["key"] for c in client.get("/api/categories?include_inactive=true", headers=admin_headers).json()]
    assert "WEBINAR" in keys


def test_template_preview_and_validation(client, admin_headers):
    tpl = client.get("/api/templates", headers=admin_headers).json()[0]
    r = client.get(f"/api/templates/{tpl['id']}/preview", headers=admin_headers)
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    r = client.patch(f"/api/templates/{tpl['id']}", json={"layout": {"elements": [{"type": "video"}]}}, headers=admin_headers)
    assert r.status_code == 422


def test_ideas_generate_and_convert(client, admin_headers):
    ideas = client.post("/api/ideas/generate", json={"count": 7}, headers=admin_headers).json()
    assert len(ideas) == 7
    r = client.post(f"/api/ideas/{ideas[0]['id']}/convert", headers=admin_headers)
    assert r.status_code == 200 and r.json()["status"] == "DRAFT" and r.json()["topic"] == ideas[0]["title"]
    remaining = client.get("/api/ideas", headers=admin_headers).json()
    assert len(remaining) == 6


def test_settings_timezone_validation(client, admin_headers):
    assert client.patch("/api/settings", json={"timezone": "Nowhere/City"}, headers=admin_headers).status_code == 422
    r = client.patch("/api/settings", json={"timezone": "Europe/London"}, headers=admin_headers)
    assert r.json()["timezone"] == "Europe/London"
    assert r.json()["mock"]["instagram"] is True
