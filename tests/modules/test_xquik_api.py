"""Tests for the Xquik API integration modules."""

from typing import Any, Dict, Optional
from unittest.mock import patch

import pytest

from core.constants import APIEndpoints, EnvVars
from core.modules.registry import ModuleRegistry
from core.modules.third_party.developer.xquik import (
    XquikCreateTweetModule,
    XquikGetTweetModule,
    XquikGetUserModule,
    XquikGetWriteActionModule,
    XquikRequestModule,
    XquikSearchTweetsModule,
)


class FakeResponse:
    """Async response context with a JSON payload."""

    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self.payload = payload

    async def json(self) -> Any:
        return self.payload

    async def text(self) -> str:
        return ""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class FakeSession:
    """Capture one Xquik request without network access."""

    def __init__(self, response: FakeResponse, *, timeout) -> None:
        self.response = response
        self.timeout = timeout
        self.request_details: Optional[Dict[str, Any]] = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def request(self, method: str, url: str, **kwargs):
        self.request_details = {
            "method": method,
            "url": url,
            **kwargs,
        }
        return self.response


def session_factory(response: FakeResponse, captured: list[FakeSession]):
    """Return a ClientSession replacement that records each instance."""

    def factory(*, timeout):
        session = FakeSession(response, timeout=timeout)
        captured.append(session)
        return session

    return factory


def xquik_patch(response: FakeResponse, captured: list[FakeSession]):
    """Patch only the Xquik module's HTTP client."""

    return patch(
        "core.modules.third_party.developer.xquik.aiohttp.ClientSession",
        side_effect=session_factory(response, captured),
    )


@pytest.mark.asyncio
async def test_search_tweets_uses_contract_auth_and_filters(monkeypatch) -> None:
    monkeypatch.setenv(EnvVars.XQUIK_API_KEY, "test-key")
    captured: list[FakeSession] = []
    response = FakeResponse(
        200,
        {
            "tweets": [{"id": "123", "text": "Flyto2"}],
            "has_next_page": True,
            "next_cursor": "next",
        },
    )

    with xquik_patch(response, captured):
        result = await XquikSearchTweetsModule(
            {
                "query": '"Flyto2"',
                "query_type": "Latest",
                "limit": 50,
                "cursor": "current",
                "filters": {"verifiedOnly": True},
            },
            {},
        ).execute()

    assert result == {
        "status": "success",
        "http_status": 200,
        "data": {
            "tweets": [{"id": "123", "text": "Flyto2"}],
            "has_next_page": True,
            "next_cursor": "next",
        },
        "tweets": [{"id": "123", "text": "Flyto2"}],
        "count": 1,
        "has_next_page": True,
        "next_cursor": "next",
    }
    assert captured[0].timeout.total == 30
    assert captured[0].request_details == {
        "method": "GET",
        "url": f"{APIEndpoints.XQUIK_BASE_URL}/x/tweets/search",
        "headers": {
            "Accept": "application/json",
            "x-api-key": "test-key",
            "xquik-api-contract": APIEndpoints.XQUIK_API_CONTRACT,
        },
        "params": {
            "verifiedOnly": True,
            "q": '"Flyto2"',
            "queryType": "Latest",
            "limit": 50,
            "cursor": "current",
        },
    }


@pytest.mark.asyncio
async def test_search_tweets_reports_missing_api_key(monkeypatch) -> None:
    monkeypatch.delenv(EnvVars.XQUIK_API_KEY, raising=False)

    result = await XquikSearchTweetsModule({"query": "Flyto2"}, {}).execute()

    assert result == {
        "status": "error",
        "message": "Set XQUIK_API_KEY or provide api_key.",
    }


@pytest.mark.asyncio
async def test_api_request_supports_documented_write_paths(monkeypatch) -> None:
    monkeypatch.delenv(EnvVars.XQUIK_API_KEY, raising=False)
    captured: list[FakeSession] = []

    with xquik_patch(FakeResponse(202, {"action": {"id": "action-1"}}), captured):
        result = await XquikRequestModule(
            {
                "api_key": "param-key",
                "method": "POST",
                "path": "/x/users/42/follow",
                "body": {"account": "@flyto2"},
                "idempotency_key": "write-1",
            },
            {},
        ).execute()

    assert result == {
        "status": "success",
        "http_status": 202,
        "data": {"action": {"id": "action-1"}},
    }
    assert captured[0].request_details == {
        "method": "POST",
        "url": f"{APIEndpoints.XQUIK_BASE_URL}/x/users/42/follow",
        "headers": {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Idempotency-Key": "write-1",
            "x-api-key": "param-key",
            "xquik-api-contract": APIEndpoints.XQUIK_API_CONTRACT,
        },
        "json": {"account": "@flyto2"},
    }


