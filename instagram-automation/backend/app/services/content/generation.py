"""AI content generation: text (LLM) + image (image provider) + template composition."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ExternalServiceError, ImageGenerationError, LLMError, ValidationFailed
from app.models import BrandProfile, ContentCategory, Post, PostStatus, StrategyInsight, Template
from app.services.ai import prompts
from app.services.ai.fact_guard import check_unverified_facts, placeholder_flags
from app.services.ai.factory import get_llm_provider
from app.services.ai.schemas import POST_JSON_SCHEMA, GeneratedPost, parse_model
from app.services.content.audit import log_integration, record_event
from app.services.content.workflow import transition
from app.services.image_generation import get_image_provider
from app.services.storage import get_storage
from app.services.templates.renderer import RenderContent, load_uploaded_image, render_template, to_instagram_jpeg

logger = logging.getLogger(__name__)
S = PostStatus


def get_brand(db: Session) -> BrandProfile:
    brand = db.get(BrandProfile, 1)
    if brand is None:
        brand = BrandProfile(id=1)
        db.add(brand)
        db.flush()
    return brand


def brand_dict(brand: BrandProfile) -> dict[str, Any]:
    return {
        "company_name": brand.company_name,
        "description": brand.description,
        "target_audience": brand.target_audience,
        "brand_voice": brand.brand_voice,
        "tone": brand.tone,
        "words_to_use": brand.words_to_use or [],
        "words_to_avoid": brand.words_to_avoid or [],
        "cta_style": brand.cta_style,
        "hashtag_strategy": brand.hashtag_strategy,
        "default_hashtags": brand.default_hashtags or [],
        "visual_style": brand.visual_style,
        "content_restrictions": brand.content_restrictions,
        "default_language": brand.default_language,
        "website": brand.website,
        "contact_info": brand.contact_info,
        "knowledge": brand.knowledge or [],
    }


def latest_insights(db: Session) -> dict[str, Any] | None:
    row = db.scalars(select(StrategyInsight).where(StrategyInsight.use_in_generation.is_(True)).order_by(StrategyInsight.id.desc()).limit(1)).first()
    if not row:
        return None
    keep = ("common_topics", "content_gaps", "recurring_themes", "audience_targeting", "cta_patterns", "visual_trends", "recommendations")
    return {k: row.insights.get(k) for k in keep if row.insights.get(k)}


def verified_sources(brand: BrandProfile, post: Post) -> list[str]:
    facts = [f"{f.get('label', '')}: {f.get('value', '')}" for f in (brand.knowledge or [])]
    return facts + [
        brand.company_name,
        brand.website,
        brand.contact_info,
        brand.description,
        post.topic,
        post.important_info,
        post.cta,
        post.reference_material,
        post.brand_instructions,
        post.objective,
        post.target_audience,
    ]


def compute_flags(db: Session, post: Post) -> list[dict[str, str]]:
    brand = get_brand(db)
    texts = [post.headline, post.subtitle, post.caption, post.cta, post.alternative_caption]
    return check_unverified_facts(texts, verified_sources(brand, post)) + placeholder_flags(texts)


def _post_context(db: Session, post: Post, *, feedback: str | None = None) -> dict[str, Any]:
    brand = get_brand(db)
    category: ContentCategory | None = post.category
    return {
        "brand": brand_dict(brand),
        "category_key": category.key if category else "NORMAL",
        "category_name": category.name if category else "General",
        "category_guidance": category.ai_guidance if category else "",
        "topic": post.topic,
        "target_audience": post.target_audience or brand.target_audience,
        "tone": post.tone or brand.tone,
        "objective": post.objective,
        "important_info": post.important_info,
        "cta": post.cta,
        "language": post.language or brand.default_language,
        "brand_instructions": post.brand_instructions,
        "reference_material": post.reference_material,
        "image_instructions": post.image_instructions,
        "insights": latest_insights(db),
        "previous_headline": post.headline or None,
        "variant": post.regeneration_count,
        "feedback": feedback,
    }


def generate_text(db: Session, post: Post, *, actor_id: int | None = None, feedback: str | None = None) -> Post:
    if not post.topic.strip():
        raise ValidationFailed("A topic is required to generate content.")
    provider = get_llm_provider()
    ctx = _post_context(db, post, feedback=feedback)
    system, user = prompts.post_system_prompt(), prompts.post_user_prompt(ctx)
    last_error: LLMError | None = None
    result = generated = None
    for attempt in range(2):  # one automatic retry for transient/format errors
        try:
            result = provider.complete_json(task="post", system=system, user=user, schema=POST_JSON_SCHEMA, context=ctx)
            generated = parse_model(GeneratedPost, result.data)
            break
        except LLMError as err:
            last_error = err
            logger.warning("LLM attempt %s failed: %s", attempt + 1, err.message)
    if generated is None or result is None:
        assert last_error is not None
        log_integration(db, "llm", f"Text generation failed: {last_error.message}", post_id=post.id)
        record_event(db, post, "generation_failed", last_error.message, actor_id=actor_id)
        db.commit()
        raise last_error

    was_generated = post.generated_at is not None
    post.headline = generated.headline
    post.subtitle = generated.subtitle
    post.caption = generated.caption
    post.cta = post.cta or generated.cta
    post.hashtags = generated.hashtags
    post.image_prompt = generated.image_prompt
    post.alternative_caption = generated.alternative_caption
    post.content_summary = generated.content_summary
    post.missing_information = generated.missing_information
    post.flags_acknowledged = False
    post.llm_provider = result.provider
    post.llm_model = result.model
    post.prompt_version = prompts.PROMPT_VERSION
    post.generation_ms = result.duration_ms
    post.generated_at = datetime.now(UTC)
    if was_generated:
        post.regeneration_count += 1
    post.review_flags = compute_flags(db, post)
    record_event(
        db,
        post,
        "text_generated",
        f"Text {'re' if was_generated else ''}generated by {result.provider}/{result.model}",
        actor_id=actor_id,
        data={"duration_ms": result.duration_ms, "usage": result.usage, "flags": len(post.review_flags)},
    )
    if post.status in (S.DRAFT, S.REJECTED, S.APPROVED, S.SCHEDULED, S.FAILED, S.NEEDS_REVIEW):
        post.approved_at = None
        post.approved_by_id = None
        post.scheduled_at = None
        transition(db, post, S.AI_GENERATED, actor_id=actor_id)
    return post


def _template_for(db: Session, post: Post) -> Template | None:
    if post.template_id:
        return db.get(Template, post.template_id)
    if post.category and post.category.default_template_id:
        return db.get(Template, post.category.default_template_id)
    return db.scalars(select(Template).where(Template.is_active.is_(True)).order_by(Template.id).limit(1)).first()


def compose_image(db: Session, post: Post) -> str:
    """Render the post's template with its raw image and texts; store the Instagram-ready JPEG."""
    storage = get_storage()
    brand = get_brand(db)
    raw = None
    if post.raw_image_url:
        try:
            raw = storage.read(post.raw_image_url)
        except Exception:
            logger.warning("Raw image for post %s not readable", post.id)
    logo = None
    if brand.logo_url:
        try:
            logo = storage.read(brand.logo_url)
        except Exception:
            logo = None
    template = _template_for(db, post)
    if template is None:
        if raw is None:
            raise ImageGenerationError("No template and no image available to compose.")
        jpeg = to_instagram_jpeg(load_uploaded_image(raw))
    else:
        if template.id != post.template_id:
            post.template_id = template.id
        content = RenderContent(
            headline=post.headline,
            subtitle=post.subtitle,
            cta=post.cta,
            footer=" · ".join(x for x in [brand.company_name, brand.website] if x),
            category=post.category.name if post.category else "",
            company=brand.company_name,
            image=raw,
            logo=logo,
            tokens={"primary": brand.primary_color or "#1e3a8a", "secondary": brand.secondary_color or "#f59e0b"},
        )
        jpeg = render_template(template.layout, content, template.width, template.height)
    post.image_url = storage.save(jpeg, folder="posts", extension="jpg", content_type="image/jpeg")
    return post.image_url


