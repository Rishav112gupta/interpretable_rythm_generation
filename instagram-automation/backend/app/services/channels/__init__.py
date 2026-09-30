"""Publishing channels - the extension point for Phase 2.

Phase 1 implements only Instagram. Every post carries a `channel` column
("instagram"), and the scheduler dispatches through `get_channel()`, so a
future WhatsApp channel can be added as a new class without changing the
content, approval or scheduling code.

Phase 2 notes (not implemented):
  * WhatsApp Business Platform (Cloud API) supports sending messages/templates
    to users who opted in and receiving messages via webhooks (leads, chatbot).
  * Posting WhatsApp *Status* updates is not offered by the official Cloud API
    at the time of writing - verify Meta's current docs before building it;
    the compliant alternative is opt-in broadcast template messages.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.models import Channel, Post


class PublishingChannel(ABC):
    key: str

    @abstractmethod
    def publish(self, db: Session, post_id: int, *, actor_id: int | None = None, manual: bool = False) -> Post: ...


class InstagramChannel(PublishingChannel):
    key = Channel.INSTAGRAM

    def publish(self, db: Session, post_id: int, *, actor_id: int | None = None, manual: bool = False) -> Post:
        from app.services.instagram.publisher import publish_post

        return publish_post(db, post_id, actor_id=actor_id, manual=manual)


_CHANNELS: dict[str, PublishingChannel] = {Channel.INSTAGRAM: InstagramChannel()}


def get_channel(key: str) -> PublishingChannel:
    try:
        return _CHANNELS[key]
    except KeyError as exc:
        raise ValueError(f"Channel '{key}' is not available in this version.") from exc