@pytest.mark.parametrize(
    ("params", "message"),
    [
        (
            {"method": "GET", "path": "https://example.com/x/tweets"},
            "path must be an absolute Xquik API path without a host or query",
        ),
        (
            {"method": "GET", "path": "/x/tweets?ids=1"},
            "path must be an absolute Xquik API path without a host or query",
        ),
        (
            {"method": "POST", "path": "/x/tweets", "body": {}},
            "idempotency_key must contain 1 to 255 visible ASCII characters",
        ),
        (
            {
                "method": "POST",
                "path": "/x/tweets",
                "body": {},
                "idempotency_key": "not valid",
            },
            "idempotency_key must contain 1 to 255 visible ASCII characters",
        ),
    ],
)
def test_api_request_rejects_unsafe_or_non_idempotent_inputs(
    params,
    message,
) -> None:
    with pytest.raises(ValueError, match=message):
        XquikRequestModule(params, {})


@pytest.mark.asyncio
async def test_api_errors_preserve_status_without_exposing_credentials() -> None:
    captured: list[FakeSession] = []
    response = FakeResponse(429, {"error": "rate_limited", "message": "Retry later."})

    with xquik_patch(response, captured):
        result = await XquikGetUserModule(
            {"user": "flyto2", "api_key": "secret-value"},
            {},
        ).execute()

    assert result == {
        "status": "error",
        "message": "Retry later.",
        "http_status": 429,
        "data": {"error": "rate_limited", "message": "Retry later."},
    }
    assert "secret-value" not in str(result)


@pytest.mark.asyncio
async def test_get_tweet_normalizes_response() -> None:
    captured: list[FakeSession] = []
    payload = {
        "tweet": {"id": "123456789012345678", "text": "Hello"},
        "author": {"username": "flyto2"},
    }

    with xquik_patch(FakeResponse(200, payload), captured):
        result = await XquikGetTweetModule(
            {"tweet_id": "123456789012345678", "api_key": "test-key"},
            {},
        ).execute()

    assert result["tweet"] == payload["tweet"]
    assert result["author"] == payload["author"]
    assert captured[0].request_details["url"].endswith("/x/tweets/123456789012345678")


@pytest.mark.asyncio
async def test_get_user_accepts_at_username() -> None:
    captured: list[FakeSession] = []
    profile = {"id": "42", "username": "flyto2"}

    with xquik_patch(FakeResponse(200, profile), captured):
        result = await XquikGetUserModule(
            {"user": "@flyto2", "api_key": "test-key"},
            {},
        ).execute()

    assert result["user"] == profile
    assert captured[0].request_details["url"].endswith("/x/users/flyto2")


@pytest.mark.asyncio
async def test_create_tweet_sends_idempotent_request() -> None:
    captured: list[FakeSession] = []
    response = FakeResponse(202, {"id": "action-1", "status": "pending"})

    with xquik_patch(response, captured):
        result = await XquikCreateTweetModule(
            {
                "account": "@flyto2",
                "text": "Hello",
                "reply_to_tweet_id": "123",
                "idempotency_key": "write-1",
                "api_key": "test-key",
            },
            {},
        ).execute()

    assert result["action"] == {"id": "action-1", "status": "pending"}
    assert captured[0].request_details["headers"]["Idempotency-Key"] == "write-1"
    assert captured[0].request_details["json"] == {
        "account": "@flyto2",
        "text": "Hello",
        "reply_to_tweet_id": "123",
        "is_note_tweet": False,
    }


@pytest.mark.parametrize(
    "params",
    [
        {"account": "@flyto2", "idempotency_key": "write-1"},
        {
            "account": "@flyto2",
            "media": ["1", "2", "3", "4", "5"],
            "idempotency_key": "write-1",
        },
        {"account": "@flyto2", "text": "Hello"},
    ],
)
def test_create_tweet_validates_content_and_idempotency(params) -> None:
    with pytest.raises(ValueError):
        XquikCreateTweetModule(params, {})


@pytest.mark.asyncio
async def test_get_write_action_supports_pending_responses() -> None:
    captured: list[FakeSession] = []
    payload = {"id": "action-1", "status": "pending"}

    with xquik_patch(FakeResponse(202, payload), captured):
        result = await XquikGetWriteActionModule(
            {"action_id": "action-1", "api_key": "test-key"},
            {},
        ).execute()

    assert result["http_status"] == 202
    assert result["action"] == payload
    assert captured[0].request_details["url"].endswith("/x/write-actions/action-1")


def test_xquik_modules_are_registered() -> None:
    module_ids = [
        "api.xquik.request",
        "api.xquik.search_tweets",
        "api.xquik.get_tweet",
        "api.xquik.get_user",
        "api.xquik.create_tweet",
        "api.xquik.get_write_action",
    ]

    assert all(ModuleRegistry.get(module_id) is not None for module_id in module_ids)
