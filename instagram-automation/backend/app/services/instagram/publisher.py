"""Publishing orchestration: safe, idempotent, retrying.

Duplicate-post prevention (defence in depth):
  1. Atomic claim: `UPDATE posts SET status='PUBLISHING' WHERE id=? AND status IN (...)
     AND instagram_media_id IS NULL`. Only one worker/request can win.
  2. The container id is committed to the database *before* media_publish is called.
     On any retry we first ask Instagram for that container's status: if it is
     already PUBLISHED we record the result instead of publishing again.
  3. A post that already has an instagram_media_id can never be claimed again
     (and the column is UNIQUE).
  4. Crash recovery: a post stuck in PUBLISHING (worker died) is returned to the
     queue, and step 2 makes the retry safe.

Retries: temporary failures (network, 5xx, throttling) are retried after
1, 5 and 15 minutes (PUBLISH_RETRY_DELAYS), then the post is marked FAILED.
Permanent failures (bad token, missing permission, invalid image) fail at once.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, DuplicatePublishError, InvalidTransitionError
from app.models import AppSetting, Post, PostStatus, PublishAttempt
from app.services.ai.schemas import compose_caption, validate_caption_with_hashtags
from app.services.content.audit import log_integration, record_event
from app.services.instagram import account as account_service
from app.services.instagram.errors import InstagramAPIError, InstagramNotConnected
from app.services.storage import get_storage
from app.services.templates.renderer import check_instagram_image

logger = logging.getLogger(__name__)
S = PostStatus


def publishing_enabled(db: Session) -> bool:
    row = db.get(AppSetting, "publishing_enabled")
    if row is not None:
        return bool(row.value)
    return settings.publishing_enabled


def _claim(db: Session, post_id: int, allowed: list[str]) -> bool:
    now = datetime.now(UTC)
    result = db.execute(
        update(Post)
        .where(Post.id == post_id, Post.status.in_(allowed), Post.instagram_media_id.is_(None))
        .values(status=S.PUBLISHING, publishing_started_at=now, publish_attempts=Post.publish_attempts + 1)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return result.rowcount == 1


def publish_post(db: Session, post_id: int, *, actor_id: int | None = None, manual: bool = False) -> Post:
    post = db.get(Post, post_id)
    if post is None:
        raise AppError("Post not found.")
    if post.instagram_media_id or post.status == S.PUBLISHED:
        raise DuplicatePublishError("This post has already been published. It will not be posted again.")
    if post.status == S.PUBLISHING:
        raise DuplicatePublishError("This post is being published right now.")
    allowed = [S.APPROVED, S.SCHEDULED] if manual else [S.SCHEDULED]
    if post.status not in allowed:
        raise InvalidTransitionError(f"Only approved or scheduled posts can be published (current status: {post.status}).")
    if not publishing_enabled(db):
        raise AppError("Publishing is paused (Settings → Publishing). Enable it to publish.")

    previous_status = post.status
    post_id = post.id
    if not _claim(db, post_id, allowed):
        db.refresh(post)
        raise DuplicatePublishError(f"Post could not be claimed for publishing (status now {post.status}). No duplicate was sent.")
    db.refresh(post)
    record_event(db, post, "publish_started", "Manual publish" if manual else "Scheduled publish", from_status=previous_status, to_status=S.PUBLISHING, actor_id=actor_id)
    if post.scheduled_at is None:
        post.scheduled_at = datetime.now(UTC)
    db.commit()

    attempt = PublishAttempt(post_id=post.id, attempt_no=post.publish_attempts)
    db.add(attempt)
    db.commit()

    try:
        _do_publish(db, post, attempt)
    except InstagramAPIError as err:
        _handle_failure(db, post, attempt, err)
    except SQLAlchemyError:
        # e.g. Instagram accepted the post but saving the result failed. The container id
        # was committed earlier, so the retry will see it is PUBLISHED and not post again.
        db.rollback()
        logger.exception("Database error while publishing post %s", post_id)
        _handle_failure(db, post, attempt, InstagramAPIError("Database error while saving the publish result; will verify with Instagram and retry.", transient=True))
    except Exception as exc:  # unexpected bug - never leave the post locked
        db.rollback()
        logger.exception("Unexpected error while publishing post %s", post_id)
        _handle_failure(db, post, attempt, InstagramAPIError(f"Unexpected error: {type(exc).__name__}", transient=True))
    db.commit()
    db.refresh(post)
    return post


def _do_publish(db: Session, post: Post, attempt: PublishAttempt) -> None:
    token, ig_user_id, acc = account_service.get_credentials(db)
    client = account_service.get_client()
    attempt.mock = client.is_mock

    caption = compose_caption(post.caption, post.hashtags or [])
    problems = validate_caption_with_hashtags(post.caption, post.hashtags or [])
    if problems:
        raise InstagramAPIError("Caption is not valid for Instagram: " + " ".join(problems))
    if not post.image_url:
        raise InstagramAPIError("Post has no image.")
    if not client.is_mock and ("://localhost" in post.image_url or "://127.0.0.1" in post.image_url):
        raise InstagramAPIError(
            "The image URL points to localhost, which Instagram cannot download. Set PUBLIC_BASE_URL to a public https address or use S3 storage (see README → Instagram setup)."
        )
    try:
        image_bytes = get_storage().read(post.image_url)
    except Exception:
        image_bytes = None  # stored elsewhere (external URL) - Instagram will validate it
    if image_bytes is not None:
        img_problems = check_instagram_image(image_bytes)
        if img_problems:
            raise InstagramAPIError("Image is not valid for Instagram: " + " ".join(img_problems))

    # --- Step 0: idempotency check on an existing container -------------------
    container_id = post.instagram_container_id
    if container_id:
        status = _container_status(client, token, container_id)
        if status == "PUBLISHED":
            _recover_published(db, post, attempt, client, token, ig_user_id, caption)
            return
        if status in ("EXPIRED", "ERROR", None):
            record_event(db, post, "container_discarded", f"Previous container {container_id} status {status}; creating a new one.")
            container_id = None
            post.instagram_container_id = None
            db.commit()

    # --- Step 0b: publishing quota -------------------------------------------
    try:
        limit = client.get_publishing_limit(token, ig_user_id)
        usage = int(limit.get("quota_usage") or 0)
        total = int((limit.get("config") or {}).get("quota_total") or 100)
        if usage >= total:
            raise InstagramAPIError(f"Instagram publishing limit reached ({usage}/{total} in 24h). Will retry later.", transient=True)
    except InstagramAPIError as err:
        if err.transient and "publishing limit" in err.message:
            raise
        if err.token_problem:
            raise
        logger.warning("Could not read publishing limit; continuing")

    # --- Step 1: create container (committed before publishing) ---------------
    if not container_id:
        container_id = client.create_image_container(token, ig_user_id, post.image_url, caption)
        post.instagram_container_id = container_id
        attempt.container_id = container_id
        record_event(db, post, "container_created", f"Media container {container_id} created.")
        db.commit()
    else:
        attempt.container_id = container_id

    # --- Step 2: wait until the container is FINISHED -------------------------
    status = None
    for i in range(max(settings.container_status_poll_attempts, 1)):
        status = _container_status(client, token, container_id, raise_errors=True)
        if status in ("FINISHED", "PUBLISHED", "ERROR", "EXPIRED"):
            break
        if i < settings.container_status_poll_attempts - 1:
            time.sleep(settings.container_status_poll_interval_seconds)
    if status == "PUBLISHED":
        _recover_published(db, post, attempt, client, token, ig_user_id, caption)
        return
    if status == "ERROR":
        post.instagram_container_id = None
        raise InstagramAPIError("Instagram could not process the image (container status ERROR). Check the image and try again.")
    if status == "EXPIRED":
        post.instagram_container_id = None
        raise InstagramAPIError("Media container expired; a new one will be created.", transient=True)
    if status != "FINISHED":
        raise InstagramAPIError("Instagram is still processing the media; will retry.", transient=True)

    # --- Step 3: publish --------------------------------------------------------
    try:
        media_id = client.publish_container(token, ig_user_id, container_id)
    except InstagramAPIError as err:
        if err.ambiguous:
            # The request may have succeeded. Verify before any retry.
            if _container_status(client, token, container_id) == "PUBLISHED":
                _recover_published(db, post, attempt, client, token, ig_user_id, caption)
                return
        raise
    _mark_published(db, post, attempt, client, token, media_id)
    account_service.record_success(acc)


def _container_status(client, token: str, container_id: str, raise_errors: bool = False) -> str | None:
    try:
        return client.get_container_status(token, container_id).get("status_code")
    except InstagramAPIError:
        if raise_errors:
            raise
        return None


def _recover_published(db: Session, post: Post, attempt: PublishAttempt, client, token: str, ig_user_id: str, caption: str) -> None:
    """The container was already published (e.g. a previous attempt's response was lost)."""
    media_id = None
    try:
        for item in client.list_recent_media(token, ig_user_id, limit=25):
            if (item.get("caption") or "").strip() == caption.strip():
                media_id = str(item["id"])
                break
    except InstagramAPIError:
        pass
    record_event(db, post, "publish_recovered", "Instagram reports this post was already published; recorded without re-posting.")
    _mark_published(db, post, attempt, client, token, media_id)


def _mark_published(db: Session, post: Post, attempt: PublishAttempt, client, token: str, media_id: str | None) -> None:
    now = datetime.now(UTC)
    post.instagram_media_id = media_id
    post.published_at = now
    post.published_via_mock = client.is_mock
    post.next_retry_at = None
    post.last_error = ""
    attempt.success = True
    attempt.media_id = media_id
    attempt.finished_at = now
    prev = post.status
    post.status = S.PUBLISHED
    msg = "SIMULATED publish (mock mode) - nothing was posted to Instagram." if client.is_mock else f"Published to Instagram (media id {media_id})."
    record_event(db, post, "published", msg, from_status=prev, to_status=S.PUBLISHED, data={"media_id": media_id, "mock": client.is_mock})
    db.commit()
    if media_id:
        try:
            media = client.get_media(token, media_id)
            post.instagram_permalink = media.get("permalink") or ""
            db.commit()
        except InstagramAPIError:
            logger.info("Could not fetch permalink for %s (will retry in metrics refresh)", media_id)


def _handle_failure(db: Session, post: Post, attempt: PublishAttempt, err: InstagramAPIError) -> None:
    try:
        db.flush()  # keep intentional changes such as a cleared expired container id
    except Exception:
        db.rollback()
        db.refresh(post)
    now = datetime.now(UTC)
    attempt.finished_at = now
    attempt.success = False
    attempt.transient = err.transient
    attempt.error_code = err.short_code
    attempt.error_message = err.message
    post.last_error = err.message
    delays = settings.retry_delays
    acc = account_service.get_account_row(db)
    account_service.record_error(db, acc, err, post_id=post.id)
    if err.transient and post.publish_attempts <= len(delays):
        delay = delays[post.publish_attempts - 1]
        post.next_retry_at = now + timedelta(seconds=delay)
        post.status = S.SCHEDULED
        record_event(
            db,
            post,
            "publish_retry_scheduled",
            f"{err.message} Retrying in {delay // 60 or 1} minute(s) (attempt {post.publish_attempts} of {len(delays) + 1}).",
            from_status=S.PUBLISHING,
            to_status=S.SCHEDULED,
        )
    else:
        post.status = S.FAILED
        post.next_retry_at = None
        reason = "after all retries" if err.transient else "(not retryable)"
        record_event(db, post, "publish_failed", f"Publishing failed {reason}: {err.message}", from_status=S.PUBLISHING, to_status=S.FAILED)
        if isinstance(err, InstagramNotConnected):
            log_integration(db, "scheduler", f"Post {post.id} could not be published: Instagram not connected.", post_id=post.id)


def due_post_ids(db: Session, now: datetime | None = None) -> list[int]:
    now = now or datetime.now(UTC)
    stmt = (
        select(Post.id).where(Post.status == S.SCHEDULED, Post.scheduled_at <= now).where((Post.next_retry_at.is_(None)) | (Post.next_retry_at <= now)).order_by(Post.scheduled_at)
    )
    return list(db.scalars(stmt))


def recover_stale_publishing(db: Session, now: datetime | None = None) -> int:
    """Return posts stuck in PUBLISHING (crashed worker) to the queue. The container check makes the retry safe."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(minutes=settings.stale_publishing_minutes)
    stale = db.scalars(select(Post).where(Post.status == S.PUBLISHING, Post.publishing_started_at < cutoff)).all()
    for post in stale:
        post.status = S.SCHEDULED
        post.next_retry_at = now
        record_event(
            db,
            post,
            "recovered_stale_lock",
            "Publishing lock expired (worker restart?). Will verify with Instagram before retrying.",
            from_status=S.PUBLISHING,
            to_status=S.SCHEDULED,
        )
    db.commit()
    return len(stale)


def publish_due_posts(db: Session) -> dict[str, int]:
    recovered = recover_stale_publishing(db)
    if not publishing_enabled(db):
        return {"published": 0, "failed": 0, "retrying": 0, "recovered": recovered, "paused": 1}
    counts = {"published": 0, "failed": 0, "retrying": 0, "recovered": recovered}
    for pid in due_post_ids(db):
        try:
            post = publish_post(db, pid)
        except (DuplicatePublishError, InvalidTransitionError):
            continue  # another worker got it
        if post.status == S.PUBLISHED:
            counts["published"] += 1
        elif post.status == S.FAILED:
            counts["failed"] += 1
        else:
            counts["retrying"] += 1
    return counts


def refresh_metrics(db: Session, days: int = 30) -> int:
    """Update likes/comments/permalink for recent real posts (basic analytics)."""
    try:
        token, _, _ = account_service.get_credentials(db)
    except InstagramNotConnected:
        return 0
    client = account_service.get_client()
    since = datetime.now(UTC) - timedelta(days=days)
    posts = db.scalars(select(Post).where(Post.status == S.PUBLISHED, Post.instagram_media_id.is_not(None), Post.published_at >= since)).all()
    n = 0
    for post in posts:
        try:
            media = client.get_media(token, post.instagram_media_id)
        except InstagramAPIError as err:
            if err.token_problem:
                break
            continue
        post.like_count = media.get("like_count")
        post.comments_count = media.get("comments_count")
        post.instagram_permalink = media.get("permalink") or post.instagram_permalink
        post.metrics_updated_at = datetime.now(UTC)
        n += 1
    db.commit()
    return n
