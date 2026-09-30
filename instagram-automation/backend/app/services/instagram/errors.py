"""Classification of Meta Graph API errors.

Graph API errors look like:
  {"error": {"message": "...", "type": "OAuthException", "code": 190,
             "error_subcode": 463, "is_transient": false, "fbtrace_id": "..."}}

We classify them so the publisher knows whether to retry (temporary), stop and
ask a human to reconnect (token), or stop and show the error (permanent).
"""

from __future__ import annotations

from app.core.errors import ExternalServiceError

# Codes Meta documents as throttling / temporary problems.
TRANSIENT_CODES = {1, 2, 4, 17, 32, 341, 368, 613, 80001, 80002}
# Access-token problems -> the account must be reconnected.
TOKEN_CODES = {102, 190, 463, 467}
# Permission problems (missing scope / app review).
PERMISSION_CODES = {3, 10, 200, 299}
# Content publishing subcodes that are temporary.
TRANSIENT_SUBCODES = {
    2207001,  # Instagram server error
    2207003,  # timeout while fetching media
    2207020,  # media expired - create a new container
    2207032,  # create media failed, try again
    2207042,  # publishing limit reached - wait
    2207051,  # temporarily blocked / spam protection
}


class InstagramAPIError(ExternalServiceError):
    code = "instagram_api_error"

    def __init__(
        self,
        message: str,
        *,
        graph_code: int | None = None,
        subcode: int | None = None,
        http_status: int | None = None,
        transient: bool = False,
        token_problem: bool = False,
        ambiguous: bool = False,
        fbtrace_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            service="instagram",
            transient=transient,
            details={"graph_code": graph_code, "subcode": subcode, "http_status": http_status, "fbtrace_id": fbtrace_id},
        )
        self.graph_code = graph_code
        self.subcode = subcode
        self.http_status = http_status
        self.token_problem = token_problem
        # True when we cannot know whether the request took effect (e.g. a timeout
        # after sending media_publish). The publisher then verifies before retrying.
        self.ambiguous = ambiguous

    @property
    def short_code(self) -> str:
        if self.graph_code is None:
            return f"http_{self.http_status}" if self.http_status else "network"
        return f"{self.graph_code}" + (f"/{self.subcode}" if self.subcode else "")


class InstagramNotConnected(InstagramAPIError):
    def __init__(self, message: str = "No Instagram account is connected. Connect one in Settings → Instagram.") -> None:
        super().__init__(message, token_problem=True)


def from_graph_error(payload: dict, http_status: int) -> InstagramAPIError:
    err = (payload or {}).get("error") or {}
    code = err.get("code")
    subcode = err.get("error_subcode")
    message = err.get("error_user_msg") or err.get("message") or f"Instagram API returned HTTP {http_status}"
    token_problem = code in TOKEN_CODES or err.get("type") == "OAuthException" and code == 190
    transient = bool(err.get("is_transient")) or code in TRANSIENT_CODES or subcode in TRANSIENT_SUBCODES or http_status >= 500
    if token_problem:
        transient = False
        message = f"Instagram access token is invalid or expired: {message}"
    elif code in PERMISSION_CODES:
        message = f"Missing Instagram permission: {message}"
    return InstagramAPIError(
        message,
        graph_code=code,
        subcode=subcode,
        http_status=http_status,
        transient=transient,
        token_problem=token_problem,
        fbtrace_id=err.get("fbtrace_id"),
    )