def generate_image(db: Session, post: Post, *, actor_id: int | None = None) -> Post:
    if not post.image_prompt.strip():
        raise ValidationFailed("Generate the text first (an image prompt is needed).")
    provider = get_image_provider()
    brand = get_brand(db)
    prompt = post.image_prompt
    if brand.visual_style and brand.visual_style.lower() not in prompt.lower():
        prompt = f"{prompt}\nVisual style: {brand.visual_style}"
    if post.image_instructions and post.image_instructions not in prompt:
        prompt = f"{prompt}\nAdditional instructions: {post.image_instructions}"
    prompt += "\nDo not include any text, letters or logos in the image."
    try:
        result = provider.generate(prompt)
    except ImageGenerationError as err:
        log_integration(db, "image_generation", f"Image generation failed: {err.message}", post_id=post.id)
        record_event(db, post, "image_generation_failed", err.message, actor_id=actor_id)
        db.commit()
        raise
    storage = get_storage()
    ext = "png" if result.content_type == "image/png" else "jpg"
    had_image = bool(post.raw_image_url)
    post.raw_image_url = storage.save(result.data, folder="raw", extension=ext, content_type=result.content_type)
    post.image_provider = result.provider
    post.image_model = result.model
    post.image_generation_ms = result.duration_ms
    if had_image:
        post.image_regeneration_count += 1
    compose_image(db, post)
    record_event(
        db, post, "image_generated", f"Image {'re' if had_image else ''}generated by {result.provider}/{result.model}", actor_id=actor_id, data={"duration_ms": result.duration_ms}
    )
    _back_to_review_if_needed(db, post, actor_id, "Image changed - re-approval required.")
    return post


