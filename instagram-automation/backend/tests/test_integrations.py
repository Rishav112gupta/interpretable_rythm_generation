"""Scheduler planning, Google Sheets (mock), competitor research, security helpers, storage/DB."""

from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import select

from app.core.errors import SheetsError, ValidationFailed
from app.core.logging import redact
from app.core.security import decrypt_secret, encrypt_secret
from app.models import ContentIdea, IntegrationLog, Post, PostStatus, RecurringSchedule, StrategyInsight
from app.services import google_sheets as sheets
from app.services.competitors import analysis
from app.services.content import workflow
from app.services.instagram import publisher
from app.services.scheduling import planner
from tests.helpers import category, make_generated_post


# ---------------------------------------------------------------- scheduling
def _schedule(db, **kw) -> RecurringSchedule:
    kw.setdefault("start_date", date.today())
    s = RecurringSchedule(
        name="Every 4th day",
        interval_days=4,
        post_time=time(18, 0),
        timezone="Asia/Kolkata",
        generation_lead_hours=72,
        category_id=category(db, "EXAM").id,
        topic_pool=["Revision tips", "Time management", "Exam-day checklist"],
        cta="Follow for more",
        **kw,
    )
    db.add(s)
    db.commit()
    return s


def test_planner_creates_every_4th_day_slots_idempotently(db):
    s = _schedule(db)
    created = planner.plan_schedule(db, s)
    assert len(created) >= 4
    slots = sorted(p.desired_publish_at for p in created)
    gaps = {(b - a).days for a, b in zip(slots, slots[1:], strict=False)}
    assert gaps == {4}
    assert all(p.status == PostStatus.DRAFT for p in created)
    assert planner.plan_schedule(db, s) == []  # second run creates nothing


def test_topic_rotation(db):
    s = _schedule(db)
    created = sorted(planner.plan_schedule(db, s), key=lambda p: p.desired_publish_at)
    assert [p.topic for p in created[:3]] == ["Revision tips", "Time management", "Exam-day checklist"] or len({p.topic for p in created}) == 3


def test_generation_clock_respects_lead_time(db):
    s = _schedule(db, start_date=date.today() + timedelta(days=1))
    planner.plan_schedule(db, s)
    result = planner.generate_due_content(db, limit=50)
    posts = db.scalars(select(Post).where(Post.schedule_id == s.id)).all()
    now = datetime.now(UTC)
    for p in posts:
        due = p.desired_publish_at - timedelta(hours=72) <= now
        assert (p.status == PostStatus.NEEDS_REVIEW) == due
    assert result["generated"] >= 1


def test_generation_without_topics_uses_ai_ideas(db):
    s = _schedule(db, start_date=date.today() + timedelta(days=1))
    s.topic_pool = []
    db.commit()
    planner.plan_schedule(db, s)
    planner.generate_due_content(db, limit=1)
    p = db.scalars(select(Post).where(Post.schedule_id == s.id, Post.status == PostStatus.NEEDS_REVIEW)).first()
    assert p is not None and p.topic and p.idea_id
    assert db.scalars(select(ContentIdea)).first() is not None


def test_publishing_clock_ignores_unapproved_and_warns(db, ig_mock):
    s = _schedule(db)
    post = planner.plan_schedule(db, s)[0]
    planner.generate_due_content(db)
    db.refresh(post)
    now = post.desired_publish_at + timedelta(minutes=1)
    assert publisher.due_post_ids(db, now) == []
    assert planner.warn_missed_slots(db, now) >= 1
    assert db.scalars(select(IntegrationLog).where(IntegrationLog.source == "scheduler")).first() is not None
    assert ig_mock.media == {}


def test_approved_schedule_post_publishes_at_slot(db, ig_mock):
    s = _schedule(db, start_date=date.today() + timedelta(days=1))
    planner.plan_schedule(db, s)
    planner.generate_due_content(db)
    post = db.scalars(select(Post).where(Post.schedule_id == s.id, Post.status == PostStatus.NEEDS_REVIEW)).first()
    when = planner.auto_schedule_on_approval(db, post)
    workflow.approve(db, post, actor_id=1, acknowledge_flags=True, schedule_at=when)
    db.commit()
    assert post.status == PostStatus.SCHEDULED and post.scheduled_at == post.desired_publish_at
    assert publisher.due_post_ids(db, post.scheduled_at - timedelta(minutes=1)) == []
    assert publisher.due_post_ids(db, post.scheduled_at + timedelta(seconds=1)) == [post.id]


