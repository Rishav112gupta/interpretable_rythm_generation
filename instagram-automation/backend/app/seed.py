"""Idempotent seed: default templates, categories, brand profile row and first admin user.

Run with:  python -m app.seed
(also runs automatically at API startup)
"""

from __future__ import annotations

import logging
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models import BrandProfile, ContentCategory, Role, Template, User
from app.services.templates.defaults import DEFAULT_CATEGORIES, DEFAULT_TEMPLATES

logger = logging.getLogger(__name__)


def seed(db: Session) -> dict[str, int]:
    created = {"templates": 0, "categories": 0, "users": 0}
    templates: dict[str, Template] = {t.key: t for t in db.scalars(select(Template)).all()}
    for spec in DEFAULT_TEMPLATES:
        if spec["key"] not in templates:
            t = Template(key=spec["key"], name=spec["name"], description=spec["description"], layout=spec["layout"])
            db.add(t)
            db.flush()
            templates[t.key] = t
            created["templates"] += 1
    existing = {c.key for c in db.scalars(select(ContentCategory)).all()}
    for i, spec in enumerate(DEFAULT_CATEGORIES):
        if spec["key"] not in existing:
            db.add(
                ContentCategory(
                    key=spec["key"],
                    name=spec["name"],
                    description=spec["description"],
                    ai_guidance=spec["ai_guidance"],
                    color=spec["color"],
                    default_template_id=templates[spec["template"]].id if spec["template"] in templates else None,
                    sort_order=(i + 1) * 10,
                )
            )
            created["categories"] += 1
    if db.get(BrandProfile, 1) is None:
        db.add(BrandProfile(id=1, company_name="", default_hashtags=[], knowledge=[]))
    if db.scalars(select(User).limit(1)).first() is None:
        password = settings.first_admin_password
        if not password:
            password = secrets.token_urlsafe(12)
            logger.warning("=" * 70)
            logger.warning("FIRST_ADMIN_PASSWORD not set. Generated admin password: %s", password)
            logger.warning("Log in as %s and change it. This is shown only once.", settings.first_admin_email)
            logger.warning("=" * 70)
        db.add(User(email=settings.first_admin_email.lower(), full_name="Administrator", hashed_password=hash_password(password), role=Role.ADMIN))
        created["users"] += 1
    db.commit()
    return created


def main() -> None:
    from app.core.logging import configure_logging

    configure_logging(settings.log_level)
    with SessionLocal() as db:
        print(seed(db))


if __name__ == "__main__":
    main()