def replace_image(db: Session, post: Post, data: bytes, *, apply_template: bool, actor_id: int | None = None) -> Post:
    img = load_uploaded_image(data)
    storage = get_storage()
    if apply_template:
        post.raw_image_url = storage.save(
            data, folder="uploads", extension=(img.format or "png").lower().replace("jpeg", "jpg").replace("mpo", "jpg"), content_type=f"image/{(img.format or 'png').lower()}"
        )
        compose_image(db, post)
    else:
        jpeg = to_instagram_jpeg(img)
        post.raw_image_url = ""
        post.image_url = storage.save(jpeg, folder="posts", extension="jpg", content_type="image/jpeg")
    post.image_provider = "upload"
    post.image_model = ""
    record_event(db, post, "image_replaced", "Image uploaded by user" + (" (template applied)" if apply_template else ""), actor_id=actor_id)
    _back_to_review_if_needed(db, post, actor_id, "Image replaced - re-approval required.")
    return post


def _back_to_review_if_needed(db: Session, post: Post, actor_id: int | None, message: str) -> None:
    if post.status in (S.APPROVED, S.SCHEDULED, S.FAILED, S.REJECTED):
        post.approved_at = None
        post.approved_by_id = None
        post.scheduled_at = None
        transition(db, post, S.NEEDS_REVIEW, actor_id=actor_id, message=message)


def generate_full(db: Session, post: Post, *, actor_id: int | None = None, feedback: str | None = None) -> tuple[Post, list[str]]:
    """Generate text and image. Returns (post, warnings). Text failure raises; image failure is a warning."""
    warnings: list[str] = []
    generate_text(db, post, actor_id=actor_id, feedback=feedback)
    try:
        generate_image(db, post, actor_id=actor_id)
    except ExternalServiceError as err:
        warnings.append(f"Text was generated but the image failed: {err.message} You can regenerate or upload an image.")
        try:
            compose_image(db, post)  # template-only design without AI image
        except Exception:
            pass
    if post.status == S.AI_GENERATED:
        transition(db, post, S.NEEDS_REVIEW, actor_id=actor_id, message="Ready for human review")
    db.commit()
    db.refresh(post)
    return post, warnings
