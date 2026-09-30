import pytest
from sqlalchemy import select

from app.core.errors import LLMError
from app.models import IntegrationLog, Post, PostStatus
from app.services.ai.factory import set_llm_provider
from app.services.ai.mock_provider import MockLLMProvider
from app.services.content.generation import generate_full, generate_image, generate_text
from app.services.image_generation import MockImageProvider, set_image_provider
from app.services.storage import get_storage
from app.services.templates.renderer import check_instagram_image
from tests.helpers import category, make_generated_post


def test_generate_full_produces_reviewable_post_with_valid_image(db):
    post = make_generated_post(db)
    assert post.status == PostStatus.NEEDS_REVIEW
    assert post.headline and post.caption and post.hashtags and post.image_prompt
    assert post.llm_provider == "mock" and post.prompt_version
    assert post.image_url.startswith("http://testserver/media/posts/")
    assert check_instagram_image(get_storage().read(post.image_url)) == []
    events = [e.event_type for e in post.events]
    assert "text_generated" in events and "image_generated" in events


def test_regeneration_counts_increment(db):
    post = make_generated_post(db)
    generate_text(db, post)
    generate_image(db, post)
    assert post.regeneration_count == 1
    assert post.image_regeneration_count == 1


def test_llm_transient_failure_is_retried_once(db):
    provider = MockLLMProvider(fail_times=1)
    set_llm_provider(provider)
    post = make_generated_post(db)
    assert provider.calls == 2
    assert post.status == PostStatus.NEEDS_REVIEW


def test_llm_persistent_failure_raises_and_is_logged(db):
    set_llm_provider(MockLLMProvider(fail_times=5))
    cat = category(db)
    post = Post(topic="x", category_id=cat.id)
    db.add(post)
    db.commit()
    with pytest.raises(LLMError):
        generate_full(db, post)
    db.refresh(post)
    assert post.status == PostStatus.DRAFT
    assert db.scalars(select(IntegrationLog).where(IntegrationLog.source == "llm")).first() is not None


def test_invalid_llm_output_is_rejected(db):
    set_llm_provider(MockLLMProvider(return_invalid=True))
    post = Post(topic="x")
    db.add(post)
    db.commit()
    with pytest.raises(LLMError, match="expected format"):
        generate_text(db, post)


def test_image_failure_keeps_text_and_warns(db):
    set_image_provider(MockImageProvider(fail_times=1))
    cat = category(db)
    post = Post(topic="Revision plan", category_id=cat.id, template_id=cat.default_template_id, cta="Follow us")
    db.add(post)
    db.commit()
    post, warnings = generate_full(db, post)
    assert post.caption
    assert warnings and "image failed" in warnings[0]
    assert post.status == PostStatus.NEEDS_REVIEW
    assert post.image_url  # template-only design still produced
    assert db.scalars(select(IntegrationLog).where(IntegrationLog.source == "image_generation")).first() is not None


def test_generation_uses_brand_facts_for_verification(db):
    from app.services.content.generation import get_brand

    brand = get_brand(db)
    brand.company_name = "Acme Academy"
    brand.knowledge = [{"label": "Fee", "value": "Rs 4,999"}]
    db.commit()
    post = make_generated_post(db, important_info="Fee is ₹4,999 for the full course. Call 9876543210.")
    types = {f["type"] for f in post.review_flags}
    assert "price" not in types  # stated in the post input and knowledge base
    assert "phone" not in types  # stated in the post input