def test_schedule_api_preview(client, admin_headers):
    r = client.post(
        "/api/schedules/preview",
        json={"start_date": "2026-10-01", "interval_days": 4, "post_time": "18:00", "timezone": "Asia/Kolkata", "count": 3},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert [x[:16] for x in r.json()] == ["2026-10-01T12:30", "2026-10-05T12:30", "2026-10-09T12:30"]


def test_schedule_api_create(client, admin_headers):
    body = {"name": "Every 4 days", "start_date": date.today().isoformat(), "interval_days": 4, "post_time": "18:00", "timezone": "Asia/Kolkata", "topic_pool": ["A", "B"]}
    r = client.post("/api/schedules", json=body, headers=admin_headers)
    assert r.status_code == 201, r.text
    assert len(r.json()["next_slots"]) == 5
    bad = {**body, "timezone": "Bad/Zone"}
    assert client.post("/api/schedules", json=bad, headers=admin_headers).status_code == 422


# ------------------------------------------------------------ Google Sheets
def test_sheets_export_and_import(db):
    client = sheets.MockSheetClient([sheets.COLUMNS, ["", "", "EXAM", "Mock test announcement", "Class 12", "NEW"] + [""] * 6])
    sheets.set_sheet_client(client)
    make_generated_post(db)
    result = sheets.sync(db, tz="Asia/Kolkata")
    assert result["imported"] == 1
    imported = db.scalars(select(Post).where(Post.topic == "Mock test announcement")).one()
    assert imported.status == PostStatus.DRAFT and imported.category.key == "EXAM"
    rows = client.rows
    assert rows[0] == sheets.COLUMNS
    assert rows[1][0] == str(imported.id)  # ID written back -> not imported twice
    assert len(rows) == 3
    again = sheets.sync(db, tz="Asia/Kolkata")
    assert again["imported"] == 0 and len(client.rows) == 3


def test_sheets_failure_is_logged_not_silent(db):
    sheets.set_sheet_client(sheets.MockSheetClient(fail=True))
    with pytest.raises(SheetsError):
        sheets.sync(db, tz="Asia/Kolkata")
    assert db.scalars(select(IntegrationLog).where(IntegrationLog.source == "google_sheets")).first() is not None


def test_sheets_api_sync(client, admin_headers):
    r = client.post("/api/sheets/sync", headers=admin_headers)
    assert r.status_code == 200 and r.json()["mock"] is True
    assert client.get("/api/sheets/preview", headers=admin_headers).json()["rows"][0] == sheets.COLUMNS


# -------------------------------------------------------------- competitors
CSV = """competitor,content_topic,content_type,caption_summary,visual_style,cta_used,observed_strategy
RivalCo,Exam tips,carousel,Five revision tips,Bright yellow cards,Comment YES,Targets anxious students
RivalCo,Result celebration,image,Topper photos,Photo collage,DM to enroll,Social proof
OtherEd,Exam tips,reel,Quick hacks,Fast cuts,Follow for more,Short-form hooks
"""


def test_competitor_csv_import_and_analysis(db):
    assert analysis.import_observations_csv(db, CSV) == 3
    insight = analysis.analyze(db)
    assert insight.observation_count == 3
    assert any("Exam tips" in t for t in insight.insights["common_topics"])
    assert db.scalars(select(StrategyInsight)).first() is not None


def test_competitor_analysis_requires_observations(db):
    with pytest.raises(ValidationFailed):
        analysis.analyze(db)


def test_competitor_csv_requires_header(db):
    with pytest.raises(ValidationFailed):
        analysis.import_observations_csv(db, "a,b\n1,2")


def test_insights_feed_generation_context(db):
    from app.services.content.generation import latest_insights

    analysis.import_observations_csv(db, CSV)
    analysis.analyze(db)
    ctx = latest_insights(db)
    assert ctx and "common_topics" in ctx


# ------------------------------------------------------------------ security
def test_token_encryption_roundtrip():
    enc = encrypt_secret("IGAAsupersecret")
    assert "IGAAsupersecret" not in enc
    assert decrypt_secret(enc) == "IGAAsupersecret"


def test_log_redaction():
    line = "GET https://graph.instagram.com/v25.0/me?fields=id&access_token=IGAAabcdef1234567890abcdef1234 Bearer sk-ant-abc123456789"
    out = redact(line)
    assert "IGAAabcdef1234567890abcdef1234" not in out
    assert "sk-ant-abc123456789" not in out
    assert "[REDACTED]" in out


def test_production_config_validation(monkeypatch):
    from app.core.config import Settings

    s = Settings(app_env="production", secret_key="short", token_encryption_key="", public_base_url="http://localhost:8000")
    problems = s.validate_for_production()
    assert len(problems) == 3


def test_database_timestamps_are_timezone_aware(db):
    post = make_generated_post(db)
    db.expire_all()
    fresh = db.get(Post, post.id)
    assert fresh.created_at.tzinfo is not None and fresh.generated_at.tzinfo is not None


def test_idea_model_defaults(db):
    idea = ContentIdea(title="t")
    db.add(idea)
    db.commit()
    assert idea.status == "new"
