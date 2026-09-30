"""Instagram account connection, token storage and token refresh.

Tokens are encrypted at rest (Fernet) and never returned to the frontend.

Supported ways to connect:
  1. OAuth "Business Login for Instagram" (META_LOGIN_TYPE=instagram, recommended):
       authorize:  https://www.instagram.com/oauth/authorize
       code->token: POST https://api.instagram.com/oauth/access_token  (short-lived, ~1 hour)
       long-lived:  GET https://graph.instagram.com/access_token?grant_type=ig_exchange_token (60 days)
       refresh:     GET https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token
                    (token must be >= 24h old and still valid)
  2. A token pasted into the environment (META_ACCESS_TOKEN + INSTAGRAM_ACCOUNT_ID), e.g. a
     Facebook Login System User token (META_LOGIN_TYPE=facebook) that does not expire.
  3. Mock mode (MOCK_INSTAGRAM=true): a simulated account. Nothing is posted.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import create_state_token, decode_token, decrypt_secret, encrypt_secret
from app.models import AccountStatus, InstagramAccount
from app.services.content.audit import log_integration
from app.services.instagram.client import GraphInstagramClient, InstagramClient, MockInstagramClient
from app.services.instagram.errors import InstagramAPIError, InstagramNotConnected, from_graph_error

AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
SHORT_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
REFRESH_WHEN_DAYS_LEFT = 15

_client_override: InstagramClient | None = None
_mock_singleton: MockInstagramClient | None = None


def get_client() -> InstagramClient:
    global _mock_singleton
    if _client_override is not None:
        return _client_override
    if settings.mock_instagram:
        if _mock_singleton is None:
            _mock_singleton = MockInstagramClient()
        return _mock_singleton
    return GraphInstagramClient(settings.graph_host, settings.meta_graph_api_version, settings.meta_http_timeout_seconds)


def set_client(client: InstagramClient | None) -> None:
    global _client_override
    _client_override = client


def get_account_row(db: Session) -> InstagramAccount:
    acc = db.get(InstagramAccount, 1)
    if acc is None:
        acc = InstagramAccount(id=1, login_type=settings.meta_login_type)
        db.add(acc)
        db.flush()
    return acc


def _sync_mode(db: Session, acc: InstagramAccount) -> InstagramAccount:
    """Make the stored account consistent with the current mock/real configuration."""
    client = get_client()
    if client.is_mock:
        if not acc.is_mock or acc.status != AccountStatus.CONNECTED:
            info = client.get_account("mock-token")
            acc.is_mock = True
            acc.ig_user_id = info.ig_user_id
            acc.username = info.username
            acc.account_type = info.account_type
            acc.status = AccountStatus.CONNECTED
            acc.token_source = "mock"
            acc.access_token_encrypted = encrypt_secret("mock-token")
            acc.token_expires_at = None
            acc.last_error = ""
        return acc
    if acc.is_mock:  # switched from mock to real: forget the fake account
        acc.is_mock = False
        acc.status = AccountStatus.NOT_CONNECTED
        acc.access_token_encrypted = ""
        acc.ig_user_id = ""
        acc.username = ""
        acc.token_source = ""
    if acc.status == AccountStatus.NOT_CONNECTED and settings.meta_access_token and settings.instagram_account_id:
        acc.access_token_encrypted = encrypt_secret(settings.meta_access_token)
        acc.ig_user_id = settings.instagram_account_id
        acc.token_source = "env"
        acc.login_type = settings.meta_login_type
        acc.status = AccountStatus.CONNECTED
        acc.token_obtained_at = datetime.now(UTC)
    return acc


def get_account(db: Session) -> InstagramAccount:
    return _sync_mode(db, get_account_row(db))


def get_credentials(db: Session) -> tuple[str, str, InstagramAccount]:
    acc = get_account(db)
    if acc.status == AccountStatus.TOKEN_EXPIRED:
        raise InstagramNotConnected("The Instagram access token has expired. Reconnect the account in Settings → Instagram.")
    if acc.status != AccountStatus.CONNECTED or not acc.access_token_encrypted or not acc.ig_user_id:
        raise InstagramNotConnected()
    try:
        token = decrypt_secret(acc.access_token_encrypted)
    except ValueError as exc:
        raise InstagramNotConnected(str(exc)) from exc
    return token, acc.ig_user_id, acc


def record_success(acc: InstagramAccount) -> None:
    acc.last_success_at = datetime.now(UTC)


def record_error(db: Session, acc: InstagramAccount, err: InstagramAPIError, post_id: int | None = None) -> None:
    acc.last_error = err.message
    acc.last_error_at = datetime.now(UTC)
    if err.token_problem and not isinstance(err, InstagramNotConnected):
        acc.status = AccountStatus.TOKEN_EXPIRED
    log_integration(db, "instagram", err.message, details=err.details, post_id=post_id)


# ----------------------------------------------------------------------- OAuth
def build_authorize_url(user_id: int) -> str:
    if settings.meta_login_type != "instagram":
        raise AppError("OAuth connect is implemented for META_LOGIN_TYPE=instagram. For Facebook Login, set META_ACCESS_TOKEN and INSTAGRAM_ACCOUNT_ID.")
    if not settings.meta_app_id or not settings.meta_app_secret:
        raise AppError("META_APP_ID and META_APP_SECRET must be configured before connecting Instagram.")
    state = create_state_token({"user_id": user_id})
    query = {
        "client_id": settings.meta_app_id,
        "redirect_uri": settings.meta_redirect_uri,
        "response_type": "code",
        "scope": settings.meta_oauth_scopes,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(query)}"


def _http() -> httpx.Client:
    return httpx.Client(timeout=settings.meta_http_timeout_seconds)


def _json_or_error(resp: httpx.Response) -> dict:
    try:
        payload = resp.json()
    except ValueError:
        payload = {}
    if resp.status_code >= 400 or "error" in payload or "error_type" in payload:
        if "error_type" in payload:  # api.instagram.com style error
            payload = {"error": {"message": payload.get("error_message", "OAuth error"), "code": payload.get("code")}}
        raise from_graph_error(payload, resp.status_code)
    return payload


def exchange_code(code: str) -> tuple[str, int | None, list[str]]:
    """Authorization code -> long-lived token. Returns (token, expires_in_seconds, permissions)."""
    code = code.split("#")[0]
    with _http() as http:
        try:
            short = _json_or_error(
                http.post(
                    SHORT_TOKEN_URL,
                    data={
                        "client_id": settings.meta_app_id,
                        "client_secret": settings.meta_app_secret,
                        "grant_type": "authorization_code",
                        "redirect_uri": settings.meta_redirect_uri,
                        "code": code,
                    },
                )
            )
            item = short["data"][0] if isinstance(short.get("data"), list) and short["data"] else short
            short_token = item["access_token"]
            permissions = item.get("permissions") or []
            if isinstance(permissions, str):
                permissions = [p.strip() for p in permissions.split(",") if p.strip()]
            long = _json_or_error(
                http.get(
                    "https://graph.instagram.com/access_token",
                    params={"grant_type": "ig_exchange_token", "client_secret": settings.meta_app_secret, "access_token": short_token},
                )
            )
        except httpx.HTTPError:
            raise InstagramAPIError("Could not reach Instagram to complete the connection.", transient=True) from None
        except KeyError as exc:
            raise InstagramAPIError("Unexpected response from Instagram token endpoint.") from exc
    return long["access_token"], long.get("expires_in"), permissions


def handle_oauth_callback(db: Session, code: str, state: str) -> InstagramAccount:
    try:
        decode_token(state, expected_type="oauth_state")
    except jwt.PyJWTError as exc:
        raise AppError("Invalid or expired connection request. Start the Instagram connection again.") from exc
    token, expires_in, permissions = exchange_code(code)
    client = get_client()
    info = client.get_account(token)
    now = datetime.now(UTC)
    acc = get_account_row(db)
    acc.is_mock = False
    acc.ig_user_id = info.ig_user_id
    acc.username = info.username
    acc.account_type = info.account_type
    acc.login_type = "instagram"
    acc.access_token_encrypted = encrypt_secret(token)
    acc.token_source = "oauth"
    acc.token_obtained_at = now
    acc.token_last_refreshed_at = now
    acc.token_expires_at = now + timedelta(seconds=int(expires_in)) if expires_in else None
    acc.scopes = permissions
    acc.status = AccountStatus.CONNECTED
    acc.last_error = ""
    acc.last_success_at = now
    return acc


def refresh_token_if_needed(db: Session, *, force: bool = False) -> bool:
    """Refresh a long-lived Instagram Login token before it expires. Returns True if refreshed."""
    acc = get_account(db)
    if acc.is_mock or acc.token_source != "oauth" or acc.status != AccountStatus.CONNECTED:
        return False
    now = datetime.now(UTC)
    if acc.token_expires_at and acc.token_expires_at <= now:
        acc.status = AccountStatus.TOKEN_EXPIRED
        log_integration(db, "instagram", "Instagram token expired - reconnect the account.")
        return False
    old_enough = acc.token_last_refreshed_at is None or now - acc.token_last_refreshed_at >= timedelta(hours=24)
    due = force or acc.token_expires_at is None or acc.token_expires_at - now <= timedelta(days=REFRESH_WHEN_DAYS_LEFT)
    if not (old_enough and due):
        return False
    token = decrypt_secret(acc.access_token_encrypted)
    try:
        with _http() as http:
            data = _json_or_error(http.get("https://graph.instagram.com/refresh_access_token", params={"grant_type": "ig_refresh_token", "access_token": token}))
    except httpx.HTTPError:
        log_integration(db, "instagram", "Network error while refreshing the Instagram token; will retry.", level="warning")
        return False
    except InstagramAPIError as err:
        record_error(db, acc, err)
        return False
    acc.access_token_encrypted = encrypt_secret(data["access_token"])
    acc.token_last_refreshed_at = now
    if data.get("expires_in"):
        acc.token_expires_at = now + timedelta(seconds=int(data["expires_in"]))
    return True


def verify_connection(db: Session) -> InstagramAccount:
    """Call the API to confirm the token works (used by the 'Test connection' button)."""
    token, ig_user_id, acc = get_credentials(db)
    try:
        info = get_client().get_account(token, ig_user_id if acc.login_type == "facebook" else None)
    except InstagramAPIError as err:
        record_error(db, acc, err)
        raise
    acc.username = info.username or acc.username
    acc.account_type = info.account_type or acc.account_type
    record_success(acc)
    return acc


def disconnect(db: Session) -> InstagramAccount:
    acc = get_account_row(db)
    acc.access_token_encrypted = ""
    acc.status = AccountStatus.NOT_CONNECTED
    acc.token_source = ""
    acc.token_expires_at = None
    acc.scopes = []
    acc.is_mock = False
    return acc
