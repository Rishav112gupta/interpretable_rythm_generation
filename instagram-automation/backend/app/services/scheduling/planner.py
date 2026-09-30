"""Recurring schedule planner.

Two independent clocks, as required:
  A. Content generation: `generation_lead_hours` before each slot, a post is
     generated with AI and placed in NEEDS_REVIEW for a human.
  B. Publishing: at the slot time, the post is published only if it was
     approved (and therefore SCHEDULED). Unapproved posts are never published;
     a warning is logged instead.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ExternalServiceError, ValidationFailed
from app.models import ContentCategory, Post, PostStatus, RecurringSchedule
from app.services.content.audit import log_integration, record_event
from app.services.scheduling.recurrence import RecurrenceRule, occurrence_index, occurrences_between

logger = logging.getLogger(__name__)
S = PostStatus
PLANNING_HORIZON_DAYS = 14


def rule_for(schedule: RecurringSchedule) -> RecurrenceRule:
    return RecurrenceRule(
        start_date=schedule.start_date,
        interval_days=schedule.interval_days,
        post_time=schedule.post_time,
        tz=schedule.timezone,
        mode=schedule.mode,
        end_date=schedule.end_date,
    )


def _pick_topic(schedule: RecurringSchedule, idx: int) -> str:
    pool = [t for t in (schedule.topic_pool or []) if t.strip()]
    if pool:
        return pool[idx % len(pool)]
    return ""


def _pick_category(db: Session, schedule: RecurringSchedule, idx: int) -> ContentCategory | None:
    rotation = [k for k in (schedule.category_rotation or []) if k]
    if rotation:
        key = rotation[idx % len(rotation)]
        cat = db.scalars(select(ContentCategory).where(ContentCategory.key == key)).first()
        if cat:
            return cat
    return schedule.category


def plan_schedule(db: Session, schedule: RecurringSchedule, now: datetime | None = None) -> list[Post]:
    """Create placeholder DRAFT posts for upcoming slots (idempotent)."""
    now = now or datetime.now(UTC)
    horizon = now + timedelta(days=PLANNING_HORIZON_DAYS, hours=schedule.generation_lead_hours)
    rule = rule_for(schedule)
    created: list[Post] = []
    for slot in occurrences_between(rule, now, horizon):
        exists = db.scalars(select(Post.id).where(Post.schedule_id == schedule.id, Post.desired_publish_at == slot)).first()
        if exists:
            continue
        idx = occurrence_index(rule, slot)
        category = _pick_category(db, schedule, idx)
        topic = _pick_topic(schedule, idx)
        post = Post(
            schedule_id=schedule.id,
            desired_publish_at=slot,
            category_id=category.id if category else None,
            template_id=schedule.template_id or (category.default_template_id if category else None),
            topic=topic,
            target_audience=schedule.target_audience,
            tone=schedule.tone,
            objective=schedule.objective,
            cta=schedule.cta,
            language=schedule.language,
            status=S.DRAFT,
            created_by_id=schedule.created_by_id,
        )
        try:
            with db.begin_nested():
                db.add(post)
                db.flush()
        except IntegrityError:  # created concurrently by another worker
            continue
        record_event(db, post, "created", f"Planned by schedule '{schedule.name}' for slot {slot.isoformat()}", to_status=S.DRAFT)
        created.append(post)
    db.commit()
    return created


def plan_all(db: Session, now: datetime | None = None) -> int:
    total = 0
    for schedule in db.scalars(select(RecurringSchedule).where(RecurringSchedule.is_active.is_(True))).all():
        try:
            total += len(plan_schedule(db, schedule, now))
        except ValueError as exc:
            log_integration(db, "scheduler", f"Schedule '{schedule.name}' is invalid: {exc}")
            db.commit()
    return total


def generate_due_content(db: Session, now: datetime | None = None, *, limit: int = 5) -> dict[str, int]:
    """Clock A: generate content for planned posts whose generation time has arrived."""
    from app.services.content import ideas as ideas_service
    from app.services.content.generation import generate_full

    now = now or datetime.now(UTC)
    stmt = (
        select(Post)
        .join(RecurringSchedule, Post.schedule_id == RecurringSchedule.id)
        .where(Post.status == S.DRAFT, Post.generated_at.is_(None), RecurringSchedule.auto_generate.is_(True), RecurringSchedule.is_active.is_(True))
        .order_by(Post.desired_publish_at)
    )
    generated = failed = 0
    for post in db.scalars(stmt).all():
        schedule = db.get(RecurringSchedule, post.schedule_id)
        if post.desired_publish_at is None or post.desired_publish_at - timedelta(hours=schedule.generation_lead_hours) > now:
            continue
        if generated + failed >= limit:
            break
        try:
            if not post.topic:
                idea = ideas_service.generate_ideas(db, count=1, target_audience=post.target_audience)[0]
                post.topic = idea.title
                post.objective = post.objective or idea.description
                post.idea_id = idea.id
            generate_full(db, post)
            generated += 1
        except (ExternalServiceError, ValidationFailed) as err:
            failed += 1
            log_integration(db, "scheduler", f"Auto-generation for planned post {post.id} failed: {err.message}", post_id=post.id)
            db.commit()
    return {"generated": generated, "failed": failed}


def warn_missed_slots(db: Session, now: datetime | None = None) -> int:
    """Publishing clock: a slot has arrived but nobody approved the post -> it is NOT published; tell the admins."""
    now = now or datetime.now(UTC)
    stmt = select(Post).where(
        Post.schedule_id.is_not(None),
        Post.desired_publish_at <= now,
        Post.status.in_([S.DRAFT, S.AI_GENERATED, S.NEEDS_REVIEW]),
    )
    n = 0
    for post in db.scalars(stmt).all():
        if any(e.event_type == "missed_slot" for e in post.events):
            continue
        record_event(db, post, "missed_slot", "Publishing slot passed without approval - the post was NOT published. Approve and schedule it manually if still relevant.")
        log_integration(db, "scheduler", f"Post {post.id} missed its slot ({post.desired_publish_at.isoformat()}) because it was not approved.", level="warning", post_id=post.id)
        n += 1
    db.commit()
    return n


def auto_schedule_on_approval(db: Session, post: Post) -> datetime | None:
    """If a recurring-schedule post is approved before its slot, schedule it for that slot."""
    if not post.schedule_id or not post.desired_publish_at:
        return None
    schedule = db.get(RecurringSchedule, post.schedule_id)
    if schedule and schedule.auto_schedule_on_approval and post.desired_publish_at > datetime.now(UTC):
        return post.desired_publish_at
    return None


def validate_schedule_input(mode: str, interval_days: int, tz: str) -> None:
    try:
        RecurrenceRule(start_date=datetime.now().date(), interval_days=interval_days, post_time=datetime.now().time(), tz=tz, mode=mode)
    except ValueError as exc:
        raise ValidationFailed(str(exc)) from exc
