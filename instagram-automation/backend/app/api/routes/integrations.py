"""Instagram connection, Google Sheets and dashboard."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import admin, approver, viewer
from app.core.config import settings
from app.core.errors import AppError
from app.database.session import get_db
from app.models import AccountStatus, IntegrationLog, Post, PostStatus, User
from app.schemas.api import InstagramStatusOut, IntegrationLogOut, PostOut
from app.services import app_settings
from app.services import google_sheets as sheets
from app.services.instagram import account as ig_account
from app.services.instagram.errors import InstagramAPIError

router = APIRouter()
logger = logging.getLogger(__name__)
S = PostStatus


# --------------------------------------------------------------- Instagram
def _status(db: Session, with_limit: bool = False) -> InstagramStatusOut:
    acc = ig_account.get_account(db)
    db.commit()
    limit = None
    if with_limit and acc.status == AccountStatus.CONNECTED:
        try:
            token, ig_id, _ = ig_account.get_credentials(db)
            limit = ig_account.get_client().get_publishing_limit(token, ig_id)
        except InstagramAPIError as err:
            limit = {"error": err.message}
    return InstagramStatusOut(
        connected=acc.status == AccountStatus.CONNECTED,
        status=acc.status,
        is_mock=acc.is_mock,
        username=acc.username,
        ig_user_id=acc.ig_user_id,
        account_type=acc.account_type,
        login_type=acc.login_type or settings.meta_login_type,
        token_source=acc.token_source,
        token_expires_at=acc.token_expires_at,
        token_last_refreshed_at=acc.token_last_refreshed_at,
        scopes=acc.scopes or [],
        last_success_at=acc.last_success_at,
        last_error=acc.last_error,
        last_error_at=acc.last_error_at,
        oauth_available=bool(settings.meta_app_id and settings.meta_app_secret and settings.meta_login_type == "instagram" and not settings.mock_instagram),
        publishing_limit=limit,
    )


@router.get("/instagram/status", response_model=InstagramStatusOut, tags=["instagram"])
def instagram_status(include_limit: bool = False, _: User = Depends(viewer), db: Session = Depends(get_db)):
    return _status(db, include_limit)


@router.get("/instagram/oauth/start", tags=["instagram"])
def oauth_start(user: User = Depends(admin)):
    """Returns the Instagram authorization URL. The browser navigates there."""
    return {"authorize_url": ig_account.build_authorize_url(user.id)}


@router.get("/instagram/oauth/callback", tags=["instagram"], include_in_schema=False)
def oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = Query(default=None, max_length=500),
    db: Session = Depends(get_db),
):
    """Instagram redirects the browser here after the user approves (or denies) access."""
    target = f"{settings.frontend_url.rstrip('/')}/settings"
    if error or not code or not state:
        return RedirectResponse(f"{target}?{urlencode({'ig_error': error_description or error or 'Connection cancelled'})}")
    try:
        acc = ig_account.handle_oauth_callback(db, code, state)
        db.commit()
    except (AppError, InstagramAPIError) as err:
        db.rollback()
        logger.warning("Instagram OAuth callback failed: %s", err.message)
        return RedirectResponse(f"{target}?{urlencode({'ig_error': err.message})}")
    return RedirectResponse(f"{target}?{urlencode({'ig_connected': acc.username})}")


@router.post("/instagram/test", response_model=InstagramStatusOut, tags=["instagram"])
def test_connection(_: User = Depends(admin), db: Session = Depends(get_db)):
    try:
        ig_account.verify_connection(db)
        db.commit()
    except InstagramAPIError:
        db.commit()
        raise
    return _status(db, True)


@router.post("/instagram/refresh-token", response_model=InstagramStatusOut, tags=["instagram"])
def refresh_token(_: User = Depends(admin), db: Session = Depends(get_db)):
    ig_account.refresh_token_if_needed(db, force=True)
    db.commit()
    return _status(db)


@router.post("/instagram/disconnect", response_model=InstagramStatusOut, tags=["instagram"])
def disconnect(_: User = Depends(admin), db: Session = Depends(get_db)):
    ig_account.disconnect(db)
    db.commit()
    return _status(db)


# ------------------------------------------------------------ Google Sheets
@router.get("/sheets/status", tags=["google-sheets"])
def sheets_status(_: User = Depends(viewer), db: Session = Depends(get_db)):
    last = db.scalar(select(func.max(Post.sheet_synced_at)))
    return {
        "enabled": settings.google_sheets_enabled or settings.mock_google_sheets,
        "mock": settings.mock_google_sheets,
        "sheet_id_configured": bool(settings.google_sheet_id),
        "worksheet": settings.google_sheet_worksheet,
        "auto_sync": app_settings.get_setting(db, "sheets_auto_sync"),
        "last_synced_at": last,
        "columns": sheets.COLUMNS,
    }


@router.post("/sheets/sync", tags=["google-sheets"])
def sheets_sync(user: User = Depends(approver), db: Session = Depends(get_db)):
    if not (settings.google_sheets_enabled or settings.mock_google_sheets):
        raise AppError("Google Sheets integration is disabled. Set GOOGLE_SHEETS_ENABLED=true (see README).")
    result = sheets.sync(db, tz=app_settings.get_timezone(db), user_id=user.id)
    return {**result, "mock": settings.mock_google_sheets}


@router.get("/sheets/preview", tags=["google-sheets"])
def sheets_preview(_: User = Depends(viewer)):
    """Mock mode only: show the in-memory sheet so the sync can be inspected without Google."""
    if not settings.mock_google_sheets:
        raise AppError("Preview is only available in mock mode - open the real Google Sheet instead.")
    return {"rows": sheets.get_sheet_client().read_rows()[:200]}


# ---------------------------------------------------------------- Dashboard
@router.get("/dashboard", tags=["dashboard"])
def dashboard(_: User = Depends(viewer), db: Session = Depends(get_db)):
    now = datetime.now(UTC)
    counts = dict(db.execute(select(Post.status, func.count()).group_by(Post.status)).all())
    upcoming = db.scalars(select(Post).where(Post.status == S.SCHEDULED, Post.scheduled_at >= now - timedelta(minutes=5)).order_by(Post.scheduled_at).limit(8)).unique().all()
    planned = (
        db.scalars(
            select(Post).where(Post.desired_publish_at >= now, Post.status.in_([S.DRAFT, S.AI_GENERATED, S.NEEDS_REVIEW, S.APPROVED])).order_by(Post.desired_publish_at).limit(8)
        )
        .unique()
        .all()
    )
    recent = db.scalars(select(Post).order_by(Post.updated_at.desc()).limit(8)).unique().all()
    errors = db.scalars(select(IntegrationLog).where(IntegrationLog.level.in_(["error", "warning"])).order_by(IntegrationLog.id.desc()).limit(8)).all()
    ig = _status(db)
    return {
        "counts": {
            "total": sum(counts.values()),
            "draft": counts.get(S.DRAFT, 0) + counts.get(S.AI_GENERATED, 0),
            "pending_approval": counts.get(S.NEEDS_REVIEW, 0),
            "approved": counts.get(S.APPROVED, 0),
            "scheduled": counts.get(S.SCHEDULED, 0) + counts.get(S.PUBLISHING, 0),
            "published": counts.get(S.PUBLISHED, 0),
            "failed": counts.get(S.FAILED, 0),
            "rejected": counts.get(S.REJECTED, 0),
            "by_status": counts,
        },
        "next_scheduled": PostOut.from_post(upcoming[0]) if upcoming else None,
        "upcoming": [PostOut.from_post(p) for p in upcoming],
        "planned_needing_review": [PostOut.from_post(p) for p in planned],
        "recent": [PostOut.from_post(p) for p in recent],
        "recent_errors": [IntegrationLogOut.model_validate(e) for e in errors],
        "instagram": ig,
        "publishing_enabled": app_settings.get_setting(db, "publishing_enabled"),
        "timezone": app_settings.get_timezone(db),
    }
