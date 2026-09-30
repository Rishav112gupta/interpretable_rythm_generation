"""The real Graph API client, exercised against a fake HTTP transport (no network)."""

import json

import httpx
import pytest

from app.services.instagram.client import GraphInstagramClient
from app.services.instagram.errors import InstagramAPIError

TOKEN = "IGAAsecretTOKENvalue1234567890abcdef"


def make(handler):
    return GraphInstagramClient("https://graph.instagram.com", "v25.0", transport=httpx.MockTransport(handler))


def test_publish_flow_uses_documented_endpoints():
    seen = []

    def handler(request: httpx.Request):
        seen.append((request.method, request.url.path, dict(request.url.params), request.content.decode()))
        path = request.url.path
        if path.endswith("/17841/media") and request.method == "POST":
            return httpx.Response(200, json={"id": "c1"})
        if path.endswith("/c1"):
            return httpx.Response(200, json={"id": "c1", "status_code": "FINISHED"})
        if path.endswith("/17841/media_publish"):
            return httpx.Response(200, json={"id": "m1"})
        if path.endswith("/17841/content_publishing_limit"):
            return httpx.Response(200, json={"data": [{"quota_usage": 3, "config": {"quota_total": 100}}]})
        return httpx.Response(404, json={"error": {"message": "nope", "code": 100}})

    c = make(handler)
    assert c.create_image_container(TOKEN, "17841", "https://cdn.example.com/a.jpg", "Hello #tag") == "c1"
    assert c.get_container_status(TOKEN, "c1")["status_code"] == "FINISHED"
    assert c.publish_container(TOKEN, "17841", "c1") == "m1"
    assert c.get_publishing_limit(TOKEN, "17841")["quota_usage"] == 3
    method, path, params, body = seen[0]
    assert (method, path) == ("POST", "/v25.0/17841/media")
    assert params["access_token"] == TOKEN
    assert "image_url=https%3A%2F%2Fcdn.example.com%2Fa.jpg" in body and "caption=Hello" in body
    assert seen[2][1] == "/v25.0/17841/media_publish" and "creation_id=c1" in seen[2][3]
    assert seen[1][2]["fields"] == "id,status_code,status"


@pytest.mark.parametrize(
    "error,transient,token",
    [
        ({"code": 190, "type": "OAuthException", "message": "Error validating access token"}, False, True),
        ({"code": 4, "message": "Application request limit reached"}, True, False),
        ({"code": 9, "error_subcode": 2207042, "message": "Max posts reached"}, True, False),
        ({"code": 100, "message": "Invalid parameter"}, False, False),
        ({"code": 1, "message": "Unknown error", "is_transient": True}, True, False),
    ],
)
def test_error_classification(error, transient, token):
    c = make(lambda r: httpx.Response(400, json={"error": error}))
    with pytest.raises(InstagramAPIError) as ei:
        c.get_media(TOKEN, "m1")
    assert ei.value.transient is transient
    assert ei.value.token_problem is token


def test_server_error_is_transient():
    c = make(lambda r: httpx.Response(502, text="Bad gateway"))
    with pytest.raises(InstagramAPIError) as ei:
        c.get_media(TOKEN, "m1")
    assert ei.value.transient


def test_network_errors_never_leak_token():
    def handler(request):
        raise httpx.ConnectError(f"failed to connect to {request.url}")

    c = make(handler)
    with pytest.raises(InstagramAPIError) as ei:
        c.get_media(TOKEN, "m1")
    assert TOKEN not in str(ei.value) and TOKEN not in json.dumps(ei.value.details)
    assert ei.value.transient


def test_publish_timeout_is_marked_ambiguous():
    def handler(request):
        raise httpx.ReadTimeout("timeout")

    with pytest.raises(InstagramAPIError) as ei:
        make(handler).publish_container(TOKEN, "1", "c1")
    assert ei.value.ambiguous and ei.value.transient


def test_get_account_instagram_login():
    c = make(lambda r: httpx.Response(200, json={"user_id": "1784", "username": "acme", "account_type": "BUSINESS"}))
    info = c.get_account(TOKEN)
    assert (info.ig_user_id, info.username, info.account_type) == ("1784", "acme", "BUSINESS")
