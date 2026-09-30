from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import approver, editor, rate_limit, viewer
from app.core.errors import InvalidTransitionError, ValidationFailed
from app.database.session import get_db
from app.models import ContentCategory, Post, PostStatus, Template, User
from app.schemas.api import (
    ApproveIn,
    PostCreate,
    PostDetailOut,
    PostListOut,
    PostOut,
    PostUpdate,
    RegenerateIn,
    RejectIn,
    ScheduleIn,
)
from app.services.channels import get_channel
from app.services.content import generation, workflow
from app.services.content.audit import record_event
from app.services.scheduling.planner import auto_schedule_on_approval

router = APIRouter(prefix="/posts", tags=["posts"])
S = PostStatus


def _get(db: Session, post_id: int) -> Post:
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(404, "Post not found.")
    return post


def _detail(post: Post, warnings: list[str] | None = None) -> PostDetailOut:
    base = PostOut.from_post(post).model_dump()
    return PostDetailOut(**base, events=[e for e in post.events], warnings=warnings or [])


def _check_refs(db: Session, category_id: int | None, template_id: int | None) -> None:
    if category_id is not None and db.get(ContentCategory, category_id) is None:
        raise ValidationFailed("Unknown category.")
    if template_id is not None and db.get(Template, template_id) is None:
        raise ValidationFailed("Unknown template.")


@router.get("", response_model=PostListOut)
def list_posts(
    status: list[str] | None = Query(default=None),
    category_id: int | None = None,
    q: str | None = Query(default=None, max_length=200),
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
    _: User = Depends(viewer),
    db: Session = Depends(get_db),
):
    stmt = select(Post)
    if status:
        stmt = stmt.where(Post.status.in_(status))
    if category_id:
        stmt = stmt.where(Post.category_id == category_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Post.topic.ilike(like), Post.headline.ilike(like), Post.caption.ilike(like)))
    when = func.coalesce(Post.published_at, Post.scheduled_at, Post.desired_publish_at)
    if start:
        stmt = stmt.where(when >= start)
    if end:
        stmt = stmt.where(when <= end)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    posts = db.scalars(stmt.order_by(Post.id.desc()).limit(limit).offset(offset)).unique().all()
    return PostListOut(items=[PostOut.from_post(p) for p in posts], total=total)


@router.get("/calendar", response_model=list[PostOut])
def calendar(start: datetime, end: datetime, _: User = Depends(viewer), db: Session = Depends(get_db)):
    """Posts positioned by their publish/scheduled/desired date within [start, end]."""
    when = func.coalesce(Post.published_at, Post.scheduled_at, Post.desired_publish_at)
    posts = db.scalars(select(Post).where(when >= start, when <= end).order_by(when)).unique().all()
    return [PostOut.from_post(p) for p in posts]


@router.post("", response_model=PostDetailOut, status_code=201)
def create_post(body: PostCreate, user: User = Depends(editor), db: Session = Depends(get_db), __=Depends(rate_limit("generate", "generation_rate_limit_per_minute"))):
    _check_refs(db, body.category_id, body.template_id)
    data = body.model_dump(exclude={"generate"})
    if data["template_id"] is None and data["category_id"]:
        cat = db.get(ContentCategory, data["category_id"])
        data["template_id"] = cat.default_template_id if cat else None
    post = Post(**data, created_by_id=user.id, status=S.DRAFT)
    db.add(post)
    db.flush()
    record_event(db, post, "created", "Post created", to_status=S.DRAFT, actor_id=user.id)
    db.commit()
    warnings: list[str] = []
    if body.generate:
        post, warnings = generation.generate_full(db, post, actor_id=user.id)
    return _detail(post, warnings)


@router.get("/{post_id}", response_model=PostDetailOut)
def get_post(post_id: int, _: User = Depends(viewer), db: Session = Depends(get_db)):
    return _detail(_get(db, post_id))


@router.patch("/{post_id}", response_model=PostDetailOut)
def update_post(post_id: int, body: PostUpdate, user: User = Depends(editor), db: Session = Depends(get_db)):
    post = _get(db, post_id)
    workflow.ensure_editable(post)
    data = body.model_dump(exclude_unset=True, exclude={"recompose_image"})
    _check_refs(db, data.get("category_id"), data.get("template_id"))
    if "desired_publish_at" in data and data["desired_publish_at"] is not None and data["desired_publish_at"].tzinfo is None:
        raise ValidationFailed("desired_publish_at must include a timezone offset.")
    changed: set[str] = set()
    for k, v in data.items():
        if getattr(post, k) != v:
            setattr(post, k, v)
            changed.add(k)
    if not changed:
        return _detail(post)
    record_event(db, post, "edited", f"Edited: {', '.join(sorted(changed))}", actor_id=user.id)
    visual = {"headline", "subtitle", "cta", "template_id", "category_id"}
    if body.recompose_image and (changed & visual) and post.image_url and (post.raw_image_url or post.template_id):
        generation.compose_image(db, post)
        changed.add("image_url")
    if changed & (workflow.CONTENT_FIELDS | {"topic", "important_info", "reference_material"}):
        post.review_flags = generation.compute_flags(db, post)
        post.flags_acknowledged = False
    workflow.after_content_edit(db, post, changed, user.id)
    db.commit()
    return _detail(post)


@router.delete("/{post_id}", status_code=204)
def delete_post(post_id: int, _: User = Depends(approver), db: Session = Depends(get_db)):
    post = _get(db, post_id)
    if post.status in (S.PUBLISHED, S.PUBLISHING):
        raise InvalidTransitionError("Published posts cannot be deleted here (they are part of the record).")
    db.delete(post)
    db.commit()


