"""Periodic tasks. Each one is a thin wrapper around a service function, and
uses a Redis lock so two beat ticks never overlap."""

from __future__ import annotations

import logging
from contextlib import contextmanager

from app.core.config import settings
from app.database.session import SessionLocal
from app.scheduler.celery_app import celery_app

logger = logging.getLogger(__name__)


@contextmanager
def single_run(name: str, timeout: int = 600):
    """Skip the task if the previous run is still going (e.g. slow API)."""
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url)
        lock = client.lock(f"lock:{name}", timeout=timeout, blocking=False)
        acquired = lock.acquire(blocking=False)
    except Exception:
        lock, acquired = None, True  # Redis unavailable: DB-level guards still prevent duplicates
    if not acquired:
        logger.info("Task %s already running; skipping this tick", name)
        yield False
        return
    try:
        yield True
    finally:
        if lock is not None:
            try:
                lock.release()
            except Exception:
                pass


@celery_app.task(name="app.scheduler.tasks.publish_due_posts")
def publish_due_posts() -> dict:
    from app.services.instagram.publisher import publish_due_posts as run

    with single_run("publish_due_posts") as ok:
        if not ok:
            return {"skipped": True}
        with SessionLocal() as db:
            result = run(db)
    if any(result.get(k) for k in ("published", "failed", "retrying", "recovered")):
        logger.info("publish_due_posts: %s", result)
    return result


@celery_app.task(name="app.scheduler.tasks.plan_and_generate")
def plan_and_generate() -> dict:
    from app.services.scheduling import planner

    with single_run("plan_and_generate", timeout=1800) as ok:
        if not ok:
            return {"skipped": True}
        with SessionLocal() as db:
            planned = planner.plan_all(db)
            gen = planner.generate_due_content(db)
    return {"planned": planned, **gen}


@celery_app.task(name="app.scheduler.tasks.warn_missed_slots")
def warn_missed_slots() -> int:
    from app.services.scheduling import planner

    with SessionLocal() as db:
        return planner.warn_missed_slots(db)


@celery_app.task(name="app.scheduler.tasks.refresh_instagram_token")
def refresh_instagram_token() -> bool:
    from app.services.instagram import account

    with SessionLocal() as db:
        refreshed = account.refresh_token_if_needed(db)
        db.commit()
        return refreshed


@celery_app.task(name="app.scheduler.tasks.refresh_post_metrics")
def refresh_post_metrics() -> int:
    from app.services.instagram.publisher import refresh_metrics

    with SessionLocal() as db:
        return refresh_metrics(db)


@celery_app.task(name="app.scheduler.tasks.sync_google_sheets")
def sync_google_sheets() -> dict:
    from app.core.errors import SheetsError
    from app.services import app_settings
    from app.services import google_sheets as sheets

    if not (settings.google_sheets_enabled or settings.mock_google_sheets):
        return {"skipped": "disabled"}
    with SessionLocal() as db:
        if not app_settings.get_setting(db, "sheets_auto_sync"):
            return {"skipped": "auto sync off"}
        try:
            return sheets.sync(db, tz=app_settings.get_timezone(db))
        except SheetsError as err:
            return {"error": err.message}


@celery_app.task(name="app.scheduler.tasks.deliver_webhooks")
def deliver_webhooks() -> dict:
    from app.services.automation import webhooks

    with single_run("deliver_webhooks", timeout=300) as ok:
        if not ok:
            return {"skipped": True}
        with SessionLocal() as db:
            return webhooks.deliver_pending(db)


@celery_app.task(name="app.scheduler.tasks.cleanup_webhooks")
def cleanup_webhooks() -> int:
    from app.services.automation import webhooks

    with SessionLocal() as db:
        return webhooks.cleanup_old(db)
