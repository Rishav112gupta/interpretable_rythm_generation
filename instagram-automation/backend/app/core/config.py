"""Application configuration.

Every setting comes from environment variables (or a local `.env` file).
Nothing secret is ever hard-coded here - defaults are only safe development
placeholders, and `validate_for_production()` refuses to start in production
with those placeholders.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET_KEY = "dev-insecure-secret-key-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore", case_sensitive=False)

    # ---- General -------------------------------------------------------
    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "Instagram Automation"
    secret_key: str = DEV_SECRET_KEY
    # Fernet key used to encrypt OAuth tokens at rest. Generate with:
    # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    token_encryption_key: str = ""
    access_token_expire_minutes: int = 720
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    # Public URL of this backend. Used to build absolute image URLs.
    # Instagram must be able to download images from here (see README).
    public_base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"
    default_timezone: str = "Asia/Kolkata"
    log_level: str = "INFO"

    first_admin_email: str = "admin@example.com"
    first_admin_password: str = ""

    # ---- Database / queue ------------------------------------------------
    database_url: str = "postgresql+psycopg://insta:insta@localhost:5432/insta"
    redis_url: str = "redis://localhost:6379/0"

    # ---- Mock switches (development without credentials) ----------------
    mock_llm: bool = True
    mock_image_generation: bool = True
    mock_instagram: bool = True
    mock_google_sheets: bool = True

    # ---- LLM -------------------------------------------------------------
    llm_provider: Literal["mock", "anthropic", "openai"] = "mock"
    llm_api_key: str = ""
    llm_model: str = ""
    # Only for the "openai" provider: any OpenAI-compatible endpoint.
    llm_base_url: str = "https://api.openai.com/v1"
    llm_timeout_seconds: float = 120.0

    # ---- Image generation --------------------------------------------------
    image_provider: Literal["mock", "openai", "none"] = "mock"
    image_api_key: str = ""
    image_model: str = "gpt-image-1"
    image_base_url: str = "https://api.openai.com/v1"
    image_timeout_seconds: float = 180.0

    # ---- Storage -----------------------------------------------------------
    storage_backend: Literal["local", "s3"] = "local"
    media_root: str = "./media"
    s3_bucket: str = ""
    s3_region: str = ""
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_public_base_url: str = ""

    # ---- Meta / Instagram --------------------------------------------------
    # "instagram": Instagram API with Instagram Login (graph.instagram.com)
    # "facebook":  Instagram API with Facebook Login (graph.facebook.com)
    meta_login_type: Literal["instagram", "facebook"] = "instagram"
    meta_graph_api_version: str = "v25.0"
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_redirect_uri: str = "http://localhost:8000/api/instagram/oauth/callback"
    meta_oauth_scopes: str = "instagram_business_basic,instagram_business_content_publish"
    # Optional: a token generated in the Meta App Dashboard instead of OAuth.
    meta_access_token: str = ""
    instagram_account_id: str = ""
    meta_http_timeout_seconds: float = 30.0

    # ---- Publishing ----------------------------------------------------------
    publishing_enabled: bool = True
    publish_retry_delays: str = "60,300,900"  # seconds: 1 min, 5 min, 15 min
    container_status_poll_attempts: int = 5
    container_status_poll_interval_seconds: float = 3.0
    stale_publishing_minutes: int = 15

    # ---- Google Sheets -------------------------------------------------------
    google_sheets_enabled: bool = False
    google_service_account_file: str = ""
    google_service_account_json: str = ""
    google_sheet_id: str = ""
    google_sheet_worksheet: str = "Posts"

    # ---- Rate limits ---------------------------------------------------------
    login_rate_limit_per_minute: int = 10
    generation_rate_limit_per_minute: int = 20

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        # Hosting providers often hand out postgres:// URLs; SQLAlchemy needs a driver.
        if v.startswith("postgres://"):
            v = "postgresql+psycopg://" + v[len("postgres://") :]
        elif v.startswith("postgresql://"):
            v = "postgresql+psycopg://" + v[len("postgresql://") :]
        return v

    # ---- Derived helpers -----------------------------------------------------
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def retry_delays(self) -> list[int]:
        return [int(x) for x in self.publish_retry_delays.split(",") if x.strip()]

    @property
    def effective_llm_provider(self) -> str:
        return "mock" if self.mock_llm else self.llm_provider

    @property
    def effective_image_provider(self) -> str:
        return "mock" if self.mock_image_generation else self.image_provider

    @property
    def graph_host(self) -> str:
        return "https://graph.instagram.com" if self.meta_login_type == "instagram" else "https://graph.facebook.com"

    def validate_for_production(self) -> list[str]:
        """Return a list of configuration problems that must block a production start."""
        problems: list[str] = []
        if self.app_env != "production":
            return problems
        if self.secret_key == DEV_SECRET_KEY or len(self.secret_key) < 32:
            problems.append("SECRET_KEY must be set to a random value of at least 32 characters.")
        if not self.token_encryption_key:
            problems.append("TOKEN_ENCRYPTION_KEY must be set (Fernet key).")
        if self.public_base_url.startswith("http://localhost"):
            problems.append("PUBLIC_BASE_URL must be a public https URL in production.")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
