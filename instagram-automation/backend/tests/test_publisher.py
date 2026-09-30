"""Instagram publishing: happy path, retries, duplicate prevention, error handling.

All tests use the in-memory MockInstagramClient - nothing is sent to Instagram.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.errors import DuplicatePublishError, InvalidTransitionError
from app.models import AccountStatus, InstagramAccount, Post, PostStatus, PublishAttempt
from app.services import app_settings
from app.services.content import workflow
from app.services.instagram import publisher
from app.services.instagram.client import MockInstagramClient
from app.services.instagram.errors import InstagramAPIError
from tests.helpers import make_generated_post, make_scheduled_post


def transient():
    return InstagramAPIError("Service temporarily unavailable", graph_code=2, http_status=503, transient=True)


def test_scheduled_post_is_published_via_official_flow(db, ig_mock):
    post = make_scheduled_post(db)
    result = publisher.publish_due_posts(db)
    db.refresh(post)
    assert result["published"] == 1
    assert post.status == PostStatus.PUBLISHED
    assert post.instagram_media_id.startswith("mock_media_")
    assert post.published_via_mock is True
    # container -> status -> publish, in that order
    ops = [c for c in ig_mock.calls if c in ("create_image_container", "get_container_status", "publish_container")]
    assert ops[0] == "create_image_container" and ops[-1] == "publish_container"
    caption = next(iter(ig_mock.containers.values())).caption
    assert post.caption in caption and "#" in caption


def test_unapproved_posts_are_never_published(db, ig_mock):
    post = make_generated_post(db)
    post.scheduled_at = datetime.now(UTC) - timedelta(minutes=5)
    db.commit()
    assert publisher.due_post_ids(db) == []
    with pytest.raises(InvalidTransitionError):
        publisher.publish_post(db, post.id, manual=True)
    assert ig_mock.media == {}


def test_future_posts_not_published_early(db, ig_mock):
    post = make_scheduled_post(db, when=datetime.now(UTC) + timedelta(hours=2))
    assert publisher.publish_due_posts(db)["published"] == 0
    db.refresh(post)
    assert post.status == PostStatus.SCHEDULED


def test_duplicate_publish_is_refused(db, ig_mock):
    post = make_scheduled_post(db)
    publisher.publish_post(db, post.id)
    with pytest.raises(DuplicatePublishError):
        publisher.publish_post(db, post.id, manual=True)
    assert len(ig_mock.media) == 1


def test_atomic_claim_only_one_winner(db, ig_mock):
    post = make_scheduled_post(db)
    assert publisher._claim(db, post.id, [PostStatus.SCHEDULED]) is True
    assert publisher._claim(db, post.id, [PostStatus.SCHEDULED]) is False


def test_transient_errors_retry_1_5_15_minutes_then_fail(db, ig_mock):
    post = make_scheduled_post(db)
    ig_mock.fail_next["create_image_container"] = [transient() for _ in range(10)]
    expected = [60, 300, 900]
    for i, delay in enumerate(expected, start=1):
        before = datetime.now(UTC)
        publisher.publish_post(db, post.id)
        db.refresh(post)
        assert post.status == PostStatus.SCHEDULED
        assert post.publish_attempts == i
        assert abs((post.next_retry_at - before).total_seconds() - delay) < 5
        assert publisher.due_post_ids(db) == []  # not due until the retry time
        post.next_retry_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    publisher.publish_post(db, post.id)
    db.refresh(post)
    assert post.status == PostStatus.FAILED
    assert post.publish_attempts == 4
    assert ig_mock.media == {}
    attempts = db.scalars(select(PublishAttempt).where(PublishAttempt.post_id == post.id)).all()
    assert len(attempts) == 4 and all(not a.success for a in attempts)


def test_transient_error_then_success(db, ig_mock):
    post = make_scheduled_post(db)
    ig_mock.fail_next["publish_container"] = [transient()]
    publisher.publish_post(db, post.id)
    db.refresh(post)
    assert post.status == PostStatus.SCHEDULED
    post.next_retry_at = datetime.now(UTC)
    db.commit()
    publisher.publish_due_posts(db)
    db.refresh(post)
    assert post.status == PostStatus.PUBLISHED
    assert len(ig_mock.media) == 1
    # The second attempt reused the committed container instead of creating another
    assert ig_mock.calls.count("create_image_container") == 1


def test_invalid_token_fails_immediately_and_marks_account(db, ig_mock):
    post = make_scheduled_post(db)
    ig_mock.fail_next["create_image_container"] = [InstagramAPIError("Invalid OAuth access token", graph_code=190, http_status=400, token_problem=True)]
    publisher.publish_post(db, post.id)
    db.refresh(post)
    assert post.status == PostStatus.FAILED
    assert post.publish_attempts == 1
    acc = db.get(InstagramAccount, 1)
    assert acc.status == AccountStatus.TOKEN_EXPIRED
    assert "Invalid OAuth" in acc.last_error


def test_lost_response_after_publish_does_not_duplicate(db, ig_mock):
    """media_publish succeeded on Instagram but the response timed out."""
    post = make_scheduled_post(db)
    ig_mock.publish_succeeds_then_times_out = True
    publisher.publish_post(db, post.id)
    db.refresh(post)
    assert post.status == PostStatus.PUBLISHED
    assert len(ig_mock.media) == 1
    assert post.instagram_media_id in ig_mock.media
    assert any(e.event_type == "publish_recovered" for e in post.events)


def test_crashed_worker_recovery_verifies_container_first(db, ig_mock):
    post = make_scheduled_post(db)
    # Simulate: container created and published, then the worker died before saving.
    cid = ig_mock.create_image_container("t", ig_mock.ig_user_id, post.image_url, "caption")
    ig_mock.publish_container("t", ig_mock.ig_user_id, cid)
    post.instagram_container_id = cid
    post.status = PostStatus.PUBLISHING
    post.publishing_started_at = datetime.now(UTC) - timedelta(hours=1)
    db.commit()
    assert publisher.recover_stale_publishing(db) == 1
    publisher.publish_due_posts(db)
    db.refresh(post)
    assert post.status == PostStatus.PUBLISHED
    assert len(ig_mock.media) == 1  # no second post


def test_expired_container_is_replaced(db, ig_mock):
    post = make_scheduled_post(db)
    cid = ig_mock.create_image_container("t", ig_mock.ig_user_id, post.image_url, "c")
    ig_mock.containers[cid].status = "EXPIRED"
    post.instagram_container_id = cid
    db.commit()
    publisher.publish_post(db, post.id)
    db.refresh(post)
    assert post.status == PostStatus.PUBLISHED
    assert post.instagram_container_id != cid


def test_publishing_paused_blocks_everything(db, ig_mock):
    post = make_scheduled_post(db)
    app_settings.set_setting(db, "publishing_enabled", False)
    db.commit()
    assert publisher.publish_due_posts(db).get("paused") == 1
    db.refresh(post)
    assert post.status == PostStatus.SCHEDULED
    assert ig_mock.media == {}


def test_publish_limit_reached_is_retried_later(db, ig_mock):
    post = make_scheduled_post(db)
    ig_mock.get_publishing_limit = lambda *a: {"quota_usage": 100, "config": {"quota_total": 100}}
    publisher.publish_post(db, post.id)
    db.refresh(post)
    assert post.status == PostStatus.SCHEDULED and post.next_retry_at is not None
    assert "limit" in post.last_error


def test_not_connected_account_fails_clearly(db):
    class Disconnected(MockInstagramClient):
        is_mock = False

    from app.services.instagram import account

    account.set_client(Disconnected())
    post = make_scheduled_post(db)
    publisher.publish_post(db, post.id)
    db.refresh(post)
    assert post.status == PostStatus.FAILED
    assert "No Instagram account is connected" in post.last_error


def test_real_client_refuses_localhost_image_urls(db, monkeypatch):
    from app.core.config import settings
    from app.services.instagram import account

    class RealLike(MockInstagramClient):
        is_mock = False

    account.set_client(RealLike())
    monkeypatch.setattr(settings, "meta_access_token", "EAAtesttoken")
    monkeypatch.setattr(settings, "instagram_account_id", "123")
    post = make_scheduled_post(db)
    post.image_url = "http://localhost:8000/media/posts/x.jpg"
    db.commit()
    publisher.publish_post(db, post.id)
    db.refresh(post)
    assert post.status == PostStatus.FAILED
    assert "localhost" in post.last_error


def test_editing_scheduled_post_requires_reapproval(db, ig_mock):
    post = make_scheduled_post(db, when=datetime.now(UTC) + timedelta(days=1))
    post.caption = "Changed caption"
    workflow.after_content_edit(db, post, {"caption"}, actor_id=1)
    db.commit()
    assert post.status == PostStatus.NEEDS_REVIEW
    assert post.scheduled_at is None
    assert publisher.due_post_ids(db, datetime.now(UTC) + timedelta(days=2)) == []


def test_refresh_metrics_updates_counts(db, ig_mock):
    post = make_scheduled_post(db)
    publisher.publish_post(db, post.id)
    ig_mock.media[post.instagram_media_id]["like_count"] = 42
    assert publisher.refresh_metrics(db) == 1
    db.refresh(post)
    assert post.like_count == 42


def test_published_post_is_immutable(db, ig_mock):
    post = make_scheduled_post(db)
    publisher.publish_post(db, post.id)
    db.refresh(post)
    with pytest.raises(InvalidTransitionError):
        workflow.ensure_editable(post)
    with pytest.raises(InvalidTransitionError):
        workflow.reject(db, post, actor_id=1)
    assert db.scalar(select(Post).where(Post.id == post.id)).status == PostStatus.PUBLISHED


def test_db_failure_after_successful_publish_never_duplicates(db, ig_mock):
    """Instagram accepted the post but saving the result to the database failed mid-flush."""
    other = make_generated_post(db)
    other.instagram_media_id = "media_x"  # forces a UNIQUE violation when saving
    db.commit()
    post = make_scheduled_post(db)
    real_publish = ig_mock.publish_container

    def publish_then_collide(token, ig_user_id, container_id):
        real_publish(token, ig_user_id, container_id)
        return "media_x"

    ig_mock.publish_container = publish_then_collide
    publisher.publish_post(db, post.id)  # must not raise
    db.refresh(post)
    assert post.status == PostStatus.SCHEDULED  # queued for a safe retry
    assert post.instagram_container_id  # container id survived
    assert "database" in post.last_error.lower()
    other.instagram_media_id = None
    post.next_retry_at = datetime.now(UTC)
    db.commit()
    publisher.publish_due_posts(db)
    db.refresh(post)
    assert post.status == PostStatus.PUBLISHED
    assert len(ig_mock.media) == 1  # the retry recovered instead of posting again
