"""Request/response schemas (input validation for every endpoint)."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import Role, ScheduleMode


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------ auth/users
class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserOut(ORM):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login_at: datetime | None = None


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(default="", max_length=255)
    password: str = Field(min_length=10, max_length=200)
    role: Role = Role.EDITOR


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=10, max_length=200)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=200)


# --------------------------------------------------------------- categories
class CategoryIn(BaseModel):
    key: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z][A-Z0-9_]*$")
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    ai_guidance: str = Field(default="", max_length=4000)
    color: str = Field(default="#6366f1", pattern=r"^#[0-9a-fA-F]{3,8}$")
    default_template_id: int | None = None
    is_active: bool = True
    sort_order: int = 100


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    ai_guidance: str | None = Field(default=None, max_length=4000)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{3,8}$")
    default_template_id: int | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class CategoryOut(ORM):
    id: int
    key: str
    name: str
    description: str
    ai_guidance: str
    color: str
    default_template_id: int | None
    is_active: bool
    sort_order: int


# ------------------------------------------------------------------- brand
class KnowledgeItem(BaseModel):
    label: str = Field(max_length=200)
    value: str = Field(max_length=2000)


class BrandIn(BaseModel):
    company_name: str = Field(default="", max_length=255)
    description: str = Field(default="", max_length=5000)
    target_audience: str = Field(default="", max_length=2000)
    brand_voice: str = Field(default="", max_length=2000)
    tone: str = Field(default="", max_length=255)
    words_to_use: list[str] = Field(default_factory=list, max_length=100)
    words_to_avoid: list[str] = Field(default_factory=list, max_length=100)
    cta_style: str = Field(default="", max_length=1000)
    hashtag_strategy: str = Field(default="", max_length=1000)
    default_hashtags: list[str] = Field(default_factory=list, max_length=30)
    visual_style: str = Field(default="", max_length=2000)
    content_restrictions: str = Field(default="", max_length=4000)
    default_language: str = Field(default="English", max_length=50)
    primary_color: str = Field(default="#1e3a8a", pattern=r"^#[0-9a-fA-F]{3,8}$")
    secondary_color: str = Field(default="#f59e0b", pattern=r"^#[0-9a-fA-F]{3,8}$")
    logo_url: str = Field(default="", max_length=1024)
    website: str = Field(default="", max_length=512)
    contact_info: str = Field(default="", max_length=2000)
    knowledge: list[KnowledgeItem] = Field(default_factory=list, max_length=300)

    @field_validator("default_hashtags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        return [t.strip().lstrip("#").replace(" ", "") for t in v if t.strip()]


class BrandOut(BrandIn, ORM):
    updated_at: datetime | None = None


# ----------------------------------------------------------------- templates
class TemplateIn(BaseModel):
    key: str = Field(min_length=2, max_length=50, pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    width: int = Field(default=1080, ge=320, le=1440)
    height: int = Field(default=1350, ge=320, le=1800)
    layout: dict[str, Any]
    is_active: bool = True


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    width: int | None = Field(default=None, ge=320, le=1440)
    height: int | None = Field(default=None, ge=320, le=1800)
    layout: dict[str, Any] | None = None
    is_active: bool | None = None


class TemplateOut(ORM):
    id: int
    key: str
    name: str
    description: str
    width: int
    height: int
    layout: dict[str, Any]
    is_active: bool


# -------------------------------------------------------------------- posts
class PostCreate(BaseModel):
    category_id: int | None = None
    template_id: int | None = None
    topic: str = Field(min_length=1, max_length=500)
    target_audience: str = Field(default="", max_length=500)
    tone: str = Field(default="", max_length=255)
    objective: str = Field(default="", max_length=2000)
    important_info: str = Field(default="", max_length=4000)
    cta: str = Field(default="", max_length=500)
    language: str = Field(default="English", max_length=50)
    brand_instructions: str = Field(default="", max_length=4000)
    reference_material: str = Field(default="", max_length=10000)
    image_instructions: str = Field(default="", max_length=2000)
    desired_publish_at: datetime | None = None
    generate: bool = False

    @field_validator("desired_publish_at")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("must include timezone offset")
        return v


class PostUpdate(BaseModel):
    category_id: int | None = None
    template_id: int | None = None
    topic: str | None = Field(default=None, max_length=500)
    target_audience: str | None = Field(default=None, max_length=500)
    tone: str | None = Field(default=None, max_length=255)
    objective: str | None = Field(default=None, max_length=2000)
    important_info: str | None = Field(default=None, max_length=4000)
    cta: str | None = Field(default=None, max_length=500)
    language: str | None = Field(default=None, max_length=50)
    brand_instructions: str | None = Field(default=None, max_length=4000)
    reference_material: str | None = Field(default=None, max_length=10000)
    image_instructions: str | None = Field(default=None, max_length=2000)
    desired_publish_at: datetime | None = None
    headline: str | None = Field(default=None, max_length=120)
    subtitle: str | None = Field(default=None, max_length=200)
    caption: str | None = Field(default=None, max_length=2200)
    alternative_caption: str | None = Field(default=None, max_length=2200)
    hashtags: list[str] | None = Field(default=None, max_length=30)
    image_prompt: str | None = Field(default=None, max_length=4000)
    recompose_image: bool = True

    @field_validator("hashtags")
    @classmethod
    def _tags(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        from app.services.ai.schemas import normalize_hashtag

        return [t for t in (normalize_hashtag(x) for x in v) if t]


class RegenerateIn(BaseModel):
    feedback: str = Field(default="", max_length=2000)


class ApproveIn(BaseModel):
    acknowledge_flags: bool = False
    schedule_at: datetime | None = None
    use_desired_time: bool = True


class RejectIn(BaseModel):
    reason: str = Field(default="", max_length=2000)


class ScheduleIn(BaseModel):
    scheduled_at: datetime

    @field_validator("scheduled_at")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("must include timezone offset")
        return v


class PostEventOut(ORM):
    id: int
    event_type: str
    from_status: str | None
    to_status: str | None
    message: str
    data: dict[str, Any]
    actor_id: int | None
    created_at: datetime


class PostOut(ORM):
    id: int
    channel: str
    status: str
    category_id: int | None
    category_key: str | None = None
    category_name: str | None = None
    category_color: str | None = None
    template_id: int | None
    schedule_id: int | None
    idea_id: int | None
    topic: str
    target_audience: str
    tone: str
    objective: str
    important_info: str
    cta: str
    language: str
    brand_instructions: str
    reference_material: str
    image_instructions: str
    desired_publish_at: datetime | None
    headline: str
    subtitle: str
    caption: str
    alternative_caption: str
    hashtags: list[str]
    content_summary: str
    image_prompt: str
    raw_image_url: str
    image_url: str
    review_flags: list[dict[str, Any]]
    missing_information: list[str]
    flags_acknowledged: bool
    rejected_reason: str
    approved_by_id: int | None
    approved_at: datetime | None
    scheduled_at: datetime | None
    published_at: datetime | None
    instagram_media_id: str | None
    instagram_permalink: str
    published_via_mock: bool
    publish_attempts: int
    next_retry_at: datetime | None
    last_error: str
    like_count: int | None
    comments_count: int | None
    llm_provider: str
    llm_model: str
    image_provider: str
    image_model: str
    prompt_version: str
    generation_ms: int | None
    image_generation_ms: int | None
    regeneration_count: int
    image_regeneration_count: int
    generated_at: datetime | None
    created_by_id: int | None
    created_by_name: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_post(cls, post) -> PostOut:
        out = cls.model_validate(post)
        if post.category:
            out.category_key = post.category.key
            out.category_name = post.category.name
            out.category_color = post.category.color
        if post.created_by:
            out.created_by_name = post.created_by.full_name or post.created_by.email
        return out


class PostDetailOut(PostOut):
    events: list[PostEventOut] = []
    warnings: list[str] = []


class PostListOut(BaseModel):
    items: list[PostOut]
    total: int


# ----------------------------------------------------------------- schedules
class ScheduleBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    mode: ScheduleMode = ScheduleMode.ROLLING
    interval_days: int = Field(default=4, ge=1, le=365)
    start_date: date
    end_date: date | None = None
    post_time: time
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    generation_lead_hours: int = Field(default=72, ge=0, le=24 * 30)
    auto_generate: bool = True
    auto_schedule_on_approval: bool = True
    category_id: int | None = None
    category_rotation: list[str] = Field(default_factory=list, max_length=50)
    template_id: int | None = None
    topic_pool: list[str] = Field(default_factory=list, max_length=500)
    target_audience: str = Field(default="", max_length=500)
    tone: str = Field(default="", max_length=255)
    objective: str = Field(default="", max_length=2000)
    cta: str = Field(default="", max_length=500)
    language: str = Field(default="English", max_length=50)
    is_active: bool = True


class ScheduleOut(ScheduleBase, ORM):
    id: int
    next_slots: list[datetime] = []
    created_at: datetime


class SchedulePreviewIn(BaseModel):
    mode: ScheduleMode = ScheduleMode.ROLLING
    interval_days: int = Field(default=4, ge=1, le=365)
    start_date: date
    end_date: date | None = None
    post_time: time
    timezone: str = "Asia/Kolkata"
    count: int = Field(default=10, ge=1, le=60)


# --------------------------------------------------------------- competitors
class CompetitorIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    instagram_handle: str = Field(default="", max_length=255)
    website: str = Field(default="", max_length=512)
    notes: str = Field(default="", max_length=4000)


class CompetitorOut(CompetitorIn, ORM):
    id: int
    observation_count: int = 0
    created_at: datetime


class ObservationIn(BaseModel):
    content_topic: str = Field(default="", max_length=500)
    content_type: str = Field(default="image", max_length=50)
    caption_summary: str = Field(default="", max_length=500, description="Your own short summary - do not paste the caption")
    visual_style: str = Field(default="", max_length=2000)
    posting_frequency: str = Field(default="", max_length=100)
    observed_strategy: str = Field(default="", max_length=2000)
    cta_used: str = Field(default="", max_length=500)
    engagement_notes: str = Field(default="", max_length=2000)
    source_url: str = Field(default="", max_length=1024)
    observed_on: date | None = None
    notes: str = Field(default="", max_length=4000)


class ObservationOut(ObservationIn, ORM):
    id: int
    competitor_id: int
    created_at: datetime


class InsightOut(ORM):
    id: int
    insights: dict[str, Any]
    observation_count: int
    llm_provider: str
    llm_model: str
    use_in_generation: bool
    created_at: datetime


class AnalyzeIn(BaseModel):
    competitor_ids: list[int] | None = None


# ---------------------------------------------------------------------- ideas
class IdeasGenerateIn(BaseModel):
    count: int = Field(default=7, ge=1, le=20)
    theme: str = Field(default="", max_length=500)
    target_audience: str = Field(default="", max_length=500)


class IdeaOut(ORM):
    id: int
    title: str
    description: str
    category_key: str
    suggested_format: str
    target_audience: str
    source: str
    status: str
    created_at: datetime


# ------------------------------------------------------------------ settings
class SettingsUpdate(BaseModel):
    timezone: str | None = Field(default=None, max_length=64)
    publishing_enabled: bool | None = None
    sheets_auto_sync: bool | None = None


class InstagramStatusOut(BaseModel):
    connected: bool
    status: str
    is_mock: bool
    username: str
    ig_user_id: str
    account_type: str
    login_type: str
    token_source: str
    token_expires_at: datetime | None
    token_last_refreshed_at: datetime | None
    scopes: list[str]
    last_success_at: datetime | None
    last_error: str
    last_error_at: datetime | None
    oauth_available: bool
    publishing_limit: dict[str, Any] | None = None


class IntegrationLogOut(ORM):
    id: int
    source: str
    level: str
    message: str
    details: dict[str, Any]
    post_id: int | None
    created_at: datetime


TokenOut.model_rebuild()
