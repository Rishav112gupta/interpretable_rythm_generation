from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"  # everything, including users, settings and Instagram connection
    APPROVER = "approver"  # can approve/reject/schedule/publish
    EDITOR = "editor"  # can create, generate and edit content
    VIEWER = "viewer"  # read-only


class PostStatus(StrEnum):
    DRAFT = "DRAFT"
    AI_GENERATED = "AI_GENERATED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    # Internal lock state while an Instagram API call is in flight. It is what
    # guarantees two workers can never publish the same post twice.
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class Channel(StrEnum):
    INSTAGRAM = "instagram"
    # Phase 2 (not implemented yet): WHATSAPP_STATUS = "whatsapp_status"


class AccountStatus(StrEnum):
    NOT_CONNECTED = "not_connected"
    CONNECTED = "connected"
    TOKEN_EXPIRED = "token_expired"
    ERROR = "error"


class IdeaStatus(StrEnum):
    NEW = "new"
    USED = "used"
    DISMISSED = "dismissed"


class ScheduleMode(StrEnum):
    # Every N days counted continuously from the start date (1st, 5th, 9th, ... of any month).
    ROLLING = "rolling"
    # Days N, 2N, 3N ... of every month (e.g. 4th, 8th, 12th ... 28th), restarting each month.
    MONTHLY = "monthly"
