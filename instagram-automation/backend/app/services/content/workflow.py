"""Post status state machine (human-in-the-loop approval workflow).

DRAFT -> AI_GENERATED -> NEEDS_REVIEW -> APPROVED -> SCHEDULED -> (PUBLISHING) -> PUBLISHED
                                   \\-> REJECTED                       \\-> FAILED

Only APPROVED/SCHEDULED posts can ever reach Instagram. Editing the content of
an approved or scheduled post sends it back to NEEDS_REVIEW, so nothing a human
has not seen can be published.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.errors import InvalidTransitionError, ValidationFailed
from app.models import Post, PostStatus
from app.services.ai.schemas import validate_caption_with_hashtags
from app.services.content.audit import record_event

S = PostStatus

TRANSITIONS: dict[str, set[str]] = {
    S.DRAFT: {S.AI_GENERATED, S.NEEDS_REVIEW, S.REJECTED},
    S.AI_GENERATED: {S.NEEDS_REVIEW, S.REJECTED},
    S.NEEDS_REVIEW: {S.NEEDS_REVIEW, S.AI_GENERATED, S.APPROVED, S.REJECTED},
    S.APPROVED: {S.SCHEDULED, S.NEEDS_REVIEW, S.PUBLISHING, S.REJECTED, S.AI_GENERATED},
    S.SCHEDULED: {S.PUBLISHING, S.APPROVED, S.NEEDS_REVIEW, S.REJECTED, S.AI_GENERATED},
    S.PUBLISHING: {S.PUBLISHED, S.SCHEDULED, S.FAILED},
    S.FAILED: {S.SCHEDULED, S.NEEDS_REVIEW, S.APPROVED, S.AI_GENERATED, S.REJECTED},
    S.REJECTED: {S.NEEDS_REVIEW, S.DRAFT, S.AI_GENERATED},
    S.PUBLISHED: set(),
}

EDITABLE = {S.DRAFT, S.AI_GENERATED, S.NEEDS_REVIEW, S.APPROVED, S.SCHEDULED, S.FAILED, S.REJECTED}
CONTENT_FIELDS = {"headline", "subtitle", "caption", "hashtags", "image_url", "cta", "alternative_caption"}


def transition(db: Session, post: Post, to: str, *, actor_id: int | None = None, message: str = "", event_type: str = "status_change", data: dict | None = None) -> None:
    current = post.status
    if to not in TRANSITIONS.get(current, set()):
        raise InvalidTransitionError(f"A post cannot move from {current} to {to}.")
    post.status = to
    record_event(db, post, event_type, message, from_status=current, to_status=to, actor_id=actor_id, data=data)


def ensure_editable(post: Post) -> None:
    if post.status not in EDITABLE:
        raise InvalidTransitionError(f"Posts in status {post.status} cannot be edited.")


def after_content_edit(db: Session, post: Post, changed: set[str], actor_id: int | None) -> None:
    """Edits to approved/scheduled content require re-approval."""
    if not (changed & CONTENT_FIELDS):
        return
    if post.status in (S.APPROVED, S.SCHEDULED, S.FAILED):
        post.approved_at = None
        post.approved_by_id = None
        post.scheduled_at = None
        post.next_retry_at = None
        transition(db, post, S.NEEDS_REVIEW, actor_id=actor_id, message="Content edited after approval - re-approval required.")
    elif post.status == S.REJECTED:
        transition(db, post, S.NEEDS_REVIEW, actor_id=actor_id, message="Rejected post edited - back to review.")


def approve(db: Session, post: Post, *, actor_id: int, acknowledge_flags: bool = False, schedule_at: datetime | None = None) -> None:
    if post.status not in (S.NEEDS_REVIEW, S.AI_GENERATED):
        raise InvalidTransitionError(f"Only posts awaiting review can be approved (current status: {post.status}).")
    problems = []
    if not post.headline.strip() and not post.caption.strip():
        problems.append("The post has no headline or caption.")
    if not post.caption.strip():
        problems.append("The caption is empty.")
    if not post.image_url:
        problems.append("The post has no image. Generate or upload one first.")
    problems += validate_caption_with_hashtags(post.caption, post.hashtags or [])
    if problems:
        raise ValidationFailed("Cannot approve: " + " ".join(problems), details={"problems": problems})
    if (post.review_flags or post.missing_information) and not acknowledge_flags:
        raise ValidationFailed(
            "This post has review flags (possible unverified facts or missing information). Check them and confirm you verified the content before approving.",
            details={"review_flags": post.review_flags, "missing_information": post.missing_information},
        )
    if post.status == S.AI_GENERATED:
        transition(db, post, S.NEEDS_REVIEW, actor_id=actor_id)
    post.flags_acknowledged = bool(post.review_flags or post.missing_information)
    post.approved_by_id = actor_id
    post.approved_at = datetime.now(UTC)
    post.rejected_reason = ""
    transition(db, post, S.APPROVED, actor_id=actor_id, message="Approved" + (" (flags acknowledged)" if post.flags_acknowledged else ""))
    if schedule_at is not None:
        schedule(db, post, schedule_at, actor_id=actor_id)


def reject(db: Session, post: Post, *, actor_id: int, reason: str = "") -> None:
    if post.status in (S.PUBLISHED, S.PUBLISHING):
        raise InvalidTransitionError("Published or publishing posts cannot be rejected.")
    post.rejected_reason = reason
    post.scheduled_at = None
    post.next_retry_at = None
    transition(db, post, S.REJECTED, actor_id=actor_id, message=reason or "Rejected")


def schedule(db: Session, post: Post, when: datetime, *, actor_id: int | None) -> None:
    if when.tzinfo is None:
        raise ValidationFailed("Scheduled time must include a timezone.")
    if post.status not in (S.APPROVED, S.SCHEDULED, S.FAILED):
        raise InvalidTransitionError("Only approved posts can be scheduled. Approve the post first.")
    if post.status == S.FAILED and not post.approved_at:
        raise InvalidTransitionError("This post must be re-approved before scheduling.")
    now = datetime.now(UTC)
    if when < now - timedelta(minutes=1):
        raise ValidationFailed("Scheduled time is in the past.")
    post.scheduled_at = when.astimezone(UTC)
    post.next_retry_at = None
    post.publish_attempts = 0
    post.last_error = ""
    if post.status == S.SCHEDULED:
        record_event(db, post, "rescheduled", f"Rescheduled for {post.scheduled_at.isoformat()}", actor_id=actor_id)
    else:
        transition(db, post, S.SCHEDULED, actor_id=actor_id, message=f"Scheduled for {post.scheduled_at.isoformat()}")


def unschedule(db: Session, post: Post, *, actor_id: int) -> None:
    if post.status != S.SCHEDULED:
        raise InvalidTransitionError("Post is not scheduled.")
    post.scheduled_at = None
    post.next_retry_at = None
    transition(db, post, S.APPROVED, actor_id=actor_id, message="Unscheduled")
