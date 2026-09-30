from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ContentCategory, Post, PostStatus
from app.services.content import workflow
from app.services.content.generation import generate_full


def category(db: Session, key: str = "NORMAL") -> ContentCategory:
    return db.scalars(select(ContentCategory).where(ContentCategory.key == key)).one()


def make_generated_post(db: Session, *, key: str = "NORMAL", topic: str = "Study habits that work", cta: str = "Follow for more tips", important_info: str = "") -> Post:
    cat = category(db, key)
    post = Post(topic=topic, cta=cta, category_id=cat.id, template_id=cat.default_template_id, important_info=important_info, target_audience="Students")
    db.add(post)
    db.commit()
    post, _ = generate_full(db, post, actor_id=None)
    return post


def make_scheduled_post(db: Session, *, when: datetime | None = None, actor_id: int = 1) -> Post:
    post = make_generated_post(db)
    workflow.approve(db, post, actor_id=actor_id, acknowledge_flags=True)
    workflow.schedule(db, post, when or datetime.now(UTC) + timedelta(seconds=1), actor_id=actor_id)
    db.commit()
    if when is None:
        post.scheduled_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert post.status == PostStatus.SCHEDULED
    return post
