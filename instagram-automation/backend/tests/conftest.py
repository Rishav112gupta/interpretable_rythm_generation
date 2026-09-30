"""Test configuration.

Tests NEVER call real external services: all providers are mocks, and the
Instagram client is an in-memory fake. By default tests use SQLite; set
TEST_DATABASE_URL to run the same suite against PostgreSQL.
"""

from __future__ import annotations

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="insta-tests-")
os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db"),
        "MEDIA_ROOT": f"{_tmp}/media",
        "PUBLIC_BASE_URL": "http://testserver",
        "MOCK_LLM": "true",
        "MOCK_IMAGE_GENERATION": "true",
        "MOCK_INSTAGRAM": "true",
        "MOCK_GOOGLE_SHEETS": "true",
        "CONTAINER_STATUS_POLL_INTERVAL_SECONDS": "0",
        "FIRST_ADMIN_EMAIL": "admin@example.com",
        "FIRST_ADMIN_PASSWORD": "admin-password-123",
        "SECRET_KEY": "test-secret-key-that-is-long-enough-1234567890",
        "META_ACCESS_TOKEN": "",
        "INSTAGRAM_ACCOUNT_ID": "",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.rate_limit import rate_limiter  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.database.session import Base, SessionLocal, engine  # noqa: E402
from app.models import Role, User  # noqa: E402
from app.seed import seed  # noqa: E402
from app.services.ai.factory import set_llm_provider  # noqa: E402
from app.services.google_sheets import set_sheet_client  # noqa: E402
from app.services.image_generation import set_image_provider  # noqa: E402
from app.services.instagram import account as ig_account  # noqa: E402
from app.services.instagram.client import MockInstagramClient  # noqa: E402
from app.services.storage import LocalStorage, set_storage  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    set_storage(LocalStorage(os.environ["MEDIA_ROOT"], "http://testserver"))
    rate_limiter.reset()
    yield
    set_llm_provider(None)
    set_image_provider(None)
    set_sheet_client(None)
    ig_account.set_client(None)
    ig_account._mock_singleton = None


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def ig_mock() -> MockInstagramClient:
    client = MockInstagramClient()
    ig_account.set_client(client)
    return client


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


def _token(client: TestClient, email: str, password: str) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def admin_headers(client):
    return _token(client, "admin@example.com", "admin-password-123")


@pytest.fixture
def make_user(db):
    def _make(role: Role, email: str | None = None) -> tuple[str, str]:
        email = email or f"{role.value}@example.com"
        db.add(User(email=email, full_name=role.value, hashed_password=hash_password("user-password-123"), role=role))
        db.commit()
        return email, "user-password-123"

    return _make


@pytest.fixture
def headers_for(client, make_user):
    def _h(role: Role) -> dict[str, str]:
        email, pw = make_user(role)
        return _token(client, email, pw)

    return _h
