"""Tests for third-party search API modules."""

from unittest.mock import patch

import pytest

from core.constants import APIEndpoints, EnvVars
from core.modules.third_party.developer.http.search import TavilySearchModule


class FakeResponse:
    """Minimal async response context used by the Tavily module tests."""

    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


class FakeSession:
    """Capture outgoing request details without contacting Tavily."""

    def __init__(self, response, *, timeout):
        self.response = response
        self.timeout = timeout
        self.request = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def post(self, url, *, headers, json):
        self.request = {"url": url, "headers": headers, "json": json}
        return self.response


def session_factory(response, captured):
    def factory(*, timeout):
        session = FakeSession(response, timeout=timeout)
        captured.append(session)
        return session

    return factory


@pytest.mark.asyncio
async def test_tavily_search_requires_api_key(monkeypatch):
    monkeypatch.delenv(EnvVars.TAVILY_API_KEY, raising=False)

    result = await TavilySearchModule({"keyword": "Flyto2"}, {}).execute()

    assert result["status"] == "error"
    assert EnvVars.TAVILY_API_KEY in result["message"]


@pytest.mark.asyncio
async def test_tavily_search_uses_bearer_auth_and_normalizes_results(monkeypatch):
    monkeypatch.setenv(EnvVars.TAVILY_API_KEY, "test-key")
    captured = []
    response = FakeResponse(
        200,
        {
            "results": [
                {
                    "title": "Flyto2 documentation",
                    "url": "https://docs.flyto2.com/",
                    "content": "Build reproducible AI agent workflows.",
                }
            ]
        },
    )

    with patch(
        "core.modules.third_party.developer.http.search.aiohttp.ClientSession",
        side_effect=session_factory(response, captured),
    ):
        result = await TavilySearchModule(
            {"keyword": "Flyto2 agent workflows", "limit": 50}, {}
        ).execute()

    assert result == {
        "status": "success",
        "data": [
            {
                "title": "Flyto2 documentation",
                "url": "https://docs.flyto2.com/",
                "description": "Build reproducible AI agent workflows.",
            }
        ],
        "count": 1,
    }
    assert captured[0].timeout.total == 30
    assert captured[0].request == {
        "url": APIEndpoints.TAVILY_BASE_URL,
        "headers": {"Authorization": "Bearer test-key"},
        "json": {
            "query": "Flyto2 agent workflows",
            "max_results": APIEndpoints.TAVILY_MAX_RESULTS,
            "search_depth": "basic",
        },
    }
    assert "api_key" not in captured[0].request["json"]


@pytest.mark.asyncio
async def test_tavily_search_reports_http_error(monkeypatch):
    monkeypatch.setenv(EnvVars.TAVILY_API_KEY, "test-key")
    captured = []

    with patch(
        "core.modules.third_party.developer.http.search.aiohttp.ClientSession",
        side_effect=session_factory(FakeResponse(429, {}), captured),
    ):
        result = await TavilySearchModule({"keyword": "Flyto2"}, {}).execute()

    assert result == {"status": "error", "message": "API error: HTTP 429"}
