"""Google Sheets integration (optional).

PostgreSQL remains the source of truth. The sheet is an export/control layer:

* EXPORT: every post is written to the sheet (one row per post, keyed by "Post ID").
  Status, caption, schedule, published flag and Instagram URL are overwritten
  from the database on each sync.
* IMPORT: rows that have a Topic but no Post ID are turned into DRAFT posts
  (content requests from the team). The new Post ID is written back so the row
  is not imported twice. Edits to other columns are NOT pulled back - edit
  content in the dashboard.

Authentication uses a Google Cloud *service account* (server-to-server, no
user login needed): share the sheet with the service account's email.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import SheetsError
from app.models import ContentCategory, Post, PostStatus
from app.services.ai.schemas import compose_caption
from app.services.content.audit import log_integration, record_event

COLUMNS = ["Post ID", "Date", "Category", "Topic", "Target Audience", "Status", "Caption", "Image", "Scheduled Time", "Published", "Instagram URL", "Last Synced"]


class SheetClient(ABC):
    @abstractmethod
    def read_rows(self) -> list[list[str]]:
        """All rows including the header row."""

    @abstractmethod
    def write_rows(self, start_row: int, rows: list[list[str]]) -> None:
        """Overwrite rows starting at 1-based `start_row`."""

    @abstractmethod
    def append_rows(self, rows: list[list[str]]) -> None: ...


class MockSheetClient(SheetClient):
    def __init__(self, rows: list[list[str]] | None = None, *, fail: bool = False) -> None:
        self.rows: list[list[str]] = rows if rows is not None else []
        self.fail = fail

    def _check(self):
        if self.fail:
            raise SheetsError("Mock Google Sheets failure (simulated).", transient=True)

    def read_rows(self) -> list[list[str]]:
        self._check()
        return [list(r) for r in self.rows]

    def write_rows(self, start_row: int, rows: list[list[str]]) -> None:
        self._check()
        for i, row in enumerate(rows):
            idx = start_row - 1 + i
            while len(self.rows) <= idx:
                self.rows.append([])
            self.rows[idx] = list(row)

    def append_rows(self, rows: list[list[str]]) -> None:
        self._check()
        self.rows.extend(list(r) for r in rows)


class GspreadSheetClient(SheetClient):
    def __init__(self) -> None:
        try:
            import gspread
            from google.oauth2.service_account import Credentials
        except ImportError as exc:  # pragma: no cover
            raise SheetsError("gspread/google-auth are not installed.") from exc
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        try:
            if settings.google_service_account_json:
                creds = Credentials.from_service_account_info(json.loads(settings.google_service_account_json), scopes=scopes)
            elif settings.google_service_account_file:
                creds = Credentials.from_service_account_file(settings.google_service_account_file, scopes=scopes)
            else:
                raise SheetsError("Set GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON.")
            if not settings.google_sheet_id:
                raise SheetsError("Set GOOGLE_SHEET_ID.")
            gc = gspread.authorize(creds)
            sheet = gc.open_by_key(settings.google_sheet_id)
            try:
                self.ws = sheet.worksheet(settings.google_sheet_worksheet)
            except gspread.WorksheetNotFound:
                self.ws = sheet.add_worksheet(settings.google_sheet_worksheet, rows=1000, cols=len(COLUMNS))
        except SheetsError:
            raise
        except Exception as exc:
            raise SheetsError(f"Could not open the Google Sheet: {type(exc).__name__}. Check the sheet ID and that it is shared with the service account.") from exc

    def read_rows(self) -> list[list[str]]:
        try:
            return self.ws.get_all_values()
        except Exception as exc:
            raise SheetsError(f"Reading the Google Sheet failed: {type(exc).__name__}", transient=True) from exc

    def write_rows(self, start_row: int, rows: list[list[str]]) -> None:
        if not rows:
            return
        end_col = chr(ord("A") + len(COLUMNS) - 1)
        try:
            self.ws.update(values=rows, range_name=f"A{start_row}:{end_col}{start_row + len(rows) - 1}")
        except Exception as exc:
            raise SheetsError(f"Writing to the Google Sheet failed: {type(exc).__name__}", transient=True) from exc

    def append_rows(self, rows: list[list[str]]) -> None:
        if not rows:
            return
        try:
            self.ws.append_rows(rows, value_input_option="RAW")
        except Exception as exc:
            raise SheetsError(f"Appending to the Google Sheet failed: {type(exc).__name__}", transient=True) from exc


_override: SheetClient | None = None
_mock: MockSheetClient | None = None


def get_sheet_client() -> SheetClient:
    global _mock
    if _override is not None:
        return _override
    if settings.mock_google_sheets:
        if _mock is None:
            _mock = MockSheetClient()
        return _mock
    return GspreadSheetClient()


def set_sheet_client(client: SheetClient | None) -> None:
    global _override
    _override = client


def _fmt(dt: datetime | None, tz: str) -> str:
    return dt.astimezone(ZoneInfo(tz)).strftime("%Y-%m-%d %H:%M") if dt else ""


def post_to_row(post: Post, tz: str) -> list[str]:
    when = post.scheduled_at or post.desired_publish_at or post.created_at
    return [
        str(post.id),
        _fmt(when, tz)[:10],
        post.category.key if post.category else "",
        post.topic,
        post.target_audience,
        post.status,
        compose_caption(post.caption, post.hashtags or [])[:5000],
        post.image_url,
        _fmt(post.scheduled_at, tz),
        ("YES (simulated)" if post.published_via_mock else "YES") if post.status == PostStatus.PUBLISHED else "NO",
        post.instagram_permalink,
        _fmt(datetime.now(UTC), tz),
    ]


def sync(db: Session, *, tz: str, user_id: int | None = None) -> dict[str, Any]:
    """Two-step sync: import new topic rows, then export all posts."""
    client = get_sheet_client()
    try:
        rows = client.read_rows()
        if not rows or [c.strip() for c in rows[0][: len(COLUMNS)]] != COLUMNS:
            if rows and any(cell.strip() for cell in rows[0]):
                # Keep user data: only (re)write the header row.
                client.write_rows(1, [COLUMNS])
                rows[0] = COLUMNS
            else:
                client.write_rows(1, [COLUMNS])
                rows = [COLUMNS]
        header = rows[0]
        idx = {name: header.index(name) for name in COLUMNS if name in header}

        def cell(row: list[str], name: str) -> str:
            i = idx.get(name)
            return row[i].strip() if i is not None and i < len(row) else ""

        imported = 0
        id_to_row: dict[int, int] = {}
        categories = {c.key: c for c in db.scalars(select(ContentCategory)).all()}
        for r_i, row in enumerate(rows[1:], start=2):
            pid = cell(row, "Post ID")
            if pid.isdigit():
                id_to_row[int(pid)] = r_i
                continue
            topic = cell(row, "Topic")
            if not topic or cell(row, "Status").upper() not in ("", "NEW", "IDEA", "TODO"):
                continue
            cat = categories.get(cell(row, "Category").upper().replace(" ", "_"))
            post = Post(
                topic=topic[:500],
                target_audience=cell(row, "Target Audience")[:500],
                category_id=cat.id if cat else None,
                template_id=cat.default_template_id if cat else None,
                status=PostStatus.DRAFT,
                created_by_id=user_id,
            )
            db.add(post)
            db.flush()
            record_event(db, post, "created", f"Imported from Google Sheets row {r_i}", to_status=PostStatus.DRAFT)
            id_to_row[post.id] = r_i
            imported += 1
        db.commit()

        posts = db.scalars(select(Post).order_by(Post.id)).all()
        updated = appended = 0
        to_append: list[list[str]] = []
        for post in posts:
            values = post_to_row(post, tz)
            if post.id in id_to_row:
                client.write_rows(id_to_row[post.id], [values])
                updated += 1
            else:
                to_append.append(values)
            post.sheet_synced_at = datetime.now(UTC)
        client.append_rows(to_append)
        appended = len(to_append)
        db.commit()
        return {"imported": imported, "updated": updated, "appended": appended}
    except SheetsError as err:
        db.rollback()
        log_integration(db, "google_sheets", err.message)
        db.commit()
        raise