@router.post("/{post_id}/generate", response_model=PostDetailOut)
def generate(
    post_id: int,
    body: RegenerateIn | None = None,
    user: User = Depends(editor),
    db: Session = Depends(get_db),
    __=Depends(rate_limit("generate", "generation_rate_limit_per_minute")),
):
    post = _get(db, post_id)
    workflow.ensure_editable(post)
    post, warnings = generation.generate_full(db, post, actor_id=user.id, feedback=(body.feedback if body else None) or None)
    return _detail(post, warnings)


@router.post("/{post_id}/regenerate-text", response_model=PostDetailOut)
def regenerate_text(
    post_id: int,
    body: RegenerateIn | None = None,
    user: User = Depends(editor),
    db: Session = Depends(get_db),
    __=Depends(rate_limit("generate", "generation_rate_limit_per_minute")),
):
    post = _get(db, post_id)
    workflow.ensure_editable(post)
    generation.generate_text(db, post, actor_id=user.id, feedback=(body.feedback if body else None) or None)
    if post.image_url:
        generation.compose_image(db, post)  # keep the design in sync with the new headline
    if post.status == S.AI_GENERATED:
        workflow.transition(db, post, S.NEEDS_REVIEW, actor_id=user.id, message="Ready for human review")
    db.commit()
    return _detail(post)


@router.post("/{post_id}/regenerate-image", response_model=PostDetailOut)
def regenerate_image(post_id: int, user: User = Depends(editor), db: Session = Depends(get_db), __=Depends(rate_limit("generate", "generation_rate_limit_per_minute"))):
    post = _get(db, post_id)
    workflow.ensure_editable(post)
    generation.generate_image(db, post, actor_id=user.id)
    if post.status == S.AI_GENERATED:
        workflow.transition(db, post, S.NEEDS_REVIEW, actor_id=user.id)
    db.commit()
    return _detail(post)


@router.post("/{post_id}/image", response_model=PostDetailOut)
async def upload_image(post_id: int, file: UploadFile = File(...), apply_template: bool = Form(True), user: User = Depends(editor), db: Session = Depends(get_db)):
    post = _get(db, post_id)
    workflow.ensure_editable(post)
    data = await file.read()
    if not data:
        raise ValidationFailed("Empty file.")
    generation.replace_image(db, post, data, apply_template=apply_template, actor_id=user.id)
    db.commit()
    return _detail(post)


@router.post("/{post_id}/submit", response_model=PostDetailOut)
def submit_for_review(post_id: int, user: User = Depends(editor), db: Session = Depends(get_db)):
    """Send a manually written draft (or an AI_GENERATED post) to review."""
    post = _get(db, post_id)
    if post.status not in (S.DRAFT, S.AI_GENERATED, S.REJECTED):
        raise InvalidTransitionError(f"Cannot submit a post in status {post.status}.")
    if not post.caption.strip():
        raise ValidationFailed("Write or generate a caption before submitting for review.")
    post.review_flags = generation.compute_flags(db, post)
    workflow.transition(db, post, S.NEEDS_REVIEW, actor_id=user.id, message="Submitted for review")
    db.commit()
    return _detail(post)


@router.post("/{post_id}/approve", response_model=PostDetailOut)
def approve(post_id: int, body: ApproveIn, user: User = Depends(approver), db: Session = Depends(get_db)):
    post = _get(db, post_id)
    when = body.schedule_at
    if when is None and body.use_desired_time:
        when = auto_schedule_on_approval(db, post)
        if when is None and post.desired_publish_at and post.desired_publish_at > datetime.now(UTC):
            when = post.desired_publish_at
    workflow.approve(db, post, actor_id=user.id, acknowledge_flags=body.acknowledge_flags, schedule_at=when)
    db.commit()
    return _detail(post)


@router.post("/{post_id}/reject", response_model=PostDetailOut)
def reject(post_id: int, body: RejectIn, user: User = Depends(approver), db: Session = Depends(get_db)):
    post = _get(db, post_id)
    workflow.reject(db, post, actor_id=user.id, reason=body.reason)
    db.commit()
    return _detail(post)


@router.post("/{post_id}/schedule", response_model=PostDetailOut)
def schedule(post_id: int, body: ScheduleIn, user: User = Depends(approver), db: Session = Depends(get_db)):
    post = _get(db, post_id)
    workflow.schedule(db, post, body.scheduled_at, actor_id=user.id)
    db.commit()
    return _detail(post)


@router.post("/{post_id}/unschedule", response_model=PostDetailOut)
def unschedule(post_id: int, user: User = Depends(approver), db: Session = Depends(get_db)):
    post = _get(db, post_id)
    workflow.unschedule(db, post, actor_id=user.id)
    db.commit()
    return _detail(post)


@router.post("/{post_id}/publish", response_model=PostDetailOut)
def publish_now(post_id: int, user: User = Depends(approver), db: Session = Depends(get_db)):
    """Publish an approved post immediately (still protected against duplicates)."""
    post = _get(db, post_id)
    post = get_channel(post.channel).publish(db, post.id, actor_id=user.id, manual=True)
    warnings = []
    if post.status == S.SCHEDULED and post.next_retry_at:
        warnings.append(f"Publishing hit a temporary error and will retry automatically: {post.last_error}")
    elif post.status == S.FAILED:
        warnings.append(f"Publishing failed: {post.last_error}")
    elif post.published_via_mock:
        warnings.append("MOCK MODE: this was a simulated publish. Nothing was posted to Instagram. Real publishing still requires Meta configuration and credentials.")
    return _detail(post, warnings)
