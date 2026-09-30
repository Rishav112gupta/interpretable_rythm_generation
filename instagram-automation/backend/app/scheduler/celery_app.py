"""Celery worker + beat configuration.

Why Celery + Redis: publishing must happen even when nobody has the dashboard
open, must survive restarts, and must not block web requests. Beat triggers
small periodic "tick" tasks; the database (not the queue) holds the schedule,
so nothing is lost if Redis restarts.
"""

from __future__ import annotations

from celery import Celery

from app.core.config import settings
from app.core.logging import configure_logging

configure_logging(settings.log_level)

celery_app = Celery("instagram_automation", broker=settings.redis_url, backend=settings.redis_url, include=["app.scheduler.tasks"])
celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=15 * 60,
    task_soft_time_limit=14 * 60,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "publish-due-posts": {"task": "app.scheduler.tasks.publish_due_posts", "schedule": 60.0},
        "plan-recurring-schedules": {"task": "app.scheduler.tasks.plan_and_generate", "schedule": 600.0},
        "warn-missed-slots": {"task": "app.scheduler.tasks.warn_missed_slots", "schedule": 900.0},
        "refresh-instagram-token": {"task": "app.scheduler.tasks.refresh_instagram_token", "schedule": 6 * 3600.0},
        "refresh-post-metrics": {"task": "app.scheduler.tasks.refresh_post_metrics", "schedule": 6 * 3600.0},
        "sync-google-sheets": {"task": "app.scheduler.tasks.sync_google_sheets", "schedule": 1800.0},
    },
)
