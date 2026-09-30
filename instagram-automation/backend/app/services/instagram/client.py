"""Instagram Platform (Meta Graph API) clients.

Official content-publishing flow for a single image (Instagram Platform docs):

  1. POST /{ig-user-id}/media           image_url=<public JPEG URL>, caption=<text>
       -> {"id": "<IG_CONTAINER_ID>"}
  2. GET  /{ig-container-id}?fields=status_code
       -> IN_PROGRESS | FINISHED | ERROR | EXPIRED | PUBLISHED
       (containers expire after 24 hours; poll at most ~once a minute for 5 min)
  3. POST /{ig-user-id}/media_publish   creation_id=<IG_CONTAINER_ID>
       -> {"id": "<IG_MEDIA_ID>"}
  4. GET  /{ig-media-id}?fields=id,permalink,timestamp,...

Rate limit: 100 API-published posts per 24h moving window per account;
check with GET /{ig-user-id}/content_publishing_limit.

Hosts: graph.instagram.com (Instagram API with Instagram Login) or
graph.facebook.com (Instagram API with Facebook Login). The API version is
configurable (META_GRAPH_API_VERSION) because Meta releases new versions
regularly.

The Graph API has no scheduling endpoint for Instagram posts, so scheduling is
done by *our* scheduler, which calls this flow at the right time.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.services.instagram.errors import InstagramAPIError, from_graph_error

MEDIA_FIELDS = "id,caption,media_type,media_url,permalink,timestamp,like_count,comments_count"


@dataclass
class AccountInfo:
    ig_user_id: str
    username: str
    account_type: str = ""
    name: str = ""


class InstagramClient(ABC):
    """Low-level API operations. `access_token` is passed per call and never stored here."""

    is_mock = False

    @abstractmethod
    def get_account(self, access_token: str, ig_user_id: str | None = None) -> AccountInfo: ...

    @abstractmethod
    def create_image_container(self, access_token: str, ig_user_id: str, image_url: str, caption: str) -> str: ...

    @abstractmethod
    def get_container_status(self, access_token: str, container_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def publish_container(self, access_token: str, ig_user_id: str, container_id: str) -> str: ...

    @abstractmethod
    def get_media(self, access_token: str, media_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def list_recent_media(self, access_token: str, ig_user_id: str, limit: int = 10) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_publishing_limit(self, access_token: str, ig_user_id: str) -> dict[str, Any]: ...


class GraphInstagramClient(InstagramClient):
    def __init__(self, host: str, version: str, timeout: float = 30.0, transport: httpx.BaseTransport | None = None) -> None:
        self.base = f"{host.rstrip('/')}/{version}"
        self.host = host.rstrip("/")
        self._client = httpx.Client(timeout=timeout, transport=transport)

    # -- plumbing ---------------------------------------------------------
    def _request(self, method: str, path: str, access_token: str, *, params: dict | None = None, data: dict | None = None, ambiguous_on_timeout: bool = False) -> dict[str, Any]:
        params = dict(params or {})
        params["access_token"] = access_token
        url = f"{self.base}/{path.lstrip('/')}"
        try:
            if method == "GET":
                resp = self._client.get(url, params=params)
            else:
                # Send the token in the query string and everything else as form data.
                resp = self._client.post(url, params={"access_token": access_token}, data=data or {})
        except httpx.TimeoutException as exc:
            raise InstagramAPIError("Instagram API request timed out.", transient=True, ambiguous=ambiguous_on_timeout) from exc
        except httpx.HTTPError:
            # Never include `exc` text: httpx errors can contain the full URL with the token.
            raise InstagramAPIError("Could not reach the Instagram API (network error).", transient=True, ambiguous=ambiguous_on_timeout) from None
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        if resp.status_code >= 400 or (isinstance(payload, dict) and "error" in payload):
            raise from_graph_error(payload if isinstance(payload, dict) else {}, resp.status_code)
        return payload if isinstance(payload, dict) else {"data": payload}

    # -- operations -------------------------------------------------------
    def get_account(self, access_token: str, ig_user_id: str | None = None) -> AccountInfo:
        if ig_user_id and "graph.facebook.com" in self.host:
            data = self._request("GET", ig_user_id, access_token, params={"fields": "id,username,name"})
            return AccountInfo(ig_user_id=str(data.get("id")), username=data.get("username", ""), name=data.get("name", ""), account_type="BUSINESS")
        data = self._request("GET", "me", access_token, params={"fields": "user_id,username,account_type,name"})
        return AccountInfo(
            ig_user_id=str(data.get("user_id") or data.get("id")),
            username=data.get("username", ""),
            account_type=data.get("account_type", ""),
            name=data.get("name", ""),
        )

    def create_image_container(self, access_token: str, ig_user_id: str, image_url: str, caption: str) -> str:
        data = self._request("POST", f"{ig_user_id}/media", access_token, data={"image_url": image_url, "caption": caption})
        if not data.get("id"):
            raise InstagramAPIError("Instagram did not return a media container id.")
        return str(data["id"])

    def get_container_status(self, access_token: str, container_id: str) -> dict[str, Any]:
        return self._request("GET", container_id, access_token, params={"fields": "id,status_code,status"})

    def publish_container(self, access_token: str, ig_user_id: str, container_id: str) -> str:
        data = self._request("POST", f"{ig_user_id}/media_publish", access_token, data={"creation_id": container_id}, ambiguous_on_timeout=True)
        if not data.get("id"):
            raise InstagramAPIError("Instagram did not return a media id after publishing.", ambiguous=True)
        return str(data["id"])

    def get_media(self, access_token: str, media_id: str) -> dict[str, Any]:
        return self._request("GET", media_id, access_token, params={"fields": MEDIA_FIELDS})

    def list_recent_media(self, access_token: str, ig_user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        data = self._request("GET", f"{ig_user_id}/media", access_token, params={"fields": "id,caption,timestamp,permalink", "limit": limit})
        return list(data.get("data", []))

    def get_publishing_limit(self, access_token: str, ig_user_id: str) -> dict[str, Any]:
        data = self._request("GET", f"{ig_user_id}/content_publishing_limit", access_token, params={"fields": "quota_usage,config"})
        items = data.get("data") or [{}]
        return items[0] if items else {}


@dataclass
class _MockContainer:
    id: str
    image_url: str
    caption: str
    status: str = "FINISHED"


@dataclass
class MockInstagramClient(InstagramClient):
    """In-memory stand-in for the Graph API. NOTHING is posted to Instagram.

    Supports fault injection so tests can exercise retries and duplicate
    protection: `fail_next` holds exceptions raised by the next calls to the
    named operation.
    """

    is_mock = True
    username: str = "mock_company_account"
    ig_user_id: str = "17840000000000000"
    containers: dict[str, _MockContainer] = field(default_factory=dict)
    media: dict[str, dict[str, Any]] = field(default_factory=dict)
    fail_next: dict[str, list[Exception]] = field(default_factory=dict)
    # Simulate "request reached Instagram but response was lost" for media_publish.
    publish_succeeds_then_times_out: bool = False
    calls: list[str] = field(default_factory=list)

    def _maybe_fail(self, op: str) -> None:
        self.calls.append(op)
        queue = self.fail_next.get(op)
        if queue:
            raise queue.pop(0)

    def get_account(self, access_token: str, ig_user_id: str | None = None) -> AccountInfo:
        self._maybe_fail("get_account")
        return AccountInfo(ig_user_id=self.ig_user_id, username=self.username, account_type="BUSINESS", name="Mock Company")

    def create_image_container(self, access_token: str, ig_user_id: str, image_url: str, caption: str) -> str:
        self._maybe_fail("create_image_container")
        if not image_url.startswith(("http://", "https://")):
            raise InstagramAPIError("image_url must be an absolute URL", graph_code=100, http_status=400)
        cid = f"mock_container_{uuid.uuid4().hex[:12]}"
        self.containers[cid] = _MockContainer(cid, image_url, caption)
        return cid

    def get_container_status(self, access_token: str, container_id: str) -> dict[str, Any]:
        self._maybe_fail("get_container_status")
        c = self.containers.get(container_id)
        if not c:
            raise InstagramAPIError("Unknown container", graph_code=100, http_status=400)
        return {"id": c.id, "status_code": c.status}

    def publish_container(self, access_token: str, ig_user_id: str, container_id: str) -> str:
        self._maybe_fail("publish_container")
        c = self.containers.get(container_id)
        if not c:
            raise InstagramAPIError("Unknown container", graph_code=100, http_status=400)
        if c.status == "PUBLISHED":
            raise InstagramAPIError("Container already published", graph_code=9004, http_status=400)
        mid = f"mock_media_{uuid.uuid4().hex[:12]}"
        c.status = "PUBLISHED"
        self.media[mid] = {"id": mid, "caption": c.caption, "media_type": "IMAGE", "permalink": "", "timestamp": "", "like_count": 0, "comments_count": 0}
        if self.publish_succeeds_then_times_out:
            self.publish_succeeds_then_times_out = False
            raise InstagramAPIError("Instagram API request timed out.", transient=True, ambiguous=True)
        return mid

    def get_media(self, access_token: str, media_id: str) -> dict[str, Any]:
        self._maybe_fail("get_media")
        if media_id not in self.media:
            raise InstagramAPIError("Unknown media", graph_code=100, http_status=400)
        return self.media[media_id]

    def list_recent_media(self, access_token: str, ig_user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        self._maybe_fail("list_recent_media")
        return list(reversed(list(self.media.values())))[:limit]

    def get_publishing_limit(self, access_token: str, ig_user_id: str) -> dict[str, Any]:
        self._maybe_fail("get_publishing_limit")
        return {"quota_usage": len(self.media), "config": {"quota_total": 100, "quota_duration": 86400}}
