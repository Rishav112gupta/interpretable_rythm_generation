"""'Generate Content Ideas' and idea -> post conversion."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import LLMError
from app.models import ContentCategory, ContentIdea, IdeaStatus, Post, PostStatus
from app.services.ai import prompts
from app.services.ai.factory import get_llm_provider
from app.services.ai.schemas import IDEAS_JSON_SCHEMA, IdeasResponse, parse_model
from app.services.content.audit import log_integration, record_event
from app.services.content.generation import brand_dict, get_brand, latest_insights


def generate_ideas(db: Session, *, count: int = 7, theme: str = "", target_audience: str = "") -> list[ContentIdea]:
    count = max(1, min(count, 20))
    categories = db.scalars(select(ContentCategory).where(ContentCategory.is_active.is_(True))).all()
    keys = [c.key for c in categories]
    recent = [t for t in db.scalars(select(Post.topic).order_by(Post.id.desc()).limit(40)) if t]
    ctx = {
        "brand": brand_dict(get_brand(db)),
        "category_keys": keys,
        "theme": theme,
        "target_audience": target_audience,
        "recent_topics": recent,
        "insights": latest_insights(db),
        "count": count,
        "variant": db.query(ContentIdea).count(),
    }
    provider = get_llm_provider()
    try:
        result = provider.complete_json(task="ideas", system=prompts.ideas_system_prompt(), user=prompts.ideas_user_prompt(ctx), schema=IDEAS_JSON_SCHEMA, context=ctx)
        parsed: IdeasResponse = parse_model(IdeasResponse, result.data)
    except LLMError as err:
        log_integration(db, "llm", f"Idea generation failed: {err.message}")
        db.commit()
        raise
    ideas = []
    for item in parsed.ideas[:count]:
        cat = item.category_key.upper() if item.category_key.upper() in keys else ("RANDOM" if "RANDOM" in keys else (keys[0] if keys else "RANDOM"))
        idea = ContentIdea(
            title=item.title,
            description=item.description,
            category_key=cat,
            suggested_format=item.suggested_format,
            target_audience=item.target_audience or target_audience,
            source="ai",
        )
        db.add(idea)
        ideas.append(idea)
    db.commit()
    return ideas


def idea_to_post(db: Session, idea: ContentIdea, *, user_id: int | None) -> Post:
    category = db.scalars(select(ContentCategory).where(ContentCategory.key == idea.category_key)).first()
    post = Post(
        topic=idea.title,
        objective=idea.description,
        target_audience=idea.target_audience,
        category_id=category.id if category else None,
        template_id=category.default_template_id if category else None,
        idea_id=idea.id,
        created_by_id=user_id,
        status=PostStatus.DRAFT,
        language=get_brand(db).default_language or "English",
    )
    db.add(post)
    db.flush()
    idea.status = IdeaStatus.USED
    record_event(db, post, "created", f"Created from idea #{idea.id}", to_status=PostStatus.DRAFT, actor_id=user_id)
    db.commit()
    return post
