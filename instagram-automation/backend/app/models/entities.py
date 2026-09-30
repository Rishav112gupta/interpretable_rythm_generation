"""SQLAlchemy ORM models. PostgreSQL is the single source of truth."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.models.base import TimestampMixin, UTCDateTime, utcnow
from app.models.enums import AccountStatus, Channel, IdeaStatus, PostStatus, Role, ScheduleMode


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=Role.EDITOR)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class ContentCategory(TimestampMixin, Base):
    """Configurable content category (NORMAL, EXAM, ...). Admins can add more at runtime."""

    __tablename__ = "content_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    # Extra instructions given to the LLM for posts in this category.
    ai_guidance: Mapped[str] = mapped_column(Text, default="")
    color: Mapped[str] = mapped_column(String(20), default="#6366f1")
    default_template_id: Mapped[int | None] = mapped_column(ForeignKey("templates.id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)


class BrandProfile(TimestampMixin, Base):
    """Single-row brand configuration used by every AI generation."""

    __tablename__ = "brand_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    target_audience: Mapped[str] = mapped_column(Text, default="")
    brand_voice: Mapped[str] = mapped_column(Text, default="")
    tone: Mapped[str] = mapped_column(String(255), default="")
    words_to_use: Mapped[list[str]] = mapped_column(JSON, default=list)
    words_to_avoid: Mapped[list[str]] = mapped_column(JSON, default=list)
    cta_style: Mapped[str] = mapped_column(Text, default="")
    hashtag_strategy: Mapped[str] = mapped_column(Text, default="")
    default_hashtags: Mapped[list[str]] = mapped_column(JSON, default=list)
    visual_style: Mapped[str] = mapped_column(Text, default="")
    content_restrictions: Mapped[str] = mapped_column(Text, default="")
    default_language: Mapped[str] = mapped_column(String(50), default="English")
    primary_color: Mapped[str] = mapped_column(String(20), default="#1e3a8a")
    secondary_color: Mapped[str] = mapped_column(String(20), default="#f59e0b")
    logo_url: Mapped[str] = mapped_column(String(1024), default="")
    website: Mapped[str] = mapped_column(String(512), default="")
    contact_info: Mapped[str] = mapped_column(Text, default="")
    # Verified company facts: [{"label": "Course fee (JEE 2027)", "value": "Rs 45,000"}, ...]
    # The AI may only state prices, dates, statistics, etc. that appear here or in the post input.
    knowledge: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class Template(TimestampMixin, Base):
    """Design template. `layout` is a JSON spec rendered by services/templates/renderer.py."""

    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    width: Mapped[int] = mapped_column(Integer, default=1080)
    height: Mapped[int] = mapped_column(Integer, default=1350)
    layout: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Post(TimestampMixin, Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(30), default=Channel.INSTAGRAM, index=True)
    status: Mapped[str] = mapped_column(String(20), default=PostStatus.DRAFT, index=True)

    category_id: Mapped[int | None] = mapped_column(ForeignKey("content_categories.id", ondelete="SET NULL"), nullable=True)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("templates.id", ondelete="SET NULL"), nullable=True)
    schedule_id: Mapped[int | None] = mapped_column(ForeignKey("recurring_schedules.id", ondelete="SET NULL"), nullable=True, index=True)
    idea_id: Mapped[int | None] = mapped_column(ForeignKey("content_ideas.id", ondelete="SET NULL"), nullable=True)

    # --- Inputs from the content form ---
    topic: Mapped[str] = mapped_column(String(500), default="")
    target_audience: Mapped[str] = mapped_column(String(500), default="")
    tone: Mapped[str] = mapped_column(String(255), default="")
    objective: Mapped[str] = mapped_column(Text, default="")
    important_info: Mapped[str] = mapped_column(Text, default="")
    cta: Mapped[str] = mapped_column(String(500), default="")
    language: Mapped[str] = mapped_column(String(50), default="English")
    brand_instructions: Mapped[str] = mapped_column(Text, default="")
    reference_material: Mapped[str] = mapped_column(Text, default="")
    image_instructions: Mapped[str] = mapped_column(Text, default="")
    desired_publish_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    # --- Generated / edited content ---
    headline: Mapped[str] = mapped_column(String(300), default="")
    subtitle: Mapped[str] = mapped_column(String(500), default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    alternative_caption: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[list[str]] = mapped_column(JSON, default=list)
    content_summary: Mapped[str] = mapped_column(Text, default="")
    image_prompt: Mapped[str] = mapped_column(Text, default="")
    raw_image_url: Mapped[str] = mapped_column(String(1024), default="")  # AI/uploaded image before template
    image_url: Mapped[str] = mapped_column(String(1024), default="")  # final composed JPEG sent to Instagram

    # --- Human-review safety net ---
    review_flags: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    missing_information: Mapped[list[str]] = mapped_column(JSON, default=list)
    flags_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    rejected_reason: Mapped[str] = mapped_column(Text, default="")
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    # --- Scheduling / publishing ---
    scheduled_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    instagram_container_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    instagram_media_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    instagram_permalink: Mapped[str] = mapped_column(String(1024), default="")
    published_via_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    publish_attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    publishing_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")

    # --- Analytics (basic, from IG Media fields) ---
    like_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comments_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metrics_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    # --- AI generation metadata ---
    llm_provider: Mapped[str] = mapped_column(String(50), default="")
    llm_model: Mapped[str] = mapped_column(String(100), default="")
    image_provider: Mapped[str] = mapped_column(String(50), default="")
    image_model: Mapped[str] = mapped_column(String(100), default="")
    prompt_version: Mapped[str] = mapped_column(String(50), default="")
    generation_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_generation_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    regeneration_count: Mapped[int] = mapped_column(Integer, default=0)
    image_regeneration_count: Mapped[int] = mapped_column(Integer, default=0)
    generated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    sheet_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    category: Mapped[ContentCategory | None] = relationship(lazy="joined")
    template: Mapped[Template | None] = relationship(lazy="joined")
    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id], lazy="joined")
    events: Mapped[list[PostEvent]] = relationship(back_populates="post", cascade="all, delete-orphan", order_by="PostEvent.id")

    __table_args__ = (UniqueConstraint("schedule_id", "desired_publish_at", name="uq_post_schedule_slot"),)


class PostEvent(Base):
    """Audit trail: every status change, edit, generation and publish attempt."""

    __tablename__ = "post_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    post: Mapped[Post] = relationship(back_populates="events")


class PublishAttempt(Base):
    __tablename__ = "publish_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    transient: Mapped[bool] = mapped_column(Boolean, default=False)
    error_code: Mapped[str] = mapped_column(String(50), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    container_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    media_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mock: Mapped[bool] = mapped_column(Boolean, default=False)


class RecurringSchedule(TimestampMixin, Base):
    """E.g. "post every 4th day at 18:00 Asia/Kolkata".

    Two separate clocks:
      * content generation happens `generation_lead_hours` before each slot,
        producing a post in NEEDS_REVIEW;
      * publishing happens at the slot time - but only if a human approved it.
    """

    __tablename__ = "recurring_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    mode: Mapped[str] = mapped_column(String(20), default=ScheduleMode.ROLLING)
    interval_days: Mapped[int] = mapped_column(Integer, default=4)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    post_time: Mapped[time] = mapped_column(Time)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    generation_lead_hours: Mapped[int] = mapped_column(Integer, default=72)
    auto_generate: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_schedule_on_approval: Mapped[bool] = mapped_column(Boolean, default=True)

    category_id: Mapped[int | None] = mapped_column(ForeignKey("content_categories.id", ondelete="SET NULL"), nullable=True)
    # If set, categories are rotated in this order instead of a single category_id.
    category_rotation: Mapped[list[str]] = mapped_column(JSON, default=list)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("templates.id", ondelete="SET NULL"), nullable=True)
    topic_pool: Mapped[list[str]] = mapped_column(JSON, default=list)
    target_audience: Mapped[str] = mapped_column(String(500), default="")
    tone: Mapped[str] = mapped_column(String(255), default="")
    objective: Mapped[str] = mapped_column(Text, default="")
    cta: Mapped[str] = mapped_column(String(500), default="")
    language: Mapped[str] = mapped_column(String(50), default="English")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    category: Mapped[ContentCategory | None] = relationship(lazy="joined")


class InstagramAccount(TimestampMixin, Base):
    __tablename__ = "instagram_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    ig_user_id: Mapped[str] = mapped_column(String(100), default="")
    username: Mapped[str] = mapped_column(String(255), default="")
    account_type: Mapped[str] = mapped_column(String(50), default="")
    login_type: Mapped[str] = mapped_column(String(20), default="instagram")
    status: Mapped[str] = mapped_column(String(30), default=AccountStatus.NOT_CONNECTED)
    access_token_encrypted: Mapped[str] = mapped_column(Text, default="")  # Fernet-encrypted, never returned by the API
    token_source: Mapped[str] = mapped_column(String(20), default="")  # "oauth" | "env" | "mock"
    token_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    token_obtained_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    token_last_refreshed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_error_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)


class Competitor(TimestampMixin, Base):
    __tablename__ = "competitors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    instagram_handle: Mapped[str] = mapped_column(String(255), default="")
    website: Mapped[str] = mapped_column(String(512), default="")
    notes: Mapped[str] = mapped_column(Text, default="")

    observations: Mapped[list[CompetitorObservation]] = relationship(back_populates="competitor", cascade="all, delete-orphan", order_by="CompetitorObservation.id.desc()")


class CompetitorObservation(TimestampMixin, Base):
    """A human-recorded (or legally obtained) summary of one competitor post/pattern.

    We deliberately store *summaries and descriptions*, not copies of captions/images.
    """

    __tablename__ = "competitor_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id", ondelete="CASCADE"), index=True)
    content_topic: Mapped[str] = mapped_column(String(500), default="")
    content_type: Mapped[str] = mapped_column(String(50), default="image")
    caption_summary: Mapped[str] = mapped_column(Text, default="")
    visual_style: Mapped[str] = mapped_column(Text, default="")
    posting_frequency: Mapped[str] = mapped_column(String(100), default="")
    observed_strategy: Mapped[str] = mapped_column(Text, default="")
    cta_used: Mapped[str] = mapped_column(String(500), default="")
    engagement_notes: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(String(1024), default="")
    observed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")

    competitor: Mapped[Competitor] = relationship(back_populates="observations")


class StrategyInsight(TimestampMixin, Base):
    """AI-derived, high-level content strategy insights from competitor observations."""

    __tablename__ = "strategy_insights"

    id: Mapped[int] = mapped_column(primary_key=True)
    insights: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    observation_count: Mapped[int] = mapped_column(Integer, default=0)
    llm_provider: Mapped[str] = mapped_column(String(50), default="")
    llm_model: Mapped[str] = mapped_column(String(100), default="")
    use_in_generation: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class ContentIdea(TimestampMixin, Base):
    __tablename__ = "content_ideas"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    category_key: Mapped[str] = mapped_column(String(50), default="RANDOM")
    suggested_format: Mapped[str] = mapped_column(String(100), default="")
    target_audience: Mapped[str] = mapped_column(String(500), default="")
    source: Mapped[str] = mapped_column(String(30), default="ai")  # ai | sheet | manual
    status: Mapped[str] = mapped_column(String(20), default=IdeaStatus.NEW)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)


class AppSetting(Base):
    """Runtime-editable settings (timezone, publishing kill switch, ...)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class IntegrationLog(Base):
    """Errors and notable events from external integrations, shown on the dashboard."""

    __tablename__ = "integration_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50), index=True)  # instagram | llm | image | sheets | scheduler | ...
    level: Mapped[str] = mapped_column(String(10), default="error")
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    post_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)


__all__ = [
    "AppSetting",
    "BrandProfile",
    "Competitor",
    "CompetitorObservation",
    "ContentCategory",
    "ContentIdea",
    "InstagramAccount",
    "IntegrationLog",
    "Post",
    "PostEvent",
    "PublishAttempt",
    "RecurringSchedule",
    "StrategyInsight",
    "Template",
    "User",
]
